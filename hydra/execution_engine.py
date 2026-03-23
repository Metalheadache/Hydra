"""
Execution Engine — DAG-based hybrid (parallel + sequential) agent runner.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from hydra.agent import Agent
from hydra.models import AgentOutput, AgentStatus, TaskPlan

if TYPE_CHECKING:
    from hydra.config import HydraConfig
    from hydra.state_manager import StateManager

logger = structlog.get_logger(__name__)


class ExecutionEngine:
    """
    Executes a TaskPlan DAG:

    - Groups within the plan are executed sequentially.
    - Agents within each group are dispatched concurrently (asyncio.gather).
    - A semaphore limits concurrent API calls to avoid rate limits.
    - Each agent has a per-agent timeout.
    - Failed agents are retried with exponential backoff.
    - A global token budget aborts execution if exceeded.
    """

    def __init__(
        self,
        config: "HydraConfig",
        agents: dict[str, Agent],
        state_manager: "StateManager",
        plan: TaskPlan,
    ) -> None:
        self.config = config
        self.agents = agents
        self.state_manager = state_manager
        self.plan = plan

        self._semaphore = asyncio.Semaphore(config.max_concurrent_agents)
        self._total_tokens_used = 0
        self._budget_exceeded = False

    async def execute(self) -> None:
        """Execute all execution groups in the plan sequentially."""
        logger.info(
            "engine_starting",
            total_groups=len(self.plan.execution_groups),
            total_agents=len(self.agents),
        )

        for group_index, group in enumerate(self.plan.execution_groups):
            if self._budget_exceeded:
                logger.error("token_budget_exceeded_aborting", group=group_index)
                break

            logger.info("group_starting", group_index=group_index, sub_tasks=group)
            group_start = time.monotonic()

            # Dispatch all agents in this group concurrently
            tasks = [self._execute_with_retry(sub_task_id) for sub_task_id in group]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results — exceptions that escaped retry logic
            for sub_task_id, result in zip(group, results):
                if isinstance(result, BaseException):
                    logger.error(
                        "group_agent_unhandled_exception",
                        sub_task_id=sub_task_id,
                        error=str(result),
                    )
                    agent = self.agents.get(sub_task_id)
                    agent_id = agent.agent_spec.agent_id if agent else sub_task_id
                    failed_output = AgentOutput(
                        agent_id=agent_id,
                        sub_task_id=sub_task_id,
                        status=AgentStatus.FAILED,
                        error=f"Unhandled exception: {result}",
                    )
                    await self.state_manager.write_output(sub_task_id, failed_output)

            elapsed_ms = int((time.monotonic() - group_start) * 1000)
            logger.info("group_done", group_index=group_index, elapsed_ms=elapsed_ms)

        logger.info("engine_done", total_tokens=self._total_tokens_used)

    # ── Private ───────────────────────────────────────────────────────────────

    async def _execute_with_retry(self, sub_task_id: str) -> None:
        """Execute a single agent with retry logic and exponential backoff."""
        agent = self.agents.get(sub_task_id)
        if agent is None:
            logger.error("agent_not_found", sub_task_id=sub_task_id)
            return

        max_retries = agent.sub_task.max_retries if agent.sub_task.retry_allowed else 0
        backoff = self.config.retry_backoff_base
        last_error: str = ""
        extra_context = ""

        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(
                    "agent_retry",
                    sub_task_id=sub_task_id,
                    attempt=attempt,
                    backoff_s=backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)  # Cap at 30s
                extra_context = f"Previous attempt failed: {last_error}\nPlease try a different approach."

            output = await self._execute_single(agent, extra_context)

            # NOTE: agent.execute() already writes the output to StateManager internally.
            # We do NOT write again here to avoid a double write. The only place the
            # engine writes to state is in _execute_single's except/timeout branches,
            # which cover the case where agent.execute() itself raised unexpectedly.

            if output.status == AgentStatus.COMPLETED:
                self._total_tokens_used += output.tokens_used
                if self._total_tokens_used > self.config.total_token_budget:
                    logger.error(
                        "token_budget_exceeded",
                        used=self._total_tokens_used,
                        budget=self.config.total_token_budget,
                    )
                    self._budget_exceeded = True
                return

            last_error = output.error or "Unknown failure"
            logger.warning(
                "agent_attempt_failed",
                sub_task_id=sub_task_id,
                attempt=attempt,
                error=last_error,
            )

        # All retries exhausted — the last failed output is already written to state by the agent
        logger.error("agent_all_retries_failed", sub_task_id=sub_task_id, max_retries=max_retries)

    async def _execute_single(self, agent: Agent, extra_context: str = "") -> AgentOutput:
        """Execute one agent with timeout and semaphore control."""
        async with self._semaphore:
            try:
                output = await asyncio.wait_for(
                    agent.execute(extra_context=extra_context),
                    timeout=self.config.per_agent_timeout_seconds,
                )
                return output
            except asyncio.TimeoutError:
                timeout = self.config.per_agent_timeout_seconds
                logger.error(
                    "agent_timeout",
                    agent_id=agent.agent_spec.agent_id,
                    sub_task_id=agent.agent_spec.sub_task_id,
                    timeout_s=timeout,
                )
                failed = AgentOutput(
                    agent_id=agent.agent_spec.agent_id,
                    sub_task_id=agent.agent_spec.sub_task_id,
                    status=AgentStatus.FAILED,
                    error=f"Agent timed out after {timeout}s",
                )
                await self.state_manager.write_output(agent.agent_spec.sub_task_id, failed)
                return failed
