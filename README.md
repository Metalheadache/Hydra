# Hydra 🐍

**Dynamic Multi-Agent Orchestration Framework**

Hydra decomposes complex tasks into sub-tasks, dynamically generates specialized AI agents at runtime, executes them via a hybrid DAG (parallel + sequential), and synthesizes results — with real-time streaming of every step.

Unlike CrewAI or AutoGen where agents are pre-defined, Hydra's Brain **generates agent specifications on the fly** — roles, tools, constraints, and personas are tailored to each specific task.

---

## Features

- 🧠 **Brain (Planner)** — Automatic task decomposition + agent generation via structured LLM call
- 🤖 **Dynamic Agents** — Each agent gets a tailored role, goal, backstory, and tool set — generated at runtime, not pre-built
- ⚡ **Hybrid DAG Execution** — Independent tasks run in parallel; dependent tasks wait automatically
- 📡 **Real-time Streaming** — Token-by-token LLM output, tool call visibility, and full pipeline progress via `.stream()`
- 🖥️ **Web UI** — Glassmorphism chat interface with live orchestration view, agent cards, quality scores, and result export
- 🔄 **Retry + Quality Gate** — Failed agents retry with exponential backoff; LLM quality scoring (1-10) with automatic re-dispatch
- 🔀 **Provider-Agnostic** — Works with Anthropic, OpenAI, Ollama, Azure, Gemini, DeepSeek, and [100+ providers via litellm](https://docs.litellm.ai/docs/providers)
- 📎 **File Upload** — Attach PDFs, DOCX, XLSX, PPTX, code files — text auto-extracted for agent context (30+ formats)
- 🔧 **30+ Built-in Tools** — Document generation, file reading (.doc/.docx/.xlsx/.csv/.pptx/.pdf/code), file management, research, data analysis, code execution, memory, translation, templates, PDF operations, validation
- 📎 **Smart File Handling** — Uploaded files auto-extracted for context; agents can re-read originals with reader tools for full structured access (tables, headings, metadata)
- 🛡️ **Human-in-the-Loop** — Tools with `requires_confirmation` pause for user approval with risk badges, keyboard shortcuts, auto-timeout, and confirmation queue
- 📋 **Audit Logging** — Every LLM call, tool execution, and state mutation logged as structured JSON Lines
- 🌐 **FastAPI Backend** — REST + WebSocket API with task history, file upload, optional auth token

---

## Quick Start

### Option 1: pip install (recommended)

```bash
pip install hydra-agents
hydra-agents serve
# → Auto-opens http://localhost:8000
```

Configure your LLM provider in the Settings panel (gear icon), then type a task and watch the agents work.

### Option 2: Docker

```bash
git clone https://github.com/Metalheadache/Hydra.git
cd Hydra

# Create a .env file with your provider key (or set env vars in docker-compose.yml)
echo "HYDRA_API_KEY=sk-ant-..." > .env

docker compose up --build
# → Open http://localhost:8000
```

Generated files (charts, exports, etc.) appear in `./hydra_output/` on your host.

**Network sandboxing** — to block outbound network calls inside `run_python` / `run_shell` subprocesses, do both of the following:

1. Add to your `.env` (or uncomment in `docker-compose.yml`):
   ```env
   HYDRA_SANDBOX_NETWORK=true
   ```
2. No extra Docker capabilities are needed on most Linux kernels. If you see a permission error, enable unprivileged user namespaces on the host:
   ```bash
   sysctl -w kernel.unprivileged_userns_clone=1
   ```
   or uncomment `cap_add: [SYS_ADMIN]` in `docker-compose.yml` as a fallback.

### Option 3: From source (for development)

```bash
git clone https://github.com/Metalheadache/Hydra.git
cd Hydra
pip install -e ".[dev]"

# Build frontend
cd frontend && npm install && npx vite build && cd ..

# Start server (auto-opens browser)
hydra-agents serve
```

### Option 4: Python API

```python
import asyncio
from hydra_agents import Hydra

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

### Option 5: Streaming API

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

### Option 6: With File Attachments

```python
result = await hydra.run(
    "Summarize these reports and compare findings",
    files=["report.pdf", "data.xlsx", "notes.md"]
)
```

### Option 7: Callbacks

```python
hydra = Hydra()
hydra.on_agent_start(lambda e: print(f"🤖 {e.agent_id} started"))
hydra.on_agent_complete(lambda e: print(f"✅ {e.agent_id} done"))
hydra.on_tool_call(lambda e: print(f"🔧 {e.data['tool']}"))

result = await hydra.run("Write a market analysis")
```

---

## Web UI

The built-in web interface provides a real-time view of the multi-agent pipeline:

```
┌─────────────────────────────────────────────────┐
│  Task: "Analyze the AI market..."    [⏹ Cancel] │
├─────────────────────────────────────────────────┤
│  🧠 Brain: 4 sub-tasks, 2 groups               │
│                                                  │
│  ⚡ Group 1 — Parallel                           │
│  ┌──────────────┐ ┌──────────────┐              │
│  │ 🔍 Researcher│ │ 📊 Analyst   │              │
│  │ ████████░░   │ │ ██████████ ✅│              │
│  │ 🔧 web_search│ │ Score: 8/10  │              │
│  └──────────────┘ └──────────────┘              │
│                                                  │
│  ⚡ Group 2 — Waiting...                         │
│  ┌──────────────┐                                │
│  │ ✍️ Writer     │                                │
│  │ ⏳ Pending    │                                │
│  └──────────────┘                                │
│                                                  │
│  📝 Synthesis: streaming output...               │
├─────────────────────────────────────────────────┤
│  ⏱ 45s | 🪙 12,450 tokens | 💰 ~$0.03          │
└─────────────────────────────────────────────────┘
```

**Features:**
- Live agent cards with status, tool calls, token preview, quality scores
- Streaming synthesis output token-by-token
- Result view with markdown rendering, agent breakdown, file downloads
- Export: clipboard (with metadata), PDF (print stylesheet), DOCX (server-generated)
- Task history with search and re-run
- Human-in-the-loop confirmation modals with risk badges, queue, auto-timeout, keyboard shortcuts
- Confirmation timeline log tracking all approval decisions
- Connection state monitoring with error banners and toast notifications
- Dark/light mode with glassmorphism design
- Works without backend (mock mode for demo)

---

## API Server

Hydra includes a FastAPI backend for web deployment:

```bash
hydra-agents serve --host 0.0.0.0 --port 8000
```

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve web UI |
| `GET` | `/api/config` | Current config (API key redacted) |
| `POST` | `/api/config` | Update config at runtime |
| `GET` | `/api/tools` | List registered tools |
| `GET` | `/api/models` | Suggested model list |
| `POST` | `/api/upload` | Upload files for processing |
| `POST` | `/api/task` | Run task (REST, non-streaming) |
| `POST` | `/api/export/docx` | Export result as DOCX |
| `GET` | `/api/history` | List past task runs |
| `GET` | `/api/history/{id}` | Full result for a past run |
| `DELETE` | `/api/history/{id}` | Delete a history entry |

### WebSocket

`WS /ws/task` — Real-time streaming endpoint

```json
// Client sends (auth optional)
{"type": "auth", "token": "your-server-token"}
{"type": "start_task", "task": "...", "files": ["upload_id"]}

// Server streams HydraEvents
{"type": "brain_start", "timestamp": 1234567890}
{"type": "agent_start", "agent_id": "agent_abc", "data": {"role": "Researcher"}}
{"type": "agent_token", "agent_id": "agent_abc", "data": "The market"}
{"type": "pipeline_complete", "data": {"output": "...", "files_generated": [...]}}

// Client can send during execution
{"type": "confirmation_response", "confirmation_id": "conf_123", "approved": true}
{"type": "cancel"}
```

---

## Configuration

All settings use the `HYDRA_` environment variable prefix:

| Variable | Default | Description |
|---|---|---|
| `HYDRA_API_KEY` | `""` | LLM provider API key |
| `HYDRA_DEFAULT_MODEL` | `deepseek/deepseek-chat` | Default model (litellm format) |
| `HYDRA_BRAIN_MODEL` | `deepseek/deepseek-chat` | Model for task planning |
| `HYDRA_POST_BRAIN_MODEL` | `deepseek/deepseek-chat` | Model for synthesis |
| `HYDRA_API_BASE` | `None` | Custom API endpoint |
| `HYDRA_MAX_CONCURRENT_AGENTS` | `5` | Max parallel agents |
| `HYDRA_PER_AGENT_TIMEOUT_SECONDS` | `300` | Timeout per agent |
| `HYDRA_TOTAL_TASK_TIMEOUT_SECONDS` | `1200` | Total pipeline timeout |
| `HYDRA_TOTAL_TOKEN_BUDGET` | `1000000` | Token budget (abort if exceeded) |
| `HYDRA_OUTPUT_DIRECTORY` | `./hydra_output` | File output directory |
| `HYDRA_MIN_QUALITY_SCORE` | `5.0` | Minimum score before retry |
| `HYDRA_SERVER_TOKEN` | `""` | Optional API auth token |
| `HYDRA_CORS_ORIGINS` | `*` | CORS allowed origins |
| `HYDRA_SANDBOX_NETWORK` | `false` | Block outbound network in code tools (Linux `unshare`) |
| `HYDRA_SEARCH_BACKEND` | `brave` | Web search provider |
| `HYDRA_SEARCH_API_KEY` | `""` | Search API key |

### Provider Examples

```bash
# Anthropic
HYDRA_API_KEY=sk-ant-...
HYDRA_DEFAULT_MODEL=anthropic/claude-sonnet-4-6

# OpenAI
HYDRA_API_KEY=sk-...
HYDRA_DEFAULT_MODEL=gpt-4o

# DeepSeek
HYDRA_API_KEY=sk-...
HYDRA_DEFAULT_MODEL=deepseek/deepseek-chat
HYDRA_BRAIN_MODEL=deepseek/deepseek-reasoner  # R1 for planning

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
```

---

## Architecture

```
User Task + Files
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

Upstream agent outputs are automatically injected into downstream agent prompts with sanitization:

```
Agent A (Research)  → StateManager → Agent C (Analysis)
Agent B (Data)      → StateManager ↗
                                      ↓
                                Agent D (Report Writer)
```

Token budgeting prevents context overflow. Long outputs are truncated with references to full versions in shared memory. Output sanitization strips prompt injection patterns before injection.

---

## Built-in Tools

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

### 📖 File Reading
| Tool | Description |
|---|---|
| `read_docx` | Read Word documents (.docx + legacy .doc) — text, tables, headings, metadata |
| `read_xlsx` | Read Excel workbooks — structured data, column stats, multi-sheet |
| `read_csv` | Read CSV/TSV — auto-detect encoding (utf-8/gb18030) and delimiter |
| `read_pptx` | Read PowerPoint presentations — slides, speaker notes, tables, metadata |
| `read_code` | Read source code — line numbers, language detection, structure map |

### 🗂️ File Management
| Tool | Description |
|---|---|
| `file_manager` | List, tree, info, find, copy, zip, unzip, mkdir |
| `file_move` | Move/rename files (requires confirmation) |
| `file_delete` | Delete files/dirs (requires confirmation) |

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
| `run_python` | Python execution (temp dir, credential-stripped env, requires confirmation) |
| `run_shell` | Whitelisted shell commands only |

### 🗂️ Memory
| Tool | Description |
|---|---|
| `memory_store` | Write to shared agent memory |
| `memory_retrieve` | Read from shared memory |

### 🌐 Language
| Tool | Description |
|---|---|
| `translate` | LLM-powered translation (any language pair, 16K tokens) |
| `summarize` | Summarize text (bullets/paragraph/executive, 8K tokens) |

### 📝 Templates
| Tool | Description |
|---|---|
| `template_render` | Jinja2 template rendering with sandbox security |

### 📑 PDF Operations
| Tool | Description |
|---|---|
| `pdf_merge` | Merge multiple PDFs with page ranges and bookmarks |
| `pdf_split` | Split PDF by pages, chunks, or one-per-page |

### ✅ Validation
| Tool | Description |
|---|---|
| `output_validator` | Validate data against JSON Schema |
| `quality_scorer` | LLM-based quality scoring (1-10) |

---

## Streaming Events

When using `hydra.stream()` or the WebSocket endpoint, you receive real-time events:

| Event Type | When | Data |
|---|---|---|
| `pipeline_start` | Pipeline begins | Task description |
| `brain_start` | Brain planning begins | — |
| `brain_complete` | Plan ready | Sub-task count, groups |
| `group_start` | Parallel group begins | Group index, agent IDs |
| `agent_start` | Agent begins execution | Agent ID, role |
| `agent_token` | LLM generates a token | Token text |
| `agent_tool_call` | Agent calls a tool | Tool name, arguments |
| `agent_tool_result` | Tool returns | Success/error, data |
| `agent_complete` | Agent finishes | Output, tokens used |
| `agent_error` | Agent failed | Error message |
| `agent_retry` | Agent retrying | Attempt number |
| `group_complete` | All agents in group done | Results |
| `quality_start` | Quality scoring begins | — |
| `quality_score` | Per-agent score | Score (1-10), feedback |
| `quality_retry` | Low-score agent re-running | Agent ID |
| `synthesis_start` | Final synthesis begins | — |
| `synthesis_token` | Synthesis LLM token | Token text |
| `synthesis_complete` | Final output ready | Output, files |
| `file_processed` | Uploaded file processed | File info |
| `confirmation_required` | Tool needs approval | Tool name, args |
| `confirmation_response` | User approved/rejected | Result |
| `pipeline_complete` | Everything done | Full result |
| `pipeline_error` | Pipeline failed | Error details |

---

## Security

Hydra runs LLM-generated code and tool calls. Here's what's protected and what's not:

**What's hardened:**
- **Shell execution**: Whitelist-only (`ls`, `cat`, `head`, `wc`, `grep`, `find`, `jq`). Metacharacters blocked. Uses `subprocess_exec` (no shell interpretation).
- **Python execution**: Runs in temp directory. Cloud credentials stripped from env (`AWS_*`, `OPENAI_API_KEY`, etc.). Requires user confirmation by default.
- **Path traversal**: All file tools validate paths with `Path.is_relative_to()`. PDF reader has `allowed_dirs` restriction.
- **SSRF prevention**: Private IPs blocked (RFC 1918, link-local, loopback, AWS metadata). Redirects disabled. DNS resolution checked.
- **Prompt injection**: Upstream agent outputs sanitized — role markers, XML injection tags, `[INST]`/`<<SYS>>` patterns stripped. Context wrapped in XML delimiters.
- **API auth**: Optional `HYDRA_SERVER_TOKEN` for all endpoints. WebSocket auth via first message (not query params).
- **File upload**: Size limits, file count limits, null byte rejection, chunked reads.
- **Audit logging**: Every LLM call, tool execution, and state mutation logged as JSON Lines with thread-safe writes.
- **Tool isolation**: Stateful tools get per-agent instances. No shared mutable state between concurrent runs.

**What's NOT sandboxed (be honest with yourself):**
- **Python execution**: Has filesystem read by default. Network access can be blocked with `HYDRA_SANDBOX_NETWORK=true` (Linux only, uses `unshare --net`). For full isolation, run in Docker with `--network none`.
- **LLM prompt injection**: Defense-in-depth sanitization helps but isn't a guarantee against sophisticated attacks.

**For production deployment**, run Hydra inside a container with restricted network and filesystem access.

---

## File Upload

Hydra extracts text from 30+ file formats for agent context:

**Documents:** `.pdf`, `.docx`, `.xlsx`, `.pptx`
**Text:** `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.xml`, `.html`, `.log`, `.ini`, `.toml`
**Code:** `.py`, `.js`, `.ts`, `.java`, `.cpp`, `.c`, `.go`, `.rs`, `.rb`, `.php`, `.swift`, `.kt`

- Max 20 files per task, 50MB per file
- 50K character extraction limit per file (truncated with marker)
- Unsupported formats: filepath available for agents to reference directly

---

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
# 270+ tests covering core pipeline, security, streaming, events, server, history
```

---

## Custom Tools

```python
from hydra_agents.tools.base import BaseTool
from hydra_agents.models import ToolResult

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
    requires_confirmation = False  # Set True for human-in-the-loop

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

**Phase 4 ✅ COMPLETE:**
- [x] Connection error handling (state machine, banners, toasts)
- [x] Export: clipboard + PDF + DOCX
- [x] Security hardening (WS timeouts, SSRF, path traversal, EventBus fixes, config validation)
- [x] Human-in-the-loop confirmation modal (queue, risk badges, auto-timeout, timeline)
- [x] Tool expansion: 22 → 33 tools (readers, file manager, templates, PDF ops)
- [x] Settings: search config, test connection, validation, backend sync
- [x] Advanced controls: brain strategy presets, custom prompt override, cost toggle
- [x] Responsive polish (mobile/tablet/desktop)

**Phase 5 ✅ COMPLETE:**
- [x] PyPI package (`pip install hydra-agents`)
- [x] CLI entry point (`hydra-agents serve` / `hydra-agents run` / `--version`)
- [x] Auto-open browser on launch
- [x] Frontend bundled in wheel
- [x] Docker: multi-stage build (node → python), docker-compose, non-root user
- [x] Network sandbox: `HYDRA_SANDBOX_NETWORK=true` blocks outbound in code tools (Linux `unshare`)
- [x] CI/CD: GitHub Actions — PyPI publish on tag (OIDC trusted), Docker push to GHCR
- [x] Version management: `bump-my-version` (bump patch/minor/major → commit → tag)

**Phase 6 (Future):**
- [ ] Standalone executable (PyInstaller, Windows — only if demand exists)
- [ ] MCP (Model Context Protocol) tool integration
- [ ] Vector store / RAG tool
- [ ] Data classification / sensitivity routing
- [ ] Webhook triggers
- [ ] User accounts + team features

---

## License

MIT
