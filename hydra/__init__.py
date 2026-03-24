"""
Hydra — Dynamic Multi-Agent Orchestration Framework.

Usage::

    import asyncio
    from hydra import Hydra

    async def main():
        hydra = Hydra()
        result = await hydra.run("Analyze the AI agent market and write a report.")
        print(result["output"])

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Callable

import structlog

from hydra.agent_factory import AgentFactory
from hydra.brain import Brain
from hydra.config import HydraConfig
from hydra.events import EventBus, EventType, HydraEvent
from hydra.execution_engine import ExecutionEngine
from hydra.logger import configure_logging
from hydra.post_brain import PostBrain
from hydra.state_manager import StateManager
from hydra.tool_registry import ToolRegistry

logger = structlog.get_logger(__name__)

__version__ = "0.1.0"
__all__ = ["Hydra", "HydraConfig", "EventBus", "EventType", "HydraEvent"]


class Hydra:
    """
    Top-level orchestrator for the Hydra framework.

    Wires together Brain → AgentFactory → ExecutionEngine → PostBrain.

    Example::

        hydra = Hydra()
        result = await hydra.run("Summarize recent AI news.")
    """

    def __init__(self, config: HydraConfig | None = None) -> None:
        self.config = config or HydraConfig()

        # Setup logging
        configure_logging()

        # Initialize tool registry with all built-in tools
        # Pass config so file tools are wired to the correct output_directory
        self.tool_registry = ToolRegistry()
        self.tool_registry.register_defaults(config=self.config)

        # Storage for registered callbacks (event_type, callback) pairs.
        # None as event_type = catch-all.
        self._event_callbacks: list[tuple[EventType | None, Callable[[HydraEvent], None]]] = []

        logger.info(
            "hydra_initialized",
            model=self.config.default_model,
            tools=len(self.tool_registry),
        )

    async def run(self, task: str) -> dict:
        """
        Execute a complex task end-to-end using the full pipeline.

        The entire pipeline is wrapped in a total timeout
        (config.total_task_timeout_seconds). On timeout, partial results are
        returned with a timeout warning.

        Args:
            task: Natural language description of the task to accomplish.

        Returns:
            A dict with:
            - output: synthesized final answer (str)
            - warnings: list of quality warnings
            - execution_summary: token/time statistics
            - files_generated: list of filepaths created
            - per_agent_quality: per-agent metadata
            - agents_needing_retry: sub_task_ids flagged for quality retry
        """
        logger.info("hydra_run_start", task_preview=task[:100])

        # We need a reference to state so we can harvest partial results on timeout.
        # _run_pipeline creates a fresh StateManager internally; we capture it via a
        # mutable container so the timeout handler can access it even after the coroutine
        # was cancelled.
        state_ref: list[StateManager] = []

        try:
            result = await asyncio.wait_for(
                self._run_pipeline(task, state_ref=state_ref),
                timeout=self.config.total_task_timeout_seconds,
            )
        except asyncio.TimeoutError:
            timeout = self.config.total_task_timeout_seconds
            logger.error("hydra_total_timeout", timeout_s=timeout)

            # Harvest whatever was completed before the timeout
            partial_outputs: dict = {}
            partial_summary: dict = {}
            partial_files: list = []
            if state_ref:
                state = state_ref[0]
                try:
                    raw_outputs = await state.get_all_outputs()
                    partial_summary = await state.get_execution_summary()
                    files_dict = await state.get_all_files()
                    partial_files = list(files_dict.values())
                    for sub_task_id, output in raw_outputs.items():
                        partial_outputs[sub_task_id] = {
                            "status": output.status,
                            "tokens_used": output.tokens_used,
                            "execution_time_ms": output.execution_time_ms,
                            "quality_score": output.quality_score,
                            "error": output.error,
                        }
                except Exception as harvest_exc:
                    logger.warning("partial_harvest_failed", error=str(harvest_exc))

            result = {
                "output": (
                    f"[Task timed out after {timeout}s] "
                    "The pipeline did not complete within the allotted time. "
                    "Partial results are included in per_agent_quality."
                ),
                "warnings": [f"Total task timeout exceeded ({timeout}s). Results may be incomplete."],
                "execution_summary": partial_summary,
                "files_generated": partial_files,
                "per_agent_quality": partial_outputs,
                "agents_needing_retry": [],
            }

        logger.info(
            "hydra_run_complete",
            warnings=len(result.get("warnings", [])),
            files=len(result.get("files_generated", [])),
        )
        return result

    # ── Callback hooks ────────────────────────────────────────────────────────

    def on_agent_start(self, callback: Callable[[HydraEvent], None]) -> None:
        """Register a callback fired when any agent starts."""
        self._event_callbacks.append((EventType.AGENT_START, callback))

    def on_agent_complete(self, callback: Callable[[HydraEvent], None]) -> None:
        """Register a callback fired when any agent completes."""
        self._event_callbacks.append((EventType.AGENT_COMPLETE, callback))

    def on_tool_call(self, callback: Callable[[HydraEvent], None]) -> None:
        """Register a callback fired on every tool call."""
        self._event_callbacks.append((EventType.AGENT_TOOL_CALL, callback))

    def on_event(self, callback: Callable[[HydraEvent], None]) -> None:
        """Register a catch-all callback for all events."""
        self._event_callbacks.append((None, callback))  # None = all events

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def stream(self, task: str) -> AsyncGenerator[HydraEvent, None]:
        """
        Execute task and stream events as they happen.

        Usage::

            async for event in hydra.stream("My task"):
                print(event.type, event.data)
        """
        event_bus = EventBus()
        # Mark stream consumer before pipeline starts so close() sends the sentinel
        # and all emitted events are enqueued from the start.
        event_bus._has_stream_consumer = True

        # Apply registered callbacks to this bus
        self._wire_callbacks(event_bus)

        # Start pipeline in background task
        pipeline_task = asyncio.create_task(
            self._run_pipeline_with_events(task, event_bus)
        )

        # Yield events as they arrive, with total timeout
        try:
            async with asyncio.timeout(self.config.total_task_timeout_seconds):
                async for event in event_bus.stream():
                    yield event
                    if event.type in (EventType.PIPELINE_COMPLETE, EventType.PIPELINE_ERROR):
                        break
        except TimeoutError:
            yield HydraEvent(
                type=EventType.PIPELINE_ERROR,
                data={"error": "Pipeline timed out"},
            )
        finally:
            pipeline_task.cancel()
            try:
                await pipeline_task
            except (asyncio.CancelledError, Exception) as exc:
                if not isinstance(exc, asyncio.CancelledError):
                    logger.error("stream_pipeline_exception", error=str(exc))

    # ── Private ───────────────────────────────────────────────────────────────

    def _wire_callbacks(self, event_bus: EventBus) -> None:
        """Register stored callbacks on the given event_bus."""
        for event_type, callback in self._event_callbacks:
            if event_type is None:
                # catch-all
                event_bus.on(callback)
            else:
                # filtered wrapper
                _type = event_type  # capture in closure

                def _make_filtered(t: EventType, cb: Callable[[HydraEvent], None]):
                    def _filtered(event: HydraEvent) -> None:
                        if event.type == t:
                            cb(event)
                    return _filtered

                event_bus.on(_make_filtered(_type, callback))

    async def _run_pipeline_with_events(self, task: str, event_bus: EventBus) -> dict:
        """Run the pipeline with events, emitting PIPELINE_START/COMPLETE/ERROR."""
        await event_bus.emit(HydraEvent(
            type=EventType.PIPELINE_START,
            data={"task_preview": task[:100]},
        ))

        try:
            result = await self._run_pipeline(task, event_bus=event_bus)
            await event_bus.emit(HydraEvent(
                type=EventType.PIPELINE_COMPLETE,
                data={
                    "warnings": len(result.get("warnings", [])),
                    "files": len(result.get("files_generated", [])),
                },
            ))
            await event_bus.close()
            return result
        except Exception as exc:
            await event_bus.emit(HydraEvent(
                type=EventType.PIPELINE_ERROR,
                data={"error": str(exc)},
            ))
            await event_bus.close()
            raise

    async def _run_pipeline(self, task: str, state_ref: list | None = None, event_bus: EventBus | None = None) -> dict:
        """Internal pipeline: Brain → Factory → Engine → PostBrain."""
        # Fresh state for each run
        state = StateManager()
        # Expose state to caller so partial results can be harvested on timeout
        if state_ref is not None:
            state_ref.append(state)

        # Wire registered callbacks if no event_bus provided (run() path)
        if event_bus is None and self._event_callbacks:
            event_bus = EventBus()
            self._wire_callbacks(event_bus)

        # 1. Brain: decompose task → TaskPlan
        brain = Brain(self.config, self.tool_registry, event_bus=event_bus)
        plan = await brain.plan(task)

        # 2. Factory: instantiate agents from plan
        factory = AgentFactory(self.config, self.tool_registry, state, event_bus=event_bus)
        agents = factory.create_agents(plan)

        # 3. Engine: execute DAG
        engine = ExecutionEngine(self.config, agents, state, plan, event_bus=event_bus)
        await engine.execute()

        # 4. Post-Brain: quality check + synthesize
        post_brain = PostBrain(self.config, state, plan, event_bus=event_bus)
        result = await post_brain.synthesize()

        # 5. Quality retry loop (single cycle, to prevent infinite loops)
        agents_needing_retry = result.get("agents_needing_retry", [])
        if agents_needing_retry:
            logger.info("quality_retry_starting", agents=agents_needing_retry)
            retry_tasks = [engine._execute_with_retry(sub_task_id) for sub_task_id in agents_needing_retry]
            await asyncio.gather(*retry_tasks, return_exceptions=True)

            # Re-synthesize to incorporate retry results
            result = await post_brain.synthesize()
            result["retry_metadata"] = {
                "retried_agents": agents_needing_retry,
                "retry_performed": True,
            }
            logger.info("quality_retry_complete", retried=agents_needing_retry)
        else:
            result["retry_metadata"] = {"retried_agents": [], "retry_performed": False}

        return result
