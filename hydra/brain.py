"""
Brain (Planner) — decomposes a complex task into a TaskPlan.
"""

from __future__ import annotations

import json
import re
from typing import Any

import litellm
import structlog

from hydra.config import HydraConfig
from hydra.models import TaskPlan
from hydra.tool_registry import ToolRegistry

logger = structlog.get_logger(__name__)

_MAX_PLAN_RETRIES = 2


def _extract_json(text: str) -> str:
    """
    Extract the first JSON object or array from a text response.
    Handles markdown code fences and extraneous surrounding text.
    """
    # Try to unwrap ```json ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence_match:
        return fence_match.group(1).strip()

    # Try to find a bare JSON object
    obj_match = re.search(r"\{[\s\S]+\}", text)
    if obj_match:
        return obj_match.group(0)

    return text.strip()


class Brain:
    """
    The Brain receives a complex task description and returns a TaskPlan
    by making a single structured LLM call.

    The LLM is instructed to:
    1. Decompose the task into 3-6 independent sub-tasks.
    2. Design an AgentSpec for each sub-task.
    3. Build a dependency graph (execution_groups).
    4. Return a single JSON object matching the TaskPlan schema.
    """

    def __init__(self, config: HydraConfig, tool_registry: ToolRegistry) -> None:
        self.config = config
        self.tool_registry = tool_registry

    async def plan(self, task: str) -> TaskPlan:
        """
        Decompose ``task`` into a TaskPlan.

        Raises:
            ValueError: If the LLM cannot produce a valid TaskPlan after retries.
        """
        logger.info("brain_planning", task_preview=task[:120])

        system_prompt = self._build_system_prompt()
        user_message = f"Decompose this task into a complete execution plan:\n\n{task}"

        last_error: Exception | None = None
        for attempt in range(_MAX_PLAN_RETRIES + 1):
            if attempt > 0:
                logger.warning("brain_retry", attempt=attempt, error=str(last_error))
                user_message = (
                    f"{user_message}\n\n"
                    "IMPORTANT: Your previous response could not be parsed. "
                    "Return ONLY a valid JSON object — no markdown, no explanation, no extra text."
                )

            try:
                plan = await self._call_llm(system_prompt, user_message)
                logger.info("brain_plan_ready", sub_tasks=len(plan.sub_tasks), groups=len(plan.execution_groups))
                return plan
            except Exception as exc:
                last_error = exc

        raise ValueError(
            f"Brain failed to produce a valid TaskPlan after {_MAX_PLAN_RETRIES + 1} attempts. "
            f"Last error: {last_error}"
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        tool_descriptions = self.tool_registry.get_tool_descriptions()
        schema = json.dumps(TaskPlan.model_json_schema(), indent=2)

        return (
            "You are a task planning AI. Given a complex task, your job is to:\n"
            "1. Decompose it into the minimum number of independent sub-tasks (prefer 3-6).\n"
            "2. Design a specialized AI agent for each sub-task.\n"
            "3. Build a dependency graph (execution_groups) — independent tasks in the same group, "
            "dependent tasks in later groups.\n\n"
            "## Rules\n"
            "- Minimize sub-tasks. Do not create agents for trivial steps.\n"
            "- Each agent's role must be highly specific to its sub-task.\n"
            "- Select only the tools each agent actually needs (fewer tools = better performance).\n"
            "- Output constraints must be specific and measurable.\n"
            "- execution_groups is a list of lists of sub-task IDs (topologically sorted).\n"
            "- Every sub-task ID referenced in execution_groups must appear in the sub_tasks list.\n"
            "- Every agent_spec's sub_task_id must reference a sub-task ID in sub_tasks.\n\n"
            f"## Available Tools\n{tool_descriptions}\n\n"
            f"## Output Schema\nRespond with ONLY a JSON object matching this schema:\n{schema}\n\n"
            "Do NOT include any text outside the JSON object."
        )

    async def _call_llm(self, system_prompt: str, user_message: str) -> TaskPlan:
        """Call the LLM and parse the JSON response into a TaskPlan."""
        call_kwargs: dict[str, Any] = {
            "model": self.config.brain_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.config.max_tokens_brain,
            "temperature": 0.2,  # Low temperature for structured output
        }
        if self.config.api_key:
            call_kwargs["api_key"] = self.config.api_key
        if self.config.api_base:
            call_kwargs["api_base"] = self.config.api_base

        response = await litellm.acompletion(**call_kwargs)
        raw_text = response.choices[0].message.content or ""

        logger.debug("brain_raw_response", chars=len(raw_text))

        json_text = _extract_json(raw_text)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Brain response is not valid JSON: {exc}\n\nRaw response:\n{raw_text[:500]}") from exc

        try:
            plan = TaskPlan.model_validate(data)
        except Exception as exc:
            raise ValueError(f"Brain response does not match TaskPlan schema: {exc}") from exc

        self._validate_plan_consistency(plan)
        return plan

    @staticmethod
    def _validate_plan_consistency(plan: TaskPlan) -> None:
        """
        Ensure sub_task IDs are consistent across execution_groups and agent_specs.
        Raises ValueError on inconsistency.
        """
        sub_task_ids = {st.id for st in plan.sub_tasks}
        agent_sub_task_ids = {spec.sub_task_id for spec in plan.agent_specs}

        # All execution group entries must reference valid sub-tasks
        for group in plan.execution_groups:
            for st_id in group:
                if st_id not in sub_task_ids:
                    raise ValueError(
                        f"execution_groups references unknown sub_task_id: '{st_id}'. "
                        f"Available IDs: {sorted(sub_task_ids)}"
                    )

        # All agent specs must reference valid sub-tasks
        for spec in plan.agent_specs:
            if spec.sub_task_id not in sub_task_ids:
                raise ValueError(
                    f"AgentSpec '{spec.agent_id}' references unknown sub_task_id: '{spec.sub_task_id}'"
                )

        # Every sub-task must appear in at least one execution group (no orphans)
        grouped_ids: set[str] = {st_id for group in plan.execution_groups for st_id in group}
        orphaned = sub_task_ids - grouped_ids
        if orphaned:
            raise ValueError(
                f"Sub-tasks {sorted(orphaned)} are not included in any execution group. "
                "Every sub-task must appear in at least one execution group."
            )

        logger.debug(
            "plan_consistency_ok",
            sub_tasks=len(sub_task_ids),
            agent_specs=len(agent_sub_task_ids),
            groups=len(plan.execution_groups),
        )
