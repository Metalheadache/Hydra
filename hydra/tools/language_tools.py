"""
Language processing tools: translation and summarization via LLM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from hydra.models import ToolResult
from hydra.tools.base import BaseTool

if TYPE_CHECKING:
    from hydra.config import HydraConfig

logger = structlog.get_logger(__name__)


async def _make_litellm_call(
    model: str,
    api_key: str,
    api_base: str | None,
    prompt: str,
    max_tokens: int = 4096,
) -> str:
    """Make a focused single-turn LLM call via litellm. Returns the text response."""
    import litellm

    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    return response.choices[0].message.content or ""


def _get_model_params(config) -> tuple[str, str, str | None]:
    """Return (model, api_key, api_base) from config or environment variables."""
    if config is not None:
        return config.default_model, config.api_key, config.api_base
    import os
    model = os.environ.get("HYDRA_DEFAULT_MODEL", "anthropic/claude-sonnet-4-6")
    api_key = os.environ.get("HYDRA_API_KEY", "")
    api_base = os.environ.get("HYDRA_API_BASE") or None
    return model, api_key, api_base


# ── TranslationTool ───────────────────────────────────────────────────────────

class TranslationTool(BaseTool):
    """Translate text between languages using an LLM."""

    name = "translate_text"
    description = (
        "Translate text from one language to another using an LLM. "
        "Source language can be 'auto-detect'. "
        "Returns only the translated text."
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to translate.",
            },
            "target_language": {
                "type": "string",
                "description": "Target language (e.g. 'English', 'Chinese', 'Spanish', 'French').",
            },
            "source_language": {
                "type": "string",
                "description": "Source language. Defaults to 'auto-detect'.",
                "default": "auto-detect",
            },
        },
        "required": ["text", "target_language"],
    }

    def __init__(self, config: "HydraConfig | None" = None) -> None:
        self._config = config

    async def execute(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto-detect",
    ) -> ToolResult:
        if not text.strip():
            return ToolResult(success=False, error="text cannot be empty")
        if not target_language.strip():
            return ToolResult(success=False, error="target_language cannot be empty")

        try:
            model, api_key, api_base = _get_model_params(self._config)
            if source_language == "auto-detect":
                prompt = (
                    f"Translate the following text to {target_language}. "
                    "Return ONLY the translation, with no extra commentary or explanation.\n\n"
                    f"<text_to_translate>\n{text}\n</text_to_translate>"
                )
            else:
                prompt = (
                    f"Translate the following text from {source_language} to {target_language}. "
                    "Return ONLY the translation, with no extra commentary or explanation.\n\n"
                    f"<text_to_translate>\n{text}\n</text_to_translate>"
                )

            translation = await _make_litellm_call(model, api_key, api_base, prompt, max_tokens=2048)
            logger.info(
                "translation_done",
                source=source_language,
                target=target_language,
                input_chars=len(text),
                output_chars=len(translation),
            )
            return ToolResult(
                success=True,
                data={
                    "translation": translation,
                    "source_language": source_language,
                    "target_language": target_language,
                },
            )

        except Exception as exc:
            logger.error("translation_failed", error=str(exc))
            return ToolResult(success=False, error=f"Translation failed: {exc}")


# ── SummarizerTool ────────────────────────────────────────────────────────────

class SummarizerTool(BaseTool):
    """Summarize text using an LLM."""

    name = "summarize_text"
    description = (
        "Summarize text using an LLM. "
        "Control output length (e.g. '3 sentences', '200 words') and style "
        "('bullet_points', 'paragraph', 'executive_summary'). "
        "Returns the summary."
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to summarize.",
            },
            "max_length": {
                "type": "string",
                "description": "Desired output length, e.g. '3 sentences', '200 words', '1 paragraph'. Optional.",
            },
            "style": {
                "type": "string",
                "enum": ["bullet_points", "paragraph", "executive_summary"],
                "description": "Output style. Defaults to 'paragraph'.",
                "default": "paragraph",
            },
        },
        "required": ["text"],
    }

    def __init__(self, config: "HydraConfig | None" = None) -> None:
        self._config = config

    async def execute(
        self,
        text: str,
        max_length: str | None = None,
        style: str = "paragraph",
    ) -> ToolResult:
        if not text.strip():
            return ToolResult(success=False, error="text cannot be empty")

        style_instructions = {
            "bullet_points": "Format the summary as a bulleted list of key points.",
            "paragraph": "Write the summary as a concise paragraph.",
            "executive_summary": (
                "Write an executive summary: start with the key takeaway, "
                "followed by supporting points."
            ),
        }
        style_instruction = style_instructions.get(style, style_instructions["paragraph"])

        length_instruction = ""
        if max_length:
            length_instruction = f" Keep the summary to approximately {max_length}."

        try:
            model, api_key, api_base = _get_model_params(self._config)
            prompt = (
                f"Summarize the following text. {style_instruction}{length_instruction} "
                "Return ONLY the summary, with no preamble or extra commentary.\n\n"
                f"<text_to_summarize>\n{text}\n</text_to_summarize>"
            )

            summary = await _make_litellm_call(model, api_key, api_base, prompt, max_tokens=4096)
            logger.info(
                "summarization_done",
                style=style,
                input_chars=len(text),
                output_chars=len(summary),
            )
            return ToolResult(
                success=True,
                data={
                    "summary": summary,
                    "style": style,
                    "max_length": max_length,
                },
            )

        except Exception as exc:
            logger.error("summarization_failed", error=str(exc))
            return ToolResult(success=False, error=f"Summarization failed: {exc}")
