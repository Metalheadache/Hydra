"""
Jinja2 template rendering tool for Hydra agents.

Uses SandboxedEnvironment to prevent template injection attacks
(blocks __import__, getattr tricks, etc).

Dependencies:
    Jinja2 >= 3.1.0  (new dependency — add to pyproject.toml)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from hydra_agents.models import ToolResult
from hydra_agents.tools._security import ensure_dir, safe_read_path, safe_write_path
from hydra_agents.tools.base import BaseTool

if TYPE_CHECKING:
    from hydra_agents.state_manager import StateManager

logger = structlog.get_logger(__name__)

_DEFAULT_OUTPUT_DIR = "./hydra_output"


class TemplateRenderTool(BaseTool):
    """Render a Jinja2 template with provided data."""

    name = "template_render"
    description = (
        "Render a Jinja2 template with provided data. Supports inline template "
        "strings or template files. Variables use {{ var }} syntax. Includes "
        "conditionals ({%% if %%}), loops ({%% for %%}), and filters "
        "(|upper, |default, |join, etc). Use for filling report templates, "
        "generating emails, config files, code scaffolds, etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "template": {
                "type": "string",
                "description": "Jinja2 template string. Mutually exclusive with template_path.",
            },
            "template_path": {
                "type": "string",
                "description": "Path to a template file (.j2, .jinja2, .txt, etc). Mutually exclusive with template.",
            },
            "data": {
                "type": "object",
                "description": "Key-value data to inject into the template.",
            },
            "output_path": {
                "type": "string",
                "description": "If provided, write rendered output to this file.",
                "default": "",
            },
            "strict": {
                "type": "boolean",
                "description": "If true, raise error on undefined variables. Default: false (undefined → empty string).",
                "default": False,
            },
        },
        "required": ["data"],
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
        data: dict,
        template: str = "",
        template_path: str = "",
        output_path: str = "",
        strict: bool = False,
    ) -> ToolResult:
        try:
            from jinja2 import BaseLoader, FileSystemLoader, StrictUndefined, Undefined
            from jinja2.sandbox import SandboxedEnvironment
        except ImportError:
            return ToolResult(
                success=False,
                error="Jinja2 is not installed. Run: pip install Jinja2>=3.1.0",
            )

        if not template and not template_path:
            return ToolResult(success=False, error="Provide either 'template' or 'template_path'")
        if template and template_path:
            return ToolResult(success=False, error="Provide 'template' or 'template_path', not both")

        try:
            env_kwargs = {
                "undefined": StrictUndefined if strict else Undefined,
                "autoescape": False,
                "keep_trailing_newline": True,
            }

            if template_path:
                path = safe_read_path(template_path, allowed_roots=[self._output_dir, Path.cwd()])
                # Restrict loader to output_dir + cwd only — prevents {% include "../../etc/passwd" %}
                allowed_dirs = [str(Path(self._output_dir).resolve()), str(Path.cwd().resolve())]
                env = SandboxedEnvironment(
                    loader=FileSystemLoader(allowed_dirs),
                    **env_kwargs,
                )
                # Load by relative path from one of the allowed dirs
                try:
                    rel = path.relative_to(Path(self._output_dir).resolve())
                except ValueError:
                    rel = path.relative_to(Path.cwd().resolve())
                tmpl = env.get_template(str(rel))
            else:
                env = SandboxedEnvironment(loader=BaseLoader(), **env_kwargs)
                tmpl = env.from_string(template)

            rendered = tmpl.render(**data)

            result: dict = {
                "rendered": rendered,
                "length": len(rendered),
                "variables_provided": list(data.keys()),
            }

            # Optionally write to file
            if output_path:
                output_dir = ensure_dir(self._output_dir)
                out = safe_write_path(output_dir, Path(output_path).name)
                if out is None:
                    return ToolResult(success=False, error="Path traversal blocked on output_path")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(rendered, encoding="utf-8")
                result["output_path"] = str(out)

                if self._state_manager is not None:
                    await self._state_manager.register_file(out.name, str(out))

            logger.info("template_render_success", output_path=output_path or "(inline)", length=len(rendered))
            return ToolResult(success=True, data=result)

        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            logger.error("template_render_failed", error=str(exc))
            return ToolResult(success=False, error=f"Template rendering failed: {exc}")
