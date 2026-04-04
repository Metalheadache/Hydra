"""
Data processing and validation tools.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema
import structlog

from hydra_agents.models import ToolResult
from hydra_agents.tools.base import BaseTool
from hydra_agents.tools.file_tools import _ensure_output_dir, _safe_filepath, _DEFAULT_OUTPUT_DIR

if TYPE_CHECKING:
    from hydra_agents.state_manager import StateManager

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


# ── ChartGeneratorTool ────────────────────────────────────────────────────────

class ChartGeneratorTool(BaseTool):
    """Generate charts (bar, line, pie, scatter) and save as PNG."""

    name = "generate_chart"
    description = (
        "Generate a chart (bar, line, pie, scatter) from data and save as a PNG image. "
        "For bar/line: data = {labels: [...], values: [...]}. "
        "For scatter: data = {x: [...], y: [...]}. "
        "For pie: data = {labels: [...], values: [...]}. "
        "Returns the filepath of the PNG."
    )
    parameters = {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["bar", "line", "pie", "scatter"],
                "description": "Type of chart to generate.",
            },
            "data": {
                "type": "object",
                "description": (
                    "Chart data. Keys: 'labels' + 'values' for bar/line/pie; "
                    "'x' + 'y' for scatter."
                ),
            },
            "title": {
                "type": "string",
                "description": "Chart title.",
            },
            "filename": {
                "type": "string",
                "description": "Output filename (e.g. 'chart.png').",
            },
            "output_dir": {
                "type": "string",
                "description": f"Directory to write the file. Defaults to '{_DEFAULT_OUTPUT_DIR}'.",
            },
        },
        "required": ["chart_type", "data", "title", "filename"],
    }

    def __init__(
        self,
        output_dir: str = _DEFAULT_OUTPUT_DIR,
        state_manager: "StateManager | None" = None,
    ) -> None:
        self._output_dir = output_dir
        self._state_manager = state_manager

    async def execute(
        self,
        chart_type: str,
        data: dict,
        title: str,
        filename: str,
        output_dir: str | None = None,
    ) -> ToolResult:
        try:
            import matplotlib
            matplotlib.use("Agg")  # non-interactive backend
            import matplotlib.pyplot as plt
        except ImportError:
            return ToolResult(success=False, error="matplotlib is not installed. Run: pip install matplotlib")

        try:
            effective_dir = output_dir if output_dir is not None else self._output_dir
            output_path = _ensure_output_dir(effective_dir)
            if not filename.endswith(".png"):
                filename += ".png"
            filepath = _safe_filepath(output_path, filename)
            if filepath is None:
                return ToolResult(success=False, error="Path traversal blocked")

            fig, ax = plt.subplots(figsize=(10, 6))
            fig.patch.set_facecolor("#FAFAFA")
            ax.set_facecolor("#FAFAFA")

            if chart_type == "bar":
                labels = data.get("labels", [])
                values = data.get("values", [])
                bars = ax.bar(labels, values, color="#2F5496", edgecolor="white", linewidth=0.8)
                ax.set_xlabel("", fontsize=11)
                ax.set_ylabel("Value", fontsize=11)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.yaxis.grid(True, linestyle="--", alpha=0.5)
                ax.set_axisbelow(True)

            elif chart_type == "line":
                labels = data.get("labels", [])
                values = data.get("values", [])
                ax.plot(labels, values, color="#2F5496", linewidth=2.5, marker="o", markersize=5)
                ax.fill_between(range(len(labels)), values, alpha=0.1, color="#2F5496")
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha="right")
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.yaxis.grid(True, linestyle="--", alpha=0.5)
                ax.set_axisbelow(True)

            elif chart_type == "pie":
                labels = data.get("labels", [])
                values = data.get("values", [])
                colors = list(plt.cm.tab20.colors)[:len(values)]
                wedges, texts, autotexts = ax.pie(
                    values,
                    labels=labels,
                    autopct="%1.1f%%",
                    colors=colors,
                    startangle=90,
                    pctdistance=0.85,
                )
                for text in autotexts:
                    text.set_fontsize(9)
                ax.axis("equal")

            elif chart_type == "scatter":
                x = data.get("x", [])
                y = data.get("y", [])
                ax.scatter(x, y, color="#2F5496", alpha=0.7, edgecolors="white", s=60)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.yaxis.grid(True, linestyle="--", alpha=0.5)
                ax.xaxis.grid(True, linestyle="--", alpha=0.5)
                ax.set_axisbelow(True)

            else:
                plt.close(fig)
                return ToolResult(success=False, error=f"Unsupported chart_type: {chart_type!r}")

            ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
            plt.tight_layout()
            plt.savefig(str(filepath), dpi=150, bbox_inches="tight")
            plt.close(fig)

            if self._state_manager is not None:
                await self._state_manager.register_file(filename, str(filepath))

            logger.info("chart_generated", filepath=str(filepath), chart_type=chart_type)
            return ToolResult(success=True, data={"filepath": str(filepath), "chart_type": chart_type})

        except Exception as exc:
            logger.error("chart_generation_failed", error=str(exc))
            try:
                plt.close("all")
            except Exception:
                pass
            return ToolResult(success=False, error=f"Failed to generate chart: {exc}")


# ── DataTransformTool ─────────────────────────────────────────────────────────

class DataTransformTool(BaseTool):
    """Transform a list of dicts using a pipeline of operations."""

    name = "data_transform"
    description = (
        "Transform tabular data (list of dicts) using a pipeline of operations: "
        "filter, sort, group_by, select, limit. Pure Python — no pandas required. "
        "Returns the transformed data."
    )
    parameters = {
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "description": "Input data as a list of dicts.",
                "items": {"type": "object"},
            },
            "operations": {
                "type": "array",
                "description": (
                    "Ordered list of operations to apply. Each operation: "
                    "{type: 'filter'|'sort'|'group_by'|'select'|'limit', params: {...}}. "
                    "filter params: {field, operator ('=='|'!='|'>'|'>='|'<'|'<='|'contains'), value}. "
                    "sort params: {field, order ('asc'|'desc')}. "
                    "group_by params: {field, agg_field, agg_func ('count'|'sum'|'avg'|'min'|'max')}. "
                    "select params: {fields: [...]}. "
                    "limit params: {count: N}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["type"],
                },
            },
        },
        "required": ["data", "operations"],
    }

    async def execute(self, data: list[dict], operations: list[dict]) -> ToolResult:
        try:
            result = list(data)  # work on a copy

            for op in operations:
                op_type = op.get("type", "").lower()
                params = op.get("params", {})

                if op_type == "filter":
                    result = self._op_filter(result, params)
                elif op_type == "sort":
                    result = self._op_sort(result, params)
                elif op_type == "group_by":
                    result = self._op_group_by(result, params)
                elif op_type == "select":
                    result = self._op_select(result, params)
                elif op_type == "limit":
                    result = self._op_limit(result, params)
                else:
                    return ToolResult(success=False, error=f"Unknown operation type: {op_type!r}")

            return ToolResult(success=True, data={"result": result, "count": len(result)})

        except Exception as exc:
            logger.error("data_transform_failed", error=str(exc))
            return ToolResult(success=False, error=f"Data transformation failed: {exc}")

    @staticmethod
    def _op_filter(data: list[dict], params: dict) -> list[dict]:
        field = params["field"]
        operator = params.get("operator", "==")
        value = params["value"]

        def _matches(row: dict) -> bool:
            row_val = row.get(field)
            if operator == "==":
                return row_val == value
            elif operator == "!=":
                return row_val != value
            elif operator == ">":
                return row_val is not None and row_val > value
            elif operator == ">=":
                return row_val is not None and row_val >= value
            elif operator == "<":
                return row_val is not None and row_val < value
            elif operator == "<=":
                return row_val is not None and row_val <= value
            elif operator == "contains":
                return value in str(row_val) if row_val is not None else False
            else:
                raise ValueError(f"Unknown operator: {operator!r}")

        return [row for row in data if _matches(row)]

    @staticmethod
    def _op_sort(data: list[dict], params: dict) -> list[dict]:
        field = params["field"]
        order = params.get("order", "asc").lower()
        reverse = order == "desc"
        return sorted(data, key=lambda row: (row.get(field) is None, row.get(field)), reverse=reverse)

    @staticmethod
    def _op_group_by(data: list[dict], params: dict) -> list[dict]:
        field = params["field"]
        agg_field = params.get("agg_field")
        agg_func = params.get("agg_func", "count").lower()

        # Validate: non-count aggregations require agg_field
        if agg_func != "count" and not agg_field:
            raise ValueError(
                f"agg_field is required when agg_func is '{agg_func}' (only 'count' works without it)"
            )

        groups: dict[Any, list] = {}
        for row in data:
            key = row.get(field)
            groups.setdefault(key, []).append(row)

        result = []
        for key, rows in groups.items():
            entry = {field: key}
            if agg_func == "count":
                entry["count"] = len(rows)
            elif agg_field:
                values = [r[agg_field] for r in rows if agg_field in r and r[agg_field] is not None]
                numeric_values = []
                for v in values:
                    try:
                        numeric_values.append(float(v))
                    except (TypeError, ValueError):
                        pass
                if agg_func == "sum":
                    entry[f"{agg_func}_{agg_field}"] = sum(numeric_values)
                elif agg_func == "avg":
                    entry[f"{agg_func}_{agg_field}"] = sum(numeric_values) / len(numeric_values) if numeric_values else None
                elif agg_func == "min":
                    entry[f"{agg_func}_{agg_field}"] = min(numeric_values) if numeric_values else None
                elif agg_func == "max":
                    entry[f"{agg_func}_{agg_field}"] = max(numeric_values) if numeric_values else None
                else:
                    raise ValueError(f"Unknown agg_func: {agg_func!r}")
            result.append(entry)
        return result

    @staticmethod
    def _op_select(data: list[dict], params: dict) -> list[dict]:
        fields = params["fields"]
        return [{f: row.get(f) for f in fields} for row in data]

    @staticmethod
    def _op_limit(data: list[dict], params: dict) -> list[dict]:
        count = int(params["count"])
        if count < 0:
            raise ValueError("limit count must be non-negative")
        return data[:count]
