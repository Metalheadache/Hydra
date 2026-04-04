"""
Validation and quality scoring tools.
"""

from __future__ import annotations

import json

import jsonschema
import litellm
import structlog

from hydra_agents.models import ToolResult
from hydra_agents.tools.base import BaseTool

logger = structlog.get_logger(__name__)


class OutputValidatorTool(BaseTool):
    """Validate agent output data against a JSON Schema."""

    name = "output_validator"
    description = (
        "Validate agent output data against a JSON Schema. "
        "Returns whether the data is valid and any validation errors."
    )
    parameters = {
        "type": "object",
        "properties": {
            "data": {
                "description": "Data to validate.",
            },
            "schema": {
                "type": "object",
                "description": "JSON Schema to validate against.",
            },
        },
        "required": ["data", "schema"],
    }

    async def execute(self, data, schema: dict) -> ToolResult:
        try:
            validator = jsonschema.Draft7Validator(schema)
            errors = [
                {"path": " > ".join(str(p) for p in err.path), "message": err.message}
                for err in validator.iter_errors(data)
            ]
            is_valid = len(errors) == 0
            return ToolResult(
                success=True,
                data={"valid": is_valid, "errors": errors, "error_count": len(errors)},
            )
        except Exception as exc:
            logger.error("output_validator_failed", error=str(exc))
            return ToolResult(success=False, error=f"Validation error: {exc}")


class QualityScorerTool(BaseTool):
    """Use an LLM to score the quality of agent output on a 1-10 scale."""

    name = "quality_scorer"
    description = (
        "Score the quality of an agent's output using an LLM. "
        "Returns a score from 1-10 and brief feedback. Useful in quality gates."
    )
    parameters = {
        "type": "object",
        "properties": {
            "output": {
                "type": "string",
                "description": "The agent output text to evaluate.",
            },
            "task_description": {
                "type": "string",
                "description": "The original task or goal the output was meant to accomplish.",
            },
            "model": {
                "type": "string",
                "description": "litellm model string to use for scoring (e.g. 'anthropic/claude-haiku-4-6').",
                "default": "anthropic/claude-haiku-4-6",
            },
        },
        "required": ["output", "task_description"],
    }
    timeout_seconds = 30

    async def execute(self, output: str, task_description: str, model: str = "anthropic/claude-haiku-4-6") -> ToolResult:
        prompt = (
            f"You are a quality evaluator. Score the following output on a scale from 1-10.\n\n"
            f"Task: {task_description}\n\n"
            f"Output:\n{output[:3000]}\n\n"  # Truncate for cost control
            f'Respond with ONLY valid JSON: {{"score": <1-10>, "feedback": "<one sentence>"}}'
        )
        try:
            resp = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1,
            )
            raw = resp.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)
            score = float(result.get("score", 5))
            feedback = result.get("feedback", "")
            return ToolResult(success=True, data={"score": score, "feedback": feedback})
        except Exception as exc:
            logger.error("quality_scorer_failed", error=str(exc))
            return ToolResult(success=False, error=f"Quality scoring failed: {exc}")
