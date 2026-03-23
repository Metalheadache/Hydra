"""
Data processing and validation tools.
"""

from __future__ import annotations

import json

import jsonschema
import structlog

from hydra.models import ToolResult
from hydra.tools.base import BaseTool

logger = structlog.get_logger(__name__)


class JsonValidatorTool(BaseTool):
    """Validate JSON data against a JSON Schema and return any errors."""

    name = "json_validator"
    description = (
        "Validate JSON data against a JSON Schema. "
        "Returns a list of validation errors (empty list means the data is valid)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "data": {
                "description": "The JSON data to validate (can be any JSON value).",
            },
            "schema": {
                "type": "object",
                "description": "The JSON Schema to validate against.",
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
            logger.debug("json_validation_done", is_valid=is_valid, error_count=len(errors))
            return ToolResult(
                success=True,
                data={
                    "valid": is_valid,
                    "errors": errors,
                    "error_count": len(errors),
                },
            )
        except jsonschema.SchemaError as exc:
            return ToolResult(success=False, error=f"Invalid JSON Schema provided: {exc.message}")
        except Exception as exc:
            logger.error("json_validator_failed", error=str(exc))
            return ToolResult(success=False, error=f"Validation failed unexpectedly: {exc}")
