"""
Pydantic v2 data models for Hydra framework.
These are the contracts between every component.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Priority(str, Enum):
    """Priority levels for sub-tasks."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class AgentStatus(str, Enum):
    """Lifecycle status of an agent."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class SubTask(BaseModel):
    """A single unit of work within a larger task plan."""
    id: str = Field(default_factory=lambda: f"st_{uuid.uuid4().hex[:8]}")
    description: str
    expected_output: str           # Description of what this sub-task should produce
    output_schema: dict | None = None  # JSON Schema for output validation
    dependencies: list[str] = []   # IDs of sub-tasks that must complete first
    priority: Priority = Priority.NORMAL
    estimated_tokens: int = 2000
    retry_allowed: bool = True
    max_retries: int = 2


class AgentSpec(BaseModel):
    """Specification for an AI agent that handles a single sub-task."""
    agent_id: str = Field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:8]}")
    sub_task_id: str               # Which sub-task this agent handles
    role: str                      # e.g. "Senior market analyst specializing in Chinese telecom AI"
    goal: str                      # Specific goal for this agent
    backstory: str                 # Persona framing for the LLM
    tools_needed: list[str]        # Tool names from registry
    output_schema: dict | None = None
    constraints: list[str] = []    # e.g. ["Only cite .gov.cn sources", "Max 2000 tokens"]
    temperature: float = 0.4
    model: str | None = None       # Override default model if needed


class TaskPlan(BaseModel):
    """Complete execution plan for a complex task."""
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    original_task: str
    sub_tasks: list[SubTask]
    agent_specs: list[AgentSpec]
    execution_groups: list[list[str]]  # Groups of sub-task IDs that can run in parallel


class AgentOutput(BaseModel):
    """Result produced by a single agent after executing its sub-task."""
    agent_id: str
    sub_task_id: str
    status: AgentStatus
    output: Any = None
    error: str | None = None
    tokens_used: int = 0
    execution_time_ms: int = 0
    retries_used: int = 0
    quality_score: float | None = None


class ToolResult(BaseModel):
    """Result returned by any tool execution."""
    success: bool
    data: Any = None
    error: str | None = None
