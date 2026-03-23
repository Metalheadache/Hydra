# Hydra 🐍

**Dynamic Multi-Agent Orchestration Framework**

Hydra decomposes complex tasks into sub-tasks, dynamically generates specialized AI agents, executes them in a hybrid DAG (parallel + sequential), and synthesizes a coherent final result.

---

## Features

- 🧠 **Brain (Planner)** — Automatic task decomposition + agent generation via a structured LLM call
- 🤖 **Specialized Agents** — Each agent gets a tailored role, goal, backstory, and tool set
- ⚡ **Hybrid DAG Execution** — Independent tasks run in parallel; dependent tasks wait
- 🔄 **Retry + Backoff** — Failed agents retry with exponential backoff
- 🛡️ **Quality Gate** — Programmatic schema validation + LLM quality scoring
- 🔀 **Provider-Agnostic** — Works with Anthropic, OpenAI, Ollama, Azure, Gemini, and [any litellm-supported provider](https://docs.litellm.ai/docs/providers)
- 🔧 **13 Built-in Tools** — File writing, web search, web fetch, Python execution, shell commands, memory, validation

---

## Quick Start

### Install

```bash
pip install hydra-agents
# or from source:
cd hydra && pip install -e ".[dev]"
```

### Configure

```bash
cp .env.example .env
# Edit .env with your API key
```

### Run

```python
import asyncio
from hydra import Hydra

async def main():
    hydra = Hydra()
    result = await hydra.run(
        "Research the current state of AI agents and write a 3-section summary."
    )
    print(result["output"])

asyncio.run(main())
```

---

## Configuration

All settings use the `HYDRA_` environment variable prefix:

| Variable | Default | Description |
|---|---|---|
| `HYDRA_API_KEY` | `""` | Provider API key |
| `HYDRA_DEFAULT_MODEL` | `anthropic/claude-sonnet-4-6` | litellm model string |
| `HYDRA_BRAIN_MODEL` | `anthropic/claude-sonnet-4-6` | Model for task planning |
| `HYDRA_POST_BRAIN_MODEL` | `anthropic/claude-sonnet-4-6` | Model for synthesis |
| `HYDRA_API_BASE` | `None` | Custom API endpoint (Ollama, Azure, etc.) |
| `HYDRA_MAX_CONCURRENT_AGENTS` | `5` | Max parallel agents |
| `HYDRA_PER_AGENT_TIMEOUT_SECONDS` | `60` | Timeout per agent |
| `HYDRA_TOTAL_TOKEN_BUDGET` | `100000` | Abort if exceeded |
| `HYDRA_OUTPUT_DIRECTORY` | `./hydra_output` | Where files are written |
| `HYDRA_SEARCH_BACKEND` | `brave` | Web search provider |
| `HYDRA_SEARCH_API_KEY` | `""` | API key for web search |

### Provider Examples

**Anthropic:**
```bash
HYDRA_API_KEY=sk-ant-...
HYDRA_DEFAULT_MODEL=anthropic/claude-sonnet-4-6
```

**OpenAI:**
```bash
HYDRA_API_KEY=sk-...
HYDRA_DEFAULT_MODEL=gpt-4o
```

**Ollama (local):**
```bash
HYDRA_API_BASE=http://localhost:11434
HYDRA_DEFAULT_MODEL=ollama/llama3
```

**Azure OpenAI:**
```bash
HYDRA_API_KEY=<azure-key>
HYDRA_API_BASE=https://<resource>.openai.azure.com
HYDRA_DEFAULT_MODEL=azure/gpt-4o
```

---

## Architecture

```
User Task
    │
    ▼
┌─────────┐
│  Brain  │  ← Decomposes task → TaskPlan (sub-tasks + agent specs + DAG)
└────┬────┘
     │
     ▼
┌──────────────┐
│ AgentFactory │  ← Instantiates agents, injects tools + state manager
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ ExecutionEngine  │  ← DAG execution: parallel groups, retries, semaphore
│                  │
│  [Group 1: A, B] │ ← A and B run in parallel
│  [Group 2: C]    │ ← C waits for A and B
└──────┬───────────┘
       │
       ▼
┌──────────────┐
│  Post-Brain  │  ← Quality gate + LLM synthesis → final output
└──────────────┘
```

### Context Flow

Upstream agent outputs are automatically injected into downstream agents:

```
Agent A (Research) → StateManager → Agent C (Analysis)
Agent B (Research) → StateManager ↗
                                    ↓
                              Agent D (Report Writing)
```

---

## Built-in Tools

| Tool | Description |
|---|---|
| `write_markdown` | Write content to a `.md` file |
| `write_json` | Write structured data to a `.json` file |
| `write_csv` | Write tabular data to a `.csv` file |
| `write_code` | Write source code to any file type |
| `web_search` | Search the web (Brave/Tavily/SerpAPI) |
| `web_fetch` | Fetch a URL and return clean text |
| `json_validator` | Validate JSON against a schema |
| `run_python` | Execute Python in a sandboxed subprocess |
| `run_shell` | Execute whitelisted shell commands |
| `memory_store` | Store a value in shared agent memory |
| `memory_retrieve` | Retrieve a value from shared memory |
| `output_validator` | Validate data against a JSON Schema |
| `quality_scorer` | LLM-based quality scoring (1-10) |

---

## Examples

```bash
# Simple research task
python examples/simple_research.py

# Full report generation pipeline
python examples/report_generation.py
```

---

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Custom Tools

```python
from hydra.tools.base import BaseTool
from hydra.models import ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "The input"}
        },
        "required": ["input"],
    }

    async def execute(self, input: str) -> ToolResult:
        try:
            result = do_something(input)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

# Register it
from hydra import Hydra
hydra = Hydra()
hydra.tool_registry.register(MyTool())
```

---

## License

MIT
