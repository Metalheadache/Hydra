"""
Abstract base class for all Hydra tools.
Every tool must inherit from BaseTool and implement execute().
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from hydra_agents.models import ToolResult


class BaseTool(ABC):
    """
    Base class for all Hydra tools.

    Subclasses must define:
    - name:        unique tool identifier
    - description: human-readable description for the LLM
    - parameters:  JSON Schema dict for the tool's input parameters
    """

    name: str
    description: str
    parameters: dict          # JSON Schema for input parameters
    requires_confirmation: bool = False
    timeout_seconds: int = 30

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given keyword arguments.

        Must never raise exceptions — catch all errors and return
        ToolResult(success=False, error="...") instead.
        """

    def get_schema(self) -> dict:
        """Return a litellm/OpenAI tool-use compatible schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def get_anthropic_schema(self) -> dict:
        """Return an Anthropic tool_use compatible schema (legacy support)."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def __repr__(self) -> str:
        return f"<Tool name={self.name!r}>"
