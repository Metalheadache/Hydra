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

import structlog

from hydra.agent_factory import AgentFactory
from hydra.brain import Brain
from hydra.config import HydraConfig
from hydra.execution_engine import ExecutionEngine
from hydra.logger import configure_logging
from hydra.post_brain import PostBrain
from hydra.state_manager import StateManager
from hydra.tool_registry import ToolRegistry

logger = structlog.get_logger(__name__)

__version__ = "0.1.0"
__all__ = ["Hydra", "HydraConfig"]


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

    async def _run_pipeline(self, task: str, state_ref: list | None = None) -> dict:
        """Internal pipeline: Brain → Factory → Engine → PostBrain."""
        # Fresh state for each run
        state = StateManager()
        # Expose state to caller so partial results can be harvested on timeout
        if state_ref is not None:
            state_ref.append(state)

        # 1. Brain: decompose task → TaskPlan
        brain = Brain(self.config, self.tool_registry)
        plan = await brain.plan(task)

        # 2. Factory: instantiate agents from plan
        factory = AgentFactory(self.config, self.tool_registry, state)
        agents = factory.create_agents(plan)

        # 3. Engine: execute DAG
        engine = ExecutionEngine(self.config, agents, state, plan)
        await engine.execute()

        # 4. Post-Brain: quality check + synthesize
        post_brain = PostBrain(self.config, state, plan)
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
