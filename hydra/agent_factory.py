"""
Agent Factory — instantiates Agent objects from a TaskPlan.
"""

from __future__ import annotations

import structlog

from hydra.agent import Agent
from hydra.config import HydraConfig
from hydra.models import AgentSpec, SubTask, TaskPlan
from hydra.state_manager import StateManager
from hydra.tool_registry import ToolRegistry
from hydra.tools.memory_tools import MemoryRetrieveTool, MemoryStoreTool
from hydra.tools.file_tools import WriteMarkdownTool, WriteJsonTool, WriteCsvTool, WriteCodeTool
from hydra.tools.document_tools import WriteDocxTool, WriteXlsxTool, WritePptxTool
from hydra.tools.data_tools import ChartGeneratorTool

logger = structlog.get_logger(__name__)


class AgentFactory:
    """
    Creates Agent instances from a TaskPlan.

    - Validates that all tools_needed exist in the registry.
    - Injects the StateManager into memory tools.
    - Registers agent roles in StateManager for richer context injection.
    - Returns a mapping of sub_task_id → Agent.
    """

    def __init__(
        self,
        config: HydraConfig,
        tool_registry: ToolRegistry,
        state_manager: StateManager,
    ) -> None:
        self.config = config
        self.tool_registry = tool_registry
        self.state_manager = state_manager

    def create_agents(self, plan: TaskPlan) -> dict[str, Agent]:
        """
        Instantiate agents for all sub-tasks in the plan.

        Returns:
            dict mapping sub_task_id → Agent
        """
        # Index sub-tasks by ID for quick lookup
        sub_task_index: dict[str, SubTask] = {st.id: st for st in plan.sub_tasks}

        agents: dict[str, Agent] = {}
        for spec in plan.agent_specs:
            sub_task = sub_task_index.get(spec.sub_task_id)
            if sub_task is None:
                raise ValueError(
                    f"AgentSpec '{spec.agent_id}' references unknown sub_task_id '{spec.sub_task_id}'. "
                    f"Available sub-task IDs: {sorted(sub_task_index.keys())}"
                )

            self._validate_tools(spec)

            # Build a per-agent tool registry with fresh memory tool instances
            # injected with the correct state_manager. We do NOT mutate the shared
            # singleton tool instances in self.tool_registry, as that would introduce
            # shared mutable state across concurrent agents.
            per_agent_registry = self._build_per_agent_registry(spec)

            # Register role in StateManager for context injection labelling
            self.state_manager.register_role(spec.sub_task_id, spec.role)

            agent = Agent(
                agent_spec=spec,
                sub_task=sub_task,
                tool_registry=per_agent_registry,
                state_manager=self.state_manager,
                config=self.config,
            )
            agents[spec.sub_task_id] = agent
            logger.debug(
                "agent_created",
                agent_id=spec.agent_id,
                sub_task_id=spec.sub_task_id,
                tools=spec.tools_needed,
            )

        logger.info("agents_created", count=len(agents))
        return agents

    # ── Private ───────────────────────────────────────────────────────────────

    def _validate_tools(self, spec: AgentSpec) -> None:
        """Raise ValueError if any tool in tools_needed is not registered."""
        missing = [t for t in spec.tools_needed if t not in self.tool_registry]
        if missing:
            available = self.tool_registry.list_names()
            raise ValueError(
                f"AgentSpec '{spec.agent_id}' requires unknown tools: {missing}. "
                f"Available tools: {available}"
            )

    def _build_per_agent_registry(self, spec: AgentSpec) -> ToolRegistry:
        """
        Build a per-agent ToolRegistry.

        For memory tools, create fresh instances with the correct state_manager
        so that each agent gets isolated, properly-wired memory tool instances.
        All other tools are reused from the shared registry (they are stateless).
        """
        per_agent = ToolRegistry()

        # Tools that need per-agent instantiation with state_manager injected.
        # Memory tools store/retrieve shared context; file tools register generated files.
        # We do NOT mutate shared singleton instances — fresh copies are created per agent.
        memory_tool_factories: dict[str, type] = {
            "memory_store": MemoryStoreTool,
            "memory_retrieve": MemoryRetrieveTool,
        }
        # File tools also need state_manager to call register_file().
        # We additionally carry over the output_dir from the shared registry instance.
        file_tool_classes: dict[str, type] = {
            "write_markdown": WriteMarkdownTool,
            "write_json": WriteJsonTool,
            "write_csv": WriteCsvTool,
            "write_code": WriteCodeTool,
            # Document tools — same pattern: inject state_manager + preserve output_dir
            "write_docx": WriteDocxTool,
            "write_xlsx": WriteXlsxTool,
            "write_pptx": WritePptxTool,
            # Chart generator also registers output files
            "generate_chart": ChartGeneratorTool,
        }

        for tool_name in spec.tools_needed:
            if tool_name in memory_tool_factories:
                # Create a fresh instance with the state_manager injected
                fresh_tool = memory_tool_factories[tool_name](state_manager=self.state_manager)
                per_agent.register(fresh_tool)
            elif tool_name in file_tool_classes:
                # Create a fresh instance preserving output_dir from the shared registry
                existing = self.tool_registry.get(tool_name)
                output_dir = existing._output_dir if existing is not None else "./hydra_output"
                fresh_tool = file_tool_classes[tool_name](
                    output_dir=output_dir,
                    state_manager=self.state_manager,
                )
                per_agent.register(fresh_tool)
            else:
                existing = self.tool_registry.get(tool_name)
                if existing is not None:
                    per_agent.register(existing)

        return per_agent
