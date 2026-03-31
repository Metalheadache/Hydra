"""
Tool registry — central store for all available Hydra tools.
"""

from __future__ import annotations

import structlog

from hydra.tools.base import BaseTool

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """
    Maintains a registry of available tools.

    Usage::

        registry = ToolRegistry()
        registry.register_defaults()
        tool = registry.get("web_search")
        schemas = registry.get_all_schemas()
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Register a single tool instance."""
        if tool.name in self._tools:
            logger.warning("tool_overwritten", tool_name=tool.name)
        self._tools[tool.name] = tool
        logger.debug("tool_registered", tool_name=tool.name)

    def register_many(self, tools: list[BaseTool]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def register_defaults(self, config=None) -> None:
        """Register all built-in Hydra tools.

        Args:
            config: Optional HydraConfig. When provided, file tools are configured
                    with config.output_directory so all file writes go to the
                    configured location.
        """
        # Import here to avoid circular imports at module load time
        from hydra.tools.file_tools import (
            WriteMarkdownTool,
            WriteJsonTool,
            WriteCsvTool,
            WriteCodeTool,
        )
        from hydra.tools.research_tools import WebSearchTool, WebFetchTool, HttpRequestTool
        from hydra.tools.data_tools import JsonValidatorTool, ChartGeneratorTool, DataTransformTool
        from hydra.tools.code_tools import RunPythonTool, RunShellTool
        from hydra.tools.memory_tools import MemoryStoreTool, MemoryRetrieveTool
        from hydra.tools.validation_tools import OutputValidatorTool, QualityScorerTool
        from hydra.tools.document_tools import (
            WriteDocxTool,
            WriteXlsxTool,
            WritePptxTool,
            PdfReaderTool,
        )
        from hydra.tools.language_tools import TranslationTool, SummarizerTool
        from hydra.tools.reader_tools import ReadDocxTool, ReadXlsxTool, ReadCsvTool, ReadCodeTool
        from hydra.tools.file_manager_tools import FileManagerTool, FileMoveTool, FileDeleteTool
        from hydra.tools.template_tools import TemplateRenderTool
        from hydra.tools.pdf_tools import PdfMergeTool, PdfSplitTool

        output_dir = config.output_directory if config is not None else "./hydra_output"

        self.register_many([
            # File tools
            WriteMarkdownTool(output_dir=output_dir),
            WriteJsonTool(output_dir=output_dir),
            WriteCsvTool(output_dir=output_dir),
            WriteCodeTool(output_dir=output_dir),
            # Document tools
            WriteDocxTool(output_dir=output_dir),
            WriteXlsxTool(output_dir=output_dir),
            WritePptxTool(output_dir=output_dir),
            PdfReaderTool(allowed_dirs=[output_dir]),
            # Research tools
            WebSearchTool(config=config),
            WebFetchTool(),
            HttpRequestTool(),
            # Data tools
            JsonValidatorTool(),
            ChartGeneratorTool(output_dir=output_dir),
            DataTransformTool(),
            # Code tools
            RunPythonTool(),
            RunShellTool(),
            # Memory tools
            MemoryStoreTool(),
            MemoryRetrieveTool(),
            # Validation tools
            OutputValidatorTool(),
            QualityScorerTool(),
            # Language tools
            TranslationTool(config=config),
            SummarizerTool(config=config),
            # Reader tools (output_dir for allowed_roots path validation)
            ReadDocxTool(output_dir=output_dir),
            ReadXlsxTool(output_dir=output_dir),
            ReadCsvTool(output_dir=output_dir),
            ReadCodeTool(output_dir=output_dir),
            # File management
            FileManagerTool(output_dir=output_dir),
            FileMoveTool(output_dir=output_dir),
            FileDeleteTool(output_dir=output_dir),
            # Templates
            TemplateRenderTool(output_dir=output_dir),
            # PDF operations
            PdfMergeTool(output_dir=output_dir),
            PdfSplitTool(output_dir=output_dir),
        ])
        logger.info("default_tools_registered", count=len(self._tools))

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get(self, name: str) -> BaseTool | None:
        """Retrieve a tool by name, or None if not found."""
        return self._tools.get(name)

    def get_or_raise(self, name: str) -> BaseTool:
        """Retrieve a tool by name, raising KeyError if not found."""
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found in registry. Available: {self.list_names()}")
        return tool

    def list_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def get_all_schemas(self) -> list[dict]:
        """Return litellm-compatible schemas for all registered tools."""
        return [tool.get_schema() for tool in self._tools.values()]

    def get_schemas_for(self, tool_names: list[str]) -> list[dict]:
        """Return litellm-compatible schemas for a subset of tools."""
        schemas = []
        for name in tool_names:
            tool = self._tools.get(name)
            if tool is None:
                logger.warning("unknown_tool_requested", tool_name=name)
                continue
            schemas.append(tool.get_schema())
        return schemas

    def get_tool_descriptions(self) -> str:
        """Return a human-readable summary of all tools for the Brain prompt."""
        lines = []
        for tool in self._tools.values():
            lines.append(f"- **{tool.name}**: {tool.description}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
