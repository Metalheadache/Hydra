"""
Hydra — Dynamic Multi-Agent Orchestration Framework.

Usage::

    import asyncio
    from hydra_agents import Hydra

    async def main():
        hydra = Hydra()
        result = await hydra.run("Analyze the AI agent market and write a report.")
        print(result["output"])

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncGenerator, Callable

import structlog

from hydra_agents.agent_factory import AgentFactory
from hydra_agents.audit import AuditLogger
from hydra_agents.brain import Brain
from hydra_agents.config import HydraConfig
from hydra_agents.events import EventBus, EventType, HydraEvent
from hydra_agents.execution_engine import ExecutionEngine
from hydra_agents.file_processor import FileProcessor
from hydra_agents.logger import configure_logging
from hydra_agents.models import FileAttachment
from hydra_agents.post_brain import PostBrain
from hydra_agents.state_manager import StateManager
from hydra_agents.tool_registry import ToolRegistry

logger = structlog.get_logger(__name__)

__version__ = "1.0.1"
__all__ = ["Hydra", "HydraConfig", "EventBus", "EventType", "HydraEvent"]

# Configure logging once at module level rather than on every Hydra() instantiation
configure_logging()


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

    async def run(self, task: str, files: list[str] | None = None) -> dict:
        """
        Execute a complex task end-to-end using the full pipeline.

        The entire pipeline is wrapped in a total timeout
        (config.total_task_timeout_seconds). On timeout, partial results are
        returned with a timeout warning.

        Args:
            task: Natural language description of the task to accomplish.
            files: Optional list of file paths to attach for agent processing.

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
                self._run_pipeline(task, state_ref=state_ref, files=files),
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

    async def stream(self, task: str, files: list[str] | None = None, event_bus: EventBus | None = None) -> AsyncGenerator[HydraEvent, None]:
        """
        Execute task and stream events as they happen.

        Args:
            task: Natural language description of the task to accomplish.
            files: Optional list of file paths to attach for agent processing.
            event_bus: Optional EventBus to use. If provided, the caller owns the bus
                and can register listeners (e.g. audit) before calling stream().
                If None (default), a new EventBus is created internally.

        Usage::

            async for event in hydra.stream("My task"):
                print(event.type, event.data)
        """
        if event_bus is None:
            event_bus = EventBus()
        # Mark stream consumer before pipeline starts so close() sends the sentinel
        # and all emitted events are enqueued from the start.
        event_bus._has_stream_consumer = True

        # Apply registered callbacks to this bus
        self._wire_callbacks(event_bus)

        # Start pipeline in background task
        pipeline_task = asyncio.create_task(
            self._run_pipeline_with_events(task, event_bus, files=files)  # type: ignore[arg-type]
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
            if not pipeline_task.done():
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

    async def _run_pipeline_with_events(
        self, task: str, event_bus: EventBus, files: list[str] | None = None
    ) -> dict:
        """Run the pipeline with events, emitting PIPELINE_START/COMPLETE/ERROR."""
        await event_bus.emit(HydraEvent(
            type=EventType.PIPELINE_START,
            data={"task_preview": task[:100]},
        ))

        try:
            result = await self._run_pipeline(task, event_bus=event_bus, files=files)
            await event_bus.emit(HydraEvent(
                type=EventType.PIPELINE_COMPLETE,
                data=result,  # full result dict — frontend reads event.data for output/warnings/etc
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

    async def _run_pipeline(
        self,
        task: str,
        state_ref: list | None = None,
        event_bus: EventBus | None = None,
        files: list[str] | None = None,
    ) -> dict:
        """Internal pipeline: Brain → Factory → Engine → PostBrain."""
        # Fresh state for each run
        audit_logger = AuditLogger(self.config.output_directory)
        state = StateManager(audit_logger=audit_logger)
        # Expose state to caller so partial results can be harvested on timeout
        if state_ref is not None:
            state_ref.append(state)

        # Wire registered callbacks if no event_bus provided (run() path)
        # MUST happen BEFORE file processing so FILE_PROCESSED events reach callbacks
        if event_bus is None and self._event_callbacks:
            event_bus = EventBus()
            self._wire_callbacks(event_bus)

        # 0. File processing — runs before Brain so files are in the prompt
        enhanced_task = task
        if files:
            enhanced_task = await self._process_files(
                task, files, state, event_bus
            )

        # 1. Brain: decompose task → TaskPlan
        brain = Brain(self.config, self.tool_registry, event_bus=event_bus)
        plan = await brain.plan(enhanced_task, has_files=bool(files))

        # 2. Factory: instantiate agents from plan
        factory = AgentFactory(
            self.config, self.tool_registry, state, event_bus=event_bus,
            audit_logger=audit_logger,
        )
        agents = factory.create_agents(plan)

        # 3. Engine: execute DAG
        engine = ExecutionEngine(self.config, agents, state, plan, event_bus=event_bus)
        await engine.execute()

        # 4. Post-Brain: quality check + synthesize
        post_brain = PostBrain(self.config, state, plan, event_bus=event_bus, audit_logger=audit_logger)
        result = await post_brain.synthesize()

        # Replace plan's original_task with enhanced_task (if files were attached)
        # This ensures the plan context is consistent with what Brain received.
        if files:
            plan.original_task = enhanced_task

        # 5. Quality retry loop (single cycle, to prevent infinite loops)
        agents_needing_retry = result.get("agents_needing_retry", [])
        if agents_needing_retry:
            logger.info("quality_retry_starting", agents=agents_needing_retry)
            retry_tasks = [engine._execute_with_retry(sub_task_id) for sub_task_id in agents_needing_retry]
            await asyncio.gather(*retry_tasks, return_exceptions=True)

            # Check which agents explicitly failed after retry
            # Only skip re-synthesis if ALL agents explicitly failed (status == FAILED)
            # Agents with missing output (e.g. during testing or if execution engine
            # didn't write back) are treated as unknown → still re-synthesize
            from hydra_agents.models import AgentStatus
            failed_retries = []
            for sub_task_id in agents_needing_retry:
                output = await state.get_output(sub_task_id)
                if output is not None and output.status == AgentStatus.FAILED:
                    logger.warning(
                        "quality_retry_agent_still_failed",
                        sub_task_id=sub_task_id,
                        status=output.status,
                    )
                    failed_retries.append(sub_task_id)

            if len(failed_retries) == len(agents_needing_retry) and failed_retries:
                # All retries explicitly failed — keep original result, skip re-synthesis
                logger.warning("quality_retry_all_failed", agents=failed_retries)
            else:
                # Some retries succeeded (or unknown) — re-synthesize
                result = await post_brain.synthesize()

            result["retry_metadata"] = {
                "retried_agents": agents_needing_retry,
                "retry_performed": True,
                "failed_retries": failed_retries,
            }
            logger.info("quality_retry_complete", retried=agents_needing_retry, failed=failed_retries)
        else:
            result["retry_metadata"] = {"retried_agents": [], "retry_performed": False}

        return result

    async def _process_files(
        self,
        task: str,
        files: list[str],
        state: StateManager,
        event_bus: EventBus | None,
    ) -> str:
        """
        Process attached files and return an enhanced task prompt.

        Steps:
        1. Process each file through FileProcessor → FileAttachment
        2. Store FileAttachments in StateManager
        3. Emit FILE_PROCESSED events (if event_bus present)
        4. Build enhanced task prompt with file context
        """
        # Enforce file count limit
        max_files = self.config.max_upload_files
        if len(files) > max_files:
            raise ValueError(
                f"Too many files: {len(files)} provided, maximum is {max_files}."
            )

        file_processor = FileProcessor(self.config.output_directory)
        attachments: list[FileAttachment] = []
        max_size_bytes = self.config.max_upload_file_size_mb * 1024 * 1024

        for filepath in files:
            # Skip files that are too large
            p = Path(filepath)
            if p.exists() and p.stat().st_size > max_size_bytes:
                logger.warning(
                    "file_too_large_skipped",
                    filepath=str(filepath),
                    size_bytes=p.stat().st_size,
                    limit_bytes=max_size_bytes,
                )
                continue

            # Use the public process() method instead of private _process_single_path
            results = await file_processor.process([filepath])
            attachment = results[0]
            attachments.append(attachment)

            if event_bus:
                await event_bus.emit(HydraEvent(
                    type=EventType.FILE_PROCESSED,
                    data={
                        "filename": attachment.original_name,
                        "size_bytes": attachment.size_bytes,
                        "mime_type": attachment.mime_type,
                        "has_text": attachment.extracted_text is not None,
                    },
                ))

        # Store in state so agents can reference later
        await state.store_files(attachments)

        # Build enhanced prompt
        lines: list[str] = [f"USER TASK: {task}", "", "ATTACHED FILES:"]
        for i, att in enumerate(attachments, 1):
            size_kb = att.size_bytes / 1024
            size_str = f"{size_kb:.1f}KB" if size_kb < 1024 else f"{size_kb / 1024:.1f}MB"

            if att.extracted_text is not None:
                preview = att.extracted_text[:500]
                if len(att.extracted_text) > 500:
                    preview += "..."
                lines.append(f"{i}. {att.original_name} ({size_str}) — {preview}")
            else:
                lines.append(
                    f"{i}. {att.original_name} ({size_str}) — "
                    f"[binary file, available at {att.filepath}]"
                )

        # Update Brain prompt context for files
        if attachments:
            lines.extend([
                "",
                f"NOTE: {len(attachments)} file(s) have been attached. "
                "Text content has been extracted where possible. "
                "Full file paths are available for direct tool access.",
            ])

        logger.info("files_processed", count=len(attachments), task_preview=task[:80])
        return "\n".join(lines)
