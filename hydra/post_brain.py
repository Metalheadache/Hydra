"""
Post-Brain (Synthesizer) — quality gate + LLM quality scoring + final synthesis.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

import jsonschema
import litellm
import structlog

from hydra.models import AgentOutput, AgentStatus, TaskPlan

if TYPE_CHECKING:
    from hydra.audit import AuditLogger
    from hydra.config import HydraConfig
    from hydra.events import EventBus
    from hydra.state_manager import StateManager

logger = structlog.get_logger(__name__)



class PostBrain:
    """
    Runs after all agents have executed:

    1. Quality gate (programmatic): checks all critical tasks completed, validates schemas.
    2. LLM quality scoring: calls LLM to score each agent output 1-10 and flag low-quality outputs.
    3. Synthesis (LLM call): merges all outputs into a coherent final deliverable.
    4. Returns a final result dict with metadata and list of agents needing retry.
    """

    def __init__(
        self,
        config: "HydraConfig",
        state_manager: "StateManager",
        plan: TaskPlan,
        event_bus: "EventBus | None" = None,
        audit_logger: "AuditLogger | None" = None,
    ) -> None:
        self.config = config
        self.state_manager = state_manager
        self.plan = plan
        self.event_bus = event_bus
        self.audit_logger = audit_logger
        self._scoring_semaphore = asyncio.Semaphore(3)

    async def synthesize(self) -> dict:
        """
        Run the quality gate, LLM quality scoring, and synthesis pipeline.

        Returns:
            A dict containing:
            - output: the synthesized final answer
            - warnings: list of quality issues
            - execution_summary: token/time stats
            - files_generated: list of files created
            - per_agent_quality: per-agent quality notes
            - agents_needing_retry: list of sub_task_ids with quality score below threshold
        """
        start = time.monotonic()
        logger.info("post_brain_starting")

        all_outputs = await self.state_manager.get_all_outputs()
        warnings: list[str] = []
        per_agent_quality: dict[str, Any] = {}

        # ── 1. Quality gate (programmatic) ────────────────────────────────────
        gate_warnings = self._run_quality_gate(all_outputs)
        warnings.extend(gate_warnings)

        # ── 2. LLM quality scoring ────────────────────────────────────────────
        if self.event_bus:
            from hydra.events import EventType, HydraEvent
            await self.event_bus.emit(HydraEvent(
                type=EventType.QUALITY_START,
                data={"agents_to_score": len(all_outputs)},
            ))

        agents_needing_retry = await self._run_quality_scoring(all_outputs)
        for sub_task_id in agents_needing_retry:
            warnings.append(
                f"Sub-task '{sub_task_id}' scored below quality threshold "
                f"(min={self.config.min_quality_score}) and is flagged for retry."
            )
            if self.event_bus:
                from hydra.events import EventType, HydraEvent
                await self.event_bus.emit(HydraEvent(
                    type=EventType.QUALITY_RETRY,
                    sub_task_id=sub_task_id,
                    data={"reason": "score_below_threshold"},
                ))

        # ── 3. Synthesis (LLM) ────────────────────────────────────────────────
        synthesis_input = self._format_outputs_for_synthesis(all_outputs)
        final_output = await self._synthesize_with_llm(synthesis_input)

        # ── 4. Gather metadata ────────────────────────────────────────────────
        execution_summary = await self.state_manager.get_execution_summary()
        execution_summary["post_brain_time_ms"] = int((time.monotonic() - start) * 1000)
        files = await self.state_manager.get_all_files()

        # Re-read outputs to include updated quality_scores
        all_outputs = await self.state_manager.get_all_outputs()
        for sub_task_id, output in all_outputs.items():
            # Look up agent role from the plan
            role = sub_task_id
            for st in self.plan.sub_tasks:
                if st.id == sub_task_id:
                    role = st.agent.role if st.agent else sub_task_id
                    break
            per_agent_quality[sub_task_id] = {
                "role": role,
                "status": output.status,
                "output": str(output.output)[:2000] if output.output else None,
                "tokens_used": output.tokens_used,
                "execution_time_ms": output.execution_time_ms,
                "quality_score": output.quality_score,

                "error": output.error,
            }

        logger.info("post_brain_done", warnings=len(warnings), agents_needing_retry=agents_needing_retry)

        return {
            "output": final_output,
            "warnings": warnings,
            "execution_summary": execution_summary,
            "files_generated": list(files.values()),
            "per_agent_quality": per_agent_quality,
            "agents_needing_retry": agents_needing_retry,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _run_quality_gate(self, all_outputs: dict[str, AgentOutput]) -> list[str]:
        """Run programmatic quality checks. Returns a list of warning strings."""
        warnings: list[str] = []

        # Index sub-tasks by ID
        sub_task_index = {st.id: st for st in self.plan.sub_tasks}

        for sub_task_id, output in all_outputs.items():
            sub_task = sub_task_index.get(sub_task_id)
            if sub_task is None:
                continue

            # Check critical task completion
            if sub_task.priority.value == "critical" and output.status != AgentStatus.COMPLETED:
                msg = f"CRITICAL sub-task '{sub_task_id}' did not complete (status: {output.status})."
                warnings.append(msg)
                logger.warning("quality_gate_critical_failure", sub_task_id=sub_task_id)

            # Check failed tasks
            if output.status == AgentStatus.FAILED:
                warnings.append(
                    f"Sub-task '{sub_task_id}' FAILED: {output.error or 'unknown error'}"
                )

            # Validate output against declared schema
            if output.status == AgentStatus.COMPLETED and sub_task.output_schema and output.output:
                schema_errors = self._validate_schema(output.output, sub_task.output_schema)
                if schema_errors:
                    warnings.append(
                        f"Sub-task '{sub_task_id}' output failed schema validation: {schema_errors}"
                    )

        return warnings

    async def _run_quality_scoring(self, all_outputs: dict[str, AgentOutput]) -> list[str]:
        """
        Stage 2: LLM quality scoring.

        Scores all completed agent outputs **in parallel** via asyncio.gather().
        Populates AgentOutput.quality_score in StateManager.
        Returns list of sub_task_ids that scored below config.min_quality_score
        AND are eligible for retry.
        """
        sub_task_index = {st.id: st for st in self.plan.sub_tasks}
        agent_spec_index = {spec.sub_task_id: spec for spec in self.plan.agent_specs}

        # Collect sub_task_ids eligible for scoring (completed only)
        scorable: list[str] = [
            sub_task_id
            for sub_task_id, output in all_outputs.items()
            if output.status == AgentStatus.COMPLETED and sub_task_index.get(sub_task_id) is not None
        ]

        if not scorable:
            return []

        async def _score_with_semaphore(sub_task_id: str):
            async with self._scoring_semaphore:
                return await self._score_single_output(
                    sub_task_id=sub_task_id,
                    output=all_outputs[sub_task_id],
                    sub_task_index=sub_task_index,
                    agent_spec_index=agent_spec_index,
                )

        # Run all scoring coroutines in parallel (semaphore limits concurrency to 3)
        scores = await asyncio.gather(
            *[_score_with_semaphore(sub_task_id) for sub_task_id in scorable]
        )

        # Map results back and determine retry candidates
        agents_needing_retry: list[str] = []
        for sub_task_id, (score, _feedback) in zip(scorable, scores):
            sub_task = sub_task_index[sub_task_id]
            if score < self.config.min_quality_score and sub_task.retry_allowed:
                agents_needing_retry.append(sub_task_id)
                logger.warning(
                    "quality_below_threshold",
                    sub_task_id=sub_task_id,
                    score=score,
                    threshold=self.config.min_quality_score,
                )

        return agents_needing_retry

    async def _score_single_output(
        self,
        sub_task_id: str,
        output: AgentOutput,
        sub_task_index: dict,
        agent_spec_index: dict,
    ) -> tuple[float, str]:
        """Score a single agent output and persist the score. Returns (score, feedback)."""
        sub_task = sub_task_index[sub_task_id]
        spec = agent_spec_index.get(sub_task_id)

        score, feedback = await self._score_output(
            task_description=sub_task.description,
            expected_output=sub_task.expected_output,
            actual_output=str(output.output or ""),
            role=spec.role if spec else sub_task_id,
        )

        # Persist the score back to the output
        output.quality_score = score
        await self.state_manager.write_output(sub_task_id, output)

        logger.info(
            "quality_scored",
            sub_task_id=sub_task_id,
            score=score,
            feedback=feedback[:100] if feedback else "",
        )

        if self.audit_logger:
            self.audit_logger.log_quality_score(
                agent_id=spec.agent_id if spec else sub_task_id,
                sub_task_id=sub_task_id,
                score=score,
                feedback=feedback,
            )

        if self.event_bus:
            from hydra.events import EventType, HydraEvent
            await self.event_bus.emit(HydraEvent(
                type=EventType.QUALITY_SCORE,
                sub_task_id=sub_task_id,
                data={"score": score, "feedback": feedback},
            ))

        return score, feedback

    async def _score_output(
        self,
        task_description: str,
        expected_output: str,
        actual_output: str,
        role: str,
    ) -> tuple[float, str]:
        """
        Call the LLM to score an agent output on a 1-10 scale.

        Returns:
            (score, feedback) tuple. On failure, returns (5.0, "scoring failed").
        """
        system_prompt = (
            "You are a quality evaluator for AI agent outputs. "
            "Given a task description, expected output, and actual output, "
            "score the quality of the actual output on a scale of 1-10.\n\n"
            "Scoring criteria:\n"
            "- 9-10: Excellent — exceeds expectations, comprehensive, accurate\n"
            "- 7-8: Good — meets expectations with minor gaps\n"
            "- 5-6: Acceptable — partially meets expectations\n"
            "- 3-4: Poor — significant gaps or inaccuracies\n"
            "- 1-2: Very poor — fails to address the task\n\n"
            "Respond with ONLY a JSON object: {\"score\": <number 1-10>, \"feedback\": \"<one sentence>\"}"
        )
        user_message = (
            f"## Agent Role\n{role}\n\n"
            f"## Task Description\n{task_description}\n\n"
            f"## Expected Output\n{expected_output}\n\n"
            f"## Actual Output\n{actual_output[:3000]}\n\n"
            "Score this output."
        )

        call_kwargs: dict = {
            "model": self.config.post_brain_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 256,
            "temperature": 0.1,
        }
        if self.config.api_key:
            call_kwargs["api_key"] = self.config.api_key
        if self.config.api_base:
            call_kwargs["api_base"] = self.config.api_base

        try:
            response = await litellm.acompletion(**call_kwargs)
            raw = response.choices[0].message.content or ""

            # Parse JSON response
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Try to find JSON in the response
                import re
                match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                else:
                    raise ValueError(f"No JSON found in scoring response: {raw[:200]}")

            score = float(data.get("score", 5.0))
            # Clamp to valid range
            score = max(1.0, min(10.0, score))
            feedback = str(data.get("feedback", ""))
            return score, feedback

        except Exception as exc:
            logger.warning("quality_scoring_failed", error=str(exc))
            # Return neutral score on failure — don't block pipeline
            return 5.0, f"Scoring failed: {exc}"

    @staticmethod
    def _validate_schema(data: Any, schema: dict) -> list[str]:
        """Return a list of schema validation error messages."""
        try:
            validator = jsonschema.Draft7Validator(schema)
            return [err.message for err in validator.iter_errors(data)]
        except Exception as exc:
            return [f"Schema validation error: {exc}"]

    def _format_outputs_for_synthesis(self, all_outputs: dict[str, AgentOutput]) -> str:
        """Format all agent outputs into a string for the synthesis LLM call."""
        sub_task_index = {st.id: st for st in self.plan.sub_tasks}
        agent_spec_index = {spec.sub_task_id: spec for spec in self.plan.agent_specs}

        sections: list[str] = []
        for sub_task_id, output in all_outputs.items():
            sub_task = sub_task_index.get(sub_task_id)
            spec = agent_spec_index.get(sub_task_id)

            role = spec.role if spec else sub_task_id
            description = sub_task.description if sub_task else "N/A"
            status_label = output.status.value.upper()

            if output.status == AgentStatus.COMPLETED:
                content = str(output.output or "")
            else:
                content = f"[{status_label}] {output.error or 'No output'}"

            sections.append(
                f"### Agent: {role}\n"
                f"**Task**: {description}\n"
                f"**Status**: {status_label}\n\n"
                f"{content}"
            )

        return "\n\n---\n\n".join(sections)

    async def _synthesize_with_llm(self, synthesis_input: str) -> str:
        """Call the LLM to merge all outputs into a final deliverable."""
        system_prompt = (
            "You are a synthesis expert. You receive outputs from multiple AI agents that worked on "
            "different aspects of a complex task. Your job is to:\n"
            "1. Merge all outputs into a single, coherent, well-structured response.\n"
            "2. Deduplicate any overlapping information.\n"
            "3. Resolve any contradictions (note them if they cannot be resolved).\n"
            "4. Produce a comprehensive final deliverable that answers the original task.\n"
            "5. Use clear formatting with headers and sections.\n\n"
            "Be comprehensive but concise. Cite specific agent outputs when relevant."
        )

        user_message = (
            f"## Original Task\n{self.plan.original_task}\n\n"
            f"## Agent Outputs\n{synthesis_input}\n\n"
            "## Instructions\n"
            "Synthesize all the above into a single, comprehensive final answer. "
            "Structure it clearly with appropriate headers and sections."
        )

        call_kwargs: dict = {
            "model": self.config.post_brain_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.config.max_tokens_synthesis,
            "temperature": 0.3,
        }
        if self.config.api_key:
            call_kwargs["api_key"] = self.config.api_key
        if self.config.api_base:
            call_kwargs["api_base"] = self.config.api_base

        if self.event_bus:
            from hydra.events import EventType, HydraEvent
            await self.event_bus.emit(HydraEvent(
                type=EventType.SYNTHESIS_START,
                data={},
            ))

        try:
            synth_start_ms = int(time.monotonic() * 1000)
            synth_tokens_in = 0
            synth_tokens_out = 0
            if self.event_bus:
                # ── Streaming path (event_bus exists) ────────────────────────
                stream_kwargs = dict(call_kwargs)
                stream_kwargs["stream"] = True
                raw_response = await litellm.acompletion(**stream_kwargs)

                content_parts: list[str] = []
                usage_info = None
                async for chunk in raw_response:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        content_parts.append(delta.content)
                        from hydra.events import EventType, HydraEvent
                        await self.event_bus.emit(HydraEvent(
                            type=EventType.SYNTHESIS_TOKEN,
                            data={"token": delta.content},
                        ))
                    # Capture usage from last chunk (some providers include it)
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage_info = chunk.usage

                final_text = "".join(content_parts)
                if usage_info:
                    synth_tokens_in = getattr(usage_info, "prompt_tokens", 0) or 0
                    synth_tokens_out = getattr(usage_info, "completion_tokens", 0) or 0
                # Fallback estimate if provider did not supply usage
                if synth_tokens_in == 0 and synth_tokens_out == 0:
                    synth_tokens_out = len(final_text) // 4  # rough chars-per-token estimate

                from hydra.events import EventType, HydraEvent
                await self.event_bus.emit(HydraEvent(
                    type=EventType.SYNTHESIS_COMPLETE,
                    data={"length": len(final_text)},
                ))
            else:
                # ── Non-streaming path (no event_bus) ────────────────────────
                raw_response = await litellm.acompletion(**call_kwargs)
                final_text = (raw_response.choices[0].message.content or "") if raw_response.choices else ""
                usage = getattr(raw_response, "usage", None)
                if usage:
                    synth_tokens_in = getattr(usage, "prompt_tokens", 0) or 0
                    synth_tokens_out = getattr(usage, "completion_tokens", 0) or 0

            synth_duration_ms = int(time.monotonic() * 1000) - synth_start_ms
            if self.audit_logger:
                self.audit_logger.log_llm_call(
                    model=self.config.post_brain_model,
                    tokens_in=synth_tokens_in,
                    tokens_out=synth_tokens_out,
                    duration_ms=synth_duration_ms,
                    agent_id="post_brain_synthesis",
                )

            return final_text
        except Exception as exc:
            logger.error("synthesis_llm_failed", error=str(exc))
            # Fallback: return the raw concatenated outputs
            return f"[Synthesis LLM call failed: {exc}]\n\n{synthesis_input}"
