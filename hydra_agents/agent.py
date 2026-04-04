"""
Hydra Agent — executes a single sub-task with LLM + tool-use loop.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import TYPE_CHECKING, Any

import litellm
import structlog

from hydra_agents.models import AgentOutput, AgentSpec, AgentStatus, SubTask, ToolResult
from hydra_agents.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from hydra_agents.audit import AuditLogger
    from hydra_agents.config import HydraConfig
    from hydra_agents.events import EventBus
    from hydra_agents.state_manager import StateManager

logger = structlog.get_logger(__name__)

_MAX_TOOL_ITERATIONS = 20  # Default safety cap — overridden by config.max_tool_iterations



class _DictToolCall:
    """Lightweight wrapper that presents a dict-based tool call as an object."""

    def __init__(self, data: dict) -> None:
        self.id = data["id"]
        self.type = data.get("type", "function")
        self.function = _DictToolCallFunction(data["function"])


class _DictToolCallFunction:
    def __init__(self, data: dict) -> None:
        self.name = data.get("name", "")
        self.arguments = data.get("arguments", "")


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
        event_bus: "EventBus | None" = None,
        audit_logger: "AuditLogger | None" = None,
    ) -> None:
        self.agent_spec = agent_spec
        self.sub_task = sub_task
        self.tool_registry = tool_registry
        self.state_manager = state_manager
        self.config = config
        self.event_bus = event_bus
        self.audit_logger = audit_logger

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

        if self.event_bus:
            from hydra_agents.events import EventType, HydraEvent
            await self.event_bus.emit(HydraEvent(
                type=EventType.AGENT_START,
                agent_id=self.agent_spec.agent_id,
                sub_task_id=self.agent_spec.sub_task_id,
                data={"role": self.agent_spec.role},
            ))

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

            if self.event_bus:
                from hydra_agents.events import EventType, HydraEvent
                await self.event_bus.emit(HydraEvent(
                    type=EventType.AGENT_ERROR,
                    agent_id=self.agent_spec.agent_id,
                    sub_task_id=self.agent_spec.sub_task_id,
                    data={"error": str(exc)},
                ))

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

        if self.event_bus:
            from hydra_agents.events import EventType, HydraEvent
            await self.event_bus.emit(HydraEvent(
                type=EventType.AGENT_COMPLETE,
                agent_id=self.agent_spec.agent_id,
                sub_task_id=self.agent_spec.sub_task_id,
                tokens=tokens_used,
                # H5: include full output info for frontend token counting and display
                data={
                    "elapsed_ms": elapsed,
                    "output": str(output.output)[:500] if output.output else "",
                    "status": output.status.value,
                    "tokens_used": output.tokens_used,
                    "execution_time_ms": output.execution_time_ms,
                    "quality_score": output.quality_score,
                },
            ))

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

        max_iterations = getattr(self.config, "max_tool_iterations", _MAX_TOOL_ITERATIONS)
        for iteration in range(max_iterations):
            self._log.debug("llm_call", iteration=iteration, message_count=len(messages))

            if self.event_bus:
                # ── Streaming path (event_bus exists) ────────────────────────
                # Use stream=True to emit AGENT_TOKEN events for each chunk.
                stream_kwargs = dict(call_kwargs)
                stream_kwargs["stream"] = True
                stream_kwargs["stream_options"] = {"include_usage": True}

                llm_start_ms = int(time.monotonic() * 1000)
                stream_response = await litellm.acompletion(**stream_kwargs)

                # Collect streaming chunks
                content_parts: list[str] = []
                tool_calls_data: list[dict] = []
                usage_info = None

                async for chunk in stream_response:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta is None:
                        continue

                    # Accumulate content and emit token events
                    if delta.content:
                        content_parts.append(delta.content)
                        from hydra_agents.events import EventType, HydraEvent
                        await self.event_bus.emit(HydraEvent(
                            type=EventType.AGENT_TOKEN,
                            agent_id=self.agent_spec.agent_id,
                            sub_task_id=self.agent_spec.sub_task_id,
                            data={"token": delta.content},
                        ))

                    # Accumulate tool calls
                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index if hasattr(tc_delta, "index") else 0
                            while len(tool_calls_data) <= idx:
                                tool_calls_data.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            # Set id/name only once (first non-empty chunk wins) to avoid double-append
                            if tc_delta.id and not tool_calls_data[idx]["id"]:
                                tool_calls_data[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name and not tool_calls_data[idx]["function"]["name"]:
                                    tool_calls_data[idx]["function"]["name"] = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tool_calls_data[idx]["function"]["arguments"] += tc_delta.function.arguments

                    # Capture usage from last chunk
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage_info = chunk.usage

                # Track token usage
                llm_duration_ms = int(time.monotonic() * 1000) - llm_start_ms
                iter_tokens_in = 0
                iter_tokens_out = 0
                if usage_info:
                    iter_tokens_in = getattr(usage_info, "prompt_tokens", 0)
                    iter_tokens_out = getattr(usage_info, "completion_tokens", 0)
                    total_tokens += getattr(usage_info, "total_tokens", 0) or (
                        iter_tokens_in + iter_tokens_out
                    )
                if self.audit_logger:
                    self.audit_logger.log_llm_call(
                        model=model,
                        tokens_in=iter_tokens_in,
                        tokens_out=iter_tokens_out,
                        duration_ms=llm_duration_ms,
                        agent_id=self.agent_spec.agent_id,
                    )

                assembled_content = "".join(content_parts) or None
                if assembled_content:
                    last_assistant_content = assembled_content

                # Build tool_calls objects from accumulated data
                assembled_tool_calls = None
                if tool_calls_data:
                    assembled_tool_calls = [_DictToolCall(tc) for tc in tool_calls_data if tc["function"]["name"]]

                # Append the assistant message to history
                messages.append({
                    "role": "assistant",
                    "content": assembled_content,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]},
                        }
                        for tc in tool_calls_data
                        if tc["function"]["name"]
                    ] or None,
                })

                if not assembled_tool_calls:
                    # No more tool calls — this is the final answer
                    final_text = assembled_content or ""
                    self._log.debug("tool_loop_done", iterations=iteration + 1)
                    return final_text, total_tokens

                # Execute each requested tool call
                tool_results = await self._execute_tool_calls(assembled_tool_calls)
                messages.extend(tool_results)

            else:
                # ── Non-streaming path (no event_bus) ────────────────────────
                # Use stream=False for simplicity — no token events needed.
                llm_start_ms = int(time.monotonic() * 1000)
                raw_response = await litellm.acompletion(**call_kwargs)
                llm_duration_ms = int(time.monotonic() * 1000) - llm_start_ms

                msg = raw_response.choices[0].message if raw_response.choices else None
                content = msg.content if msg else ""
                tcs = getattr(msg, "tool_calls", None) if msg else None
                usage = getattr(raw_response, "usage", None)
                ns_tokens_in = 0
                ns_tokens_out = 0
                if usage:
                    ns_tokens_in = getattr(usage, "prompt_tokens", 0)
                    ns_tokens_out = getattr(usage, "completion_tokens", 0)
                    total_tokens += getattr(usage, "total_tokens", 0) or (
                        ns_tokens_in + ns_tokens_out
                    )
                if self.audit_logger:
                    self.audit_logger.log_llm_call(
                        model=model,
                        tokens_in=ns_tokens_in,
                        tokens_out=ns_tokens_out,
                        duration_ms=llm_duration_ms,
                        agent_id=self.agent_spec.agent_id,
                    )

                if content:
                    last_assistant_content = content

                assembled_content = content or None
                messages.append({
                    "role": "assistant",
                    "content": assembled_content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in (tcs or [])
                    ] or None,
                })

                if not tcs:
                    final_text = assembled_content or ""
                    self._log.debug("tool_loop_done", iterations=iteration + 1)
                    return final_text, total_tokens

                tool_results = await self._execute_tool_calls(tcs)
                messages.extend(tool_results)

            # Update the call kwargs messages reference
            call_kwargs["messages"] = messages

        # Exceeded max iterations — return the last substantive assistant text
        self._log.warning("max_tool_iterations_reached", max=max_iterations)
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

            if self.event_bus:
                from hydra_agents.events import EventType, HydraEvent
                await self.event_bus.emit(HydraEvent(
                    type=EventType.AGENT_TOOL_CALL,
                    agent_id=self.agent_spec.agent_id,
                    sub_task_id=self.agent_spec.sub_task_id,
                    # H5: include both 'tool' and 'tool_name' (frontend reads both);
                    # args as full dict (not just keys) for confirmation modal display
                    data={"tool": tool_name, "tool_name": tool_name, "args": kwargs},
                ))

            tool = self.tool_registry.get(tool_name)
            if tool is None:
                result = ToolResult(
                    success=False,
                    error=f"Tool '{tool_name}' not found in registry.",
                )
            else:
                # ── Confirmation gate ─────────────────────────────────────────
                # If the tool requires confirmation AND we have an event_bus,
                # pause and wait for external approval.
                if getattr(tool, "requires_confirmation", False) and self.event_bus:
                    from hydra_agents.events import EventType, HydraEvent
                    confirmation_id = str(uuid.uuid4())
                    timeout = self.config.per_agent_timeout_seconds
                    try:
                        approved = await asyncio.wait_for(
                            self.event_bus.request_confirmation(
                                confirmation_id=confirmation_id,
                                tool_name=tool_name,
                                args=kwargs,
                            ),
                            timeout=timeout,
                        )
                    except asyncio.TimeoutError:
                        self._log.warning(
                            "confirmation_timeout",
                            tool=tool_name,
                            confirmation_id=confirmation_id,
                        )
                        approved = False

                    if not approved:
                        result = ToolResult(
                            success=False,
                            error="Tool execution rejected by user",
                        )
                        self._log.info("tool_rejected", tool=tool_name)
                        if self.audit_logger:
                            self.audit_logger.log_tool_execution(
                                tool_name=tool_name,
                                args=kwargs,
                                result_success=False,
                                duration_ms=0,
                                agent_id=self.agent_spec.agent_id,
                            )
                        if self.event_bus:
                            await self.event_bus.emit(HydraEvent(
                                type=EventType.AGENT_TOOL_RESULT,
                                agent_id=self.agent_spec.agent_id,
                                sub_task_id=self.agent_spec.sub_task_id,
                                data={"tool": tool_name, "success": False, "error": result.error},
                            ))
                        content = json.dumps({"success": result.success, "data": result.data, "error": result.error})
                        result_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": content,
                        })
                        continue

                # Execute the tool
                tool_start_ms = int(time.monotonic() * 1000)
                try:
                    result = await tool.execute(**kwargs)
                except Exception as exc:
                    self._log.error("tool_execution_exception", tool=tool_name, error=str(exc))
                    result = ToolResult(success=False, error=f"Tool '{tool_name}' raised an exception: {exc}")
                tool_duration_ms = int(time.monotonic() * 1000) - tool_start_ms

                if self.audit_logger:
                    self.audit_logger.log_tool_execution(
                        tool_name=tool_name,
                        args=kwargs,
                        result_success=result.success,
                        duration_ms=tool_duration_ms,
                        agent_id=self.agent_spec.agent_id,
                    )

            self._log.debug("tool_result", tool=tool_name, success=result.success)

            if self.event_bus:
                from hydra_agents.events import EventType, HydraEvent
                await self.event_bus.emit(HydraEvent(
                    type=EventType.AGENT_TOOL_RESULT,
                    agent_id=self.agent_spec.agent_id,
                    sub_task_id=self.agent_spec.sub_task_id,
                    data={"tool": tool_name, "success": result.success, "error": result.error},
                ))

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
