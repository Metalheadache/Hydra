"""
Hydra Agent — executes a single sub-task with LLM + tool-use loop.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

import litellm
import structlog

from hydra.models import AgentOutput, AgentSpec, AgentStatus, SubTask, ToolResult
from hydra.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from hydra.config import HydraConfig
    from hydra.state_manager import StateManager

logger = structlog.get_logger(__name__)

_MAX_TOOL_ITERATIONS = 20  # Safety cap to prevent infinite tool-use loops


def _build_system_prompt(spec: AgentSpec, tool_schemas: list[dict]) -> str:
    """Construct the system prompt for an agent from its spec."""
    tool_names = ", ".join(spec.tools_needed) if spec.tools_needed else "none"
    constraints = "\n".join(f"- {c}" for c in spec.constraints) if spec.constraints else "- None"

    schema_section = ""
    if spec.output_schema:
        schema_section = f"\n\n## Expected Output Schema\nYour final response MUST conform to this JSON Schema:\n{json.dumps(spec.output_schema, indent=2)}"

    return (
        f"## Role\n{spec.role}\n\n"
        f"## Goal\n{spec.goal}\n\n"
        f"## Backstory\n{spec.backstory}\n\n"
        f"## Constraints\n{constraints}"
        f"{schema_section}\n\n"
        f"## Available Tools\n{tool_names}\n\n"
        "Use your tools to gather information and complete the task. "
        "When you have finished all research and analysis, provide your final answer directly — "
        "do NOT call any more tools at that point."
    )


class Agent:
    """
    An autonomous agent that executes one sub-task.

    Lifecycle:
    1. Retrieve upstream context from StateManager.
    2. Build user message with injected context + task description.
    3. Call LLM in a tool-use loop until a final text response is produced.
    4. Write result to StateManager.
    5. Return AgentOutput.
    """

    def __init__(
        self,
        agent_spec: AgentSpec,
        sub_task: SubTask,
        tool_registry: ToolRegistry,
        state_manager: "StateManager",
        config: "HydraConfig",
    ) -> None:
        self.agent_spec = agent_spec
        self.sub_task = sub_task
        self.tool_registry = tool_registry
        self.state_manager = state_manager
        self.config = config

        # Build tool schemas for this agent's assigned tools
        self.tool_schemas = tool_registry.get_schemas_for(agent_spec.tools_needed)

        # Build system prompt
        self.system_prompt = _build_system_prompt(agent_spec, self.tool_schemas)

        self._log = logger.bind(
            agent_id=agent_spec.agent_id,
            sub_task_id=agent_spec.sub_task_id,
        )

    # ── Public interface ──────────────────────────────────────────────────────

    async def execute(self, extra_context: str = "") -> AgentOutput:
        """Execute the agent and return its output."""
        start_ms = int(time.monotonic() * 1000)
        self._log.info("agent_starting", role=self.agent_spec.role)

        # 1. Inject upstream context
        upstream_context = await self.state_manager.get_upstream_context(
            self.agent_spec.sub_task_id,
            self.sub_task.dependencies,
        )

        # 2. Build user message
        user_message = self._build_user_message(upstream_context, extra_context)

        # 3. Tool-use loop
        try:
            final_text, tokens_used = await self._run_tool_loop(user_message)
        except Exception as exc:
            self._log.error("agent_execution_failed", error=str(exc))
            elapsed = int(time.monotonic() * 1000) - start_ms
            output = AgentOutput(
                agent_id=self.agent_spec.agent_id,
                sub_task_id=self.agent_spec.sub_task_id,
                status=AgentStatus.FAILED,
                error=str(exc),
                execution_time_ms=elapsed,
            )
            await self.state_manager.write_output(self.agent_spec.sub_task_id, output)
            return output

        # 4. Parse output if schema is declared
        parsed_output = self._parse_output(final_text)

        elapsed = int(time.monotonic() * 1000) - start_ms
        output = AgentOutput(
            agent_id=self.agent_spec.agent_id,
            sub_task_id=self.agent_spec.sub_task_id,
            status=AgentStatus.COMPLETED,
            output=parsed_output,
            tokens_used=tokens_used,
            execution_time_ms=elapsed,
        )

        # 5. Write to state
        await self.state_manager.write_output(self.agent_spec.sub_task_id, output)
        # Also store full output in shared memory for memory_retrieve tool access
        await self.state_manager.write_shared(self.agent_spec.sub_task_id, parsed_output)

        self._log.info(
            "agent_completed",
            tokens_used=tokens_used,
            elapsed_ms=elapsed,
        )
        return output

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_user_message(self, upstream_context: str, extra_context: str) -> str:
        """Assemble the user message with injected context and task description."""
        parts: list[str] = []

        if upstream_context:
            parts.append(f"## Previous results from upstream tasks:\n{upstream_context}")

        if extra_context:
            parts.append(f"## Additional context:\n{extra_context}")

        parts.append(f"## Your task:\n{self.sub_task.description}")

        if self.sub_task.expected_output:
            parts.append(f"## Expected output:\n{self.sub_task.expected_output}")

        return "\n\n".join(parts)

    async def _run_tool_loop(self, initial_user_message: str) -> tuple[str, int]:
        """
        Run the LLM tool-use loop.

        Returns:
            (final_text, total_tokens_used)
        """
        model = self.agent_spec.model or self.config.default_model
        messages: list[dict] = [{"role": "user", "content": initial_user_message}]
        total_tokens = 0

        # litellm call kwargs
        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": self.config.max_tokens_per_agent,
            "temperature": self.agent_spec.temperature,
        }
        if self.config.api_key:
            call_kwargs["api_key"] = self.config.api_key
        if self.config.api_base:
            call_kwargs["api_base"] = self.config.api_base
        if self.tool_schemas:
            call_kwargs["tools"] = self.tool_schemas
            call_kwargs["tool_choice"] = "auto"

        # Also pass system via messages for providers that don't support top-level system
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})

        last_assistant_content: str = ""  # Track last assistant text response separately

        for iteration in range(_MAX_TOOL_ITERATIONS):
            self._log.debug("llm_call", iteration=iteration, message_count=len(messages))

            response = await litellm.acompletion(**call_kwargs)

            # Track token usage
            if response.usage:
                total_tokens += getattr(response.usage, "total_tokens", 0) or (
                    getattr(response.usage, "prompt_tokens", 0)
                    + getattr(response.usage, "completion_tokens", 0)
                )

            choice = response.choices[0]
            message = choice.message

            # Track the last assistant text content for use if max iterations is hit
            if message.content:
                last_assistant_content = message.content

            # Append the assistant message to history.
            # Allow content=None (don't coerce to "") so the message accurately reflects
            # the LLM response — some providers return None when only tool_calls are present.
            messages.append({
                "role": "assistant",
                "content": message.content,  # May be None; that's valid per OpenAI spec
                "tool_calls": getattr(message, "tool_calls", None),
            })

            # Check if any tool calls were requested
            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                # No more tool calls — this is the final answer
                final_text = message.content or ""
                self._log.debug("tool_loop_done", iterations=iteration + 1)
                return final_text, total_tokens

            # Execute each requested tool call
            tool_results = await self._execute_tool_calls(tool_calls)
            messages.extend(tool_results)

            # Update the call kwargs messages reference
            call_kwargs["messages"] = messages

        # Exceeded max iterations — return the last substantive assistant text,
        # not messages[-1] which would be a tool result message.
        self._log.warning("max_tool_iterations_reached", max=_MAX_TOOL_ITERATIONS)
        return last_assistant_content or "Max tool iterations reached without final answer.", total_tokens

    async def _execute_tool_calls(self, tool_calls: list) -> list[dict]:
        """Execute a list of tool calls and return tool result messages."""
        result_messages = []

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            try:
                raw_args = tool_call.function.arguments
                kwargs = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError as exc:
                kwargs = {}
                self._log.warning("tool_args_parse_failed", tool=tool_name, error=str(exc))

            self._log.info("tool_executing", tool=tool_name, args=list(kwargs.keys()))

            tool = self.tool_registry.get(tool_name)
            if tool is None:
                result = ToolResult(
                    success=False,
                    error=f"Tool '{tool_name}' not found in registry.",
                )
            else:
                try:
                    result = await tool.execute(**kwargs)
                except Exception as exc:
                    self._log.error("tool_execution_exception", tool=tool_name, error=str(exc))
                    result = ToolResult(success=False, error=f"Tool '{tool_name}' raised an exception: {exc}")

            self._log.debug("tool_result", tool=tool_name, success=result.success)

            # Format as OpenAI/litellm tool result message
            content = json.dumps({"success": result.success, "data": result.data, "error": result.error})
            result_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": content,
            })

        return result_messages

    def _parse_output(self, text: str) -> Any:
        """Try to parse the output as JSON if a schema is declared, otherwise return raw text."""
        if not self.agent_spec.output_schema:
            return text

        # Try to extract JSON from the response
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block within the text
        import re
        json_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Return raw text if all parsing fails
        self._log.warning("output_json_parse_failed", text_preview=text[:200])
        return text
