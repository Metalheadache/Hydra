# Hydra 🐍

**Dynamic Multi-Agent Orchestration Framework**

Hydra decomposes complex tasks into sub-tasks, dynamically generates specialized AI agents at runtime, executes them via a hybrid DAG (parallel + sequential), and synthesizes results — with real-time streaming of every step.

Unlike CrewAI or AutoGen where agents are pre-defined, Hydra's Brain **generates agent specifications on the fly** — roles, tools, constraints, and personas are tailored to each specific task.

---

## Features

- 🧠 **Brain (Planner)** — Automatic task decomposition + agent generation via structured LLM call
- 🤖 **Dynamic Agents** — Each agent gets a tailored role, goal, backstory, and tool set — generated at runtime, not pre-built
- ⚡ **Hybrid DAG Execution** — Independent tasks run in parallel; dependent tasks wait automatically
- 📡 **Real-time Streaming** — Token-by-token LLM output, tool call visibility, and full pipeline progress via `hydra.stream()`
- 🔄 **Retry + Quality Gate** — Failed agents retry with exponential backoff; LLM quality scoring (1-10) with automatic re-dispatch
- 🔀 **Provider-Agnostic** — Works with Anthropic, OpenAI, Ollama, Azure, Gemini, and [100+ providers via litellm](https://docs.litellm.ai/docs/providers)
- 🔧 **22 Built-in Tools** — Document generation, research, data analysis, code execution, memory, validation
- 🔒 **Security Hardened** — Shell command whitelisting, SSRF prevention, path traversal protection, sandboxed execution

---

## Quick Start

### Install

```bash
# From source
git clone https://github.com/Metalheadache/Hydra.git
cd Hydra
pip install -e ".[dev]"
```

### Configure

```bash
cp .env.example .env
# Edit .env with your API key and preferred model
```

### Run

```python
import asyncio
from hydra import Hydra

async def main():
    hydra = Hydra()
    result = await hydra.run(
        "Research the current state of AI agents and write a 3-section summary report."
    )
    print(result["output"])
    print(f"Files: {result['files_generated']}")
    print(f"Tokens: {result['execution_summary']['total_tokens']}")

asyncio.run(main())
```

### Stream (Real-time)

```python
async def main():
    hydra = Hydra()
    
    async for event in hydra.stream("Analyze the AI market and create a report"):
        if event.type == "agent_token":
            print(event.data, end="", flush=True)
        elif event.type == "agent_start":
            print(f"\n🤖 Agent started: {event.agent_id}")
        elif event.type == "agent_tool_call":
            print(f"  🔧 Tool: {event.data['tool']}")
        elif event.type == "quality_score":
            print(f"  📊 Score: {event.data['score']}/10")
        elif event.type == "pipeline_complete":
            print(f"\n✅ Done!")

asyncio.run(main())
```

### Callbacks

```python
hydra = Hydra()
hydra.on_agent_start(lambda e: print(f"🤖 {e.agent_id} started"))
hydra.on_agent_complete(lambda e: print(f"✅ {e.agent_id} done"))
hydra.on_tool_call(lambda e: print(f"🔧 {e.data['tool']}({e.data.get('args', {})})"))
hydra.on_event(lambda e: None)  # catch-all

result = await hydra.run("Write a market analysis")
```

---

## Configuration

All settings use the `HYDRA_` environment variable prefix:

| Variable | Default | Description |
|---|---|---|
| `HYDRA_API_KEY` | `""` | Provider API key |
| `HYDRA_DEFAULT_MODEL` | `anthropic/claude-sonnet-4-6` | Default model (litellm format) |
| `HYDRA_BRAIN_MODEL` | `anthropic/claude-sonnet-4-6` | Model for task planning |
| `HYDRA_POST_BRAIN_MODEL` | `anthropic/claude-sonnet-4-6` | Model for synthesis |
| `HYDRA_API_BASE` | `None` | Custom API endpoint |
| `HYDRA_MAX_CONCURRENT_AGENTS` | `5` | Max parallel agents |
| `HYDRA_PER_AGENT_TIMEOUT_SECONDS` | `60` | Timeout per agent |
| `HYDRA_TOTAL_TASK_TIMEOUT_SECONDS` | `300` | Total pipeline timeout |
| `HYDRA_TOTAL_TOKEN_BUDGET` | `100000` | Token budget (abort if exceeded) |
| `HYDRA_OUTPUT_DIRECTORY` | `./hydra_output` | File output directory |
| `HYDRA_SEARCH_BACKEND` | `brave` | Web search provider |
| `HYDRA_SEARCH_API_KEY` | `""` | Search API key |
| `HYDRA_MIN_QUALITY_SCORE` | `5.0` | Minimum quality score (1-10) before retry |
| `HYDRA_MAX_TOKENS_BRAIN` | `4096` | Max tokens for Brain planning |
| `HYDRA_MAX_TOKENS_SYNTHESIS` | `8192` | Max tokens for synthesis |

### Provider Examples

```bash
# Anthropic
HYDRA_API_KEY=sk-ant-...
HYDRA_DEFAULT_MODEL=anthropic/claude-sonnet-4-6

# OpenAI
HYDRA_API_KEY=sk-...
HYDRA_DEFAULT_MODEL=gpt-4o

# Ollama (local, free)
HYDRA_API_BASE=http://localhost:11434
HYDRA_DEFAULT_MODEL=ollama/llama3

# Azure OpenAI
HYDRA_API_KEY=<azure-key>
HYDRA_API_BASE=https://<resource>.openai.azure.com
HYDRA_DEFAULT_MODEL=azure/gpt-4o

# Google Gemini
HYDRA_API_KEY=<gemini-key>
HYDRA_DEFAULT_MODEL=gemini/gemini-2.5-flash

# DeepSeek
HYDRA_API_KEY=sk-...
HYDRA_DEFAULT_MODEL=deepseek/deepseek-chat
HYDRA_BRAIN_MODEL=deepseek/deepseek-reasoner  # R1 for planning
HYDRA_POST_BRAIN_MODEL=deepseek/deepseek-chat
```

---

## Architecture

```
User Task
    │
    ▼
┌─────────┐
│  Brain   │  → Decomposes task → TaskPlan (sub-tasks + agent specs + DAG)
└────┬─────┘
     │
     ▼
┌──────────────┐
│ AgentFactory │  → Instantiates agents with tools, state manager, event bus
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ ExecutionEngine   │  → DAG execution: parallel groups, retries, semaphore
│                   │
│  [Group 1: A, B]  │  ← Run in parallel
│  [Group 2: C]     │  ← Waits for A and B
└──────┬────────────┘
       │
       ▼
┌──────────────┐
│  Post-Brain  │  → Quality gate → LLM scoring → Retry → Synthesis
└──────────────┘
       │
       ▼
   Final Result + Files + Metadata
```

### How Context Flows

Upstream agent outputs are automatically injected into downstream agent prompts:

```
Agent A (Research)  → StateManager → Agent C (Analysis)
Agent B (Data)      → StateManager ↗
                                      ↓
                                Agent D (Report Writer)
```

Token budgeting ensures injected context doesn't overflow the model's context window. Long outputs are automatically truncated with references to the full version in shared memory.

---

## Built-in Tools (22)

### 📄 File Writing
| Tool | Description |
|---|---|
| `write_markdown` | Write `.md` files |
| `write_json` | Write `.json` with pretty-printing |
| `write_csv` | Write `.csv` from rows |
| `write_code` | Write source code (any extension) |

### 📑 Document Generation
| Tool | Description |
|---|---|
| `write_docx` | Word documents (headings, bullets, bold/italic) |
| `write_xlsx` | Excel (multi-sheet, auto-width, freeze, filters) |
| `write_pptx` | PowerPoint (title/content/blank slides, speaker notes) |
| `read_pdf` | Extract text from PDF files |

### 🔍 Research & Web
| Tool | Description |
|---|---|
| `web_search` | Search the web (Brave/Tavily/SerpAPI) |
| `web_fetch` | Fetch URL → clean text |
| `http_request` | Generic HTTP client (GET/POST/PUT/DELETE) with SSRF prevention |

### 🧮 Data & Analysis
| Tool | Description |
|---|---|
| `json_validator` | Validate JSON against schema |
| `chart_generator` | Bar/line/pie/scatter charts → PNG |
| `data_transform` | Filter, sort, group_by, select, limit pipelines |

### 💻 Code Execution
| Tool | Description |
|---|---|
| `run_python` | Sandboxed Python execution (temp directory) |
| `run_shell` | Whitelisted shell commands only |

### 🗂️ Memory
| Tool | Description |
|---|---|
| `memory_store` | Write to shared agent memory |
| `memory_retrieve` | Read from shared memory |

### 🌐 Language
| Tool | Description |
|---|---|
| `translate` | LLM-powered translation (any language pair) |
| `summarize` | Summarize text (bullets/paragraph/executive) |

### ✅ Validation
| Tool | Description |
|---|---|
| `output_validator` | Validate data against JSON Schema |
| `quality_scorer` | LLM-based quality scoring (1-10) |

---

## Streaming Events

When using `hydra.stream()`, you receive real-time events for every pipeline stage:

| Event Type | When | Data |
|---|---|---|
| `pipeline_start` | Pipeline begins | Task description |
| `brain_start` | Brain planning begins | — |
| `brain_complete` | Plan ready | Number of sub-tasks, groups |
| `group_start` | Parallel group begins | Group index, agent IDs |
| `agent_start` | Agent begins execution | Agent ID, role |
| `agent_token` | LLM generates a token | Token text |
| `agent_tool_call` | Agent calls a tool | Tool name, arguments |
| `agent_tool_result` | Tool returns | Success/error, data |
| `agent_complete` | Agent finishes | Output summary, tokens used |
| `agent_error` | Agent failed | Error message |
| `agent_retry` | Agent retrying | Attempt number, error |
| `group_complete` | All agents in group done | Results summary |
| `quality_start` | Quality scoring begins | — |
| `quality_score` | Per-agent score | Score (1-10), feedback |
| `quality_retry` | Low-score agent re-running | Agent ID, score |
| `synthesis_start` | Final synthesis begins | — |
| `synthesis_token` | Synthesis LLM token | Token text |
| `synthesis_complete` | Final output ready | Output, files |
| `pipeline_complete` | Everything done | Full result |
| `pipeline_error` | Pipeline failed | Error details |

---

## Security

- **Shell execution**: Commands whitelisted (`ls`, `cat`, `head`, `wc`, `grep`, `find`, `jq`). Shell metacharacters (`|`, `;`, `&`, `` ` ``) blocked. Uses `subprocess_exec` not `subprocess_shell`.
- **Python execution**: Runs in isolated temp directory. ⚠️ Network access not blocked at OS level — use Docker `--network none` for production.
- **SSRF prevention**: HTTP tools block private IP ranges (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16). Redirects disabled.
- **Path traversal**: All file tools validate output paths with `Path.is_relative_to()`. PDF reader has `allowed_dirs` sandboxing.
- **Tool isolation**: Stateful tools (memory, file) get per-agent instances — no shared mutable state between concurrent runs.

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
# 133 tests covering core pipeline, security, streaming, events
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
hydra = Hydra()
hydra.tool_registry.register(MyTool())
```

---

## Roadmap

- [ ] FastAPI + browser-based chat frontend
- [ ] PyPI package (`pip install hydra-agents`)
- [ ] PyInstaller standalone executable
- [ ] `py.typed` marker for IDE type checking
- [ ] MCP (Model Context Protocol) tool integration
- [ ] Vector store / RAG tool
- [ ] Webhook triggers for automated workflows

---

## License

MIT
