# Hydra Frontend — Development TODO

> Track progress here. Check off items as completed.

## Phase 1: Framework Additions ✅ COMPLETE
- [x] Human-in-the-loop confirmation gates
- [x] Audit logging
- [x] Output sanitization

## Phase 2: FastAPI Backend ✅ COMPLETE
- [x] `hydra/server.py` — main server file
- [x] `GET /` — serve frontend static files
- [x] `GET /api/config` — return current config (sans API key)
- [x] `POST /api/config` — update config at runtime
- [x] `GET /api/tools` — list registered tools + descriptions
- [x] `GET /api/models` — suggested model list
- [x] `POST /api/upload` — file upload → FileProcessor → return FileAttachments
- [x] `WS /ws/task` — WebSocket: send task, receive HydraEvent stream
- [x] `POST /api/task` — REST trigger for webhooks/programmatic use
- [x] `GET /api/history` — list past task runs
- [x] `GET /api/history/{id}` — full result for a past run
- [x] `DELETE /api/history/{id}` — delete run
- [x] History DB (SQLite with WAL)
- [x] Audit log integration (EventBus → audit.log)

## Phase 3: Frontend — Core Pages ✅ COMPLETE
- [x] Wire frontend to FastAPI WebSocket (replace mock streaming)
- [x] Page 1: Home (IDLE) — HYDRA title, input bar, recent tasks cards from history API
- [x] Page 2: Orchestration View — real-time pipeline visualization
  - [x] BrainPanel (planning status)
  - [x] GroupPanel (wraps parallel agent cards)
  - [x] AgentCard (role, status, progress, tool calls, score, tokens, expandable)
  - [x] QualityBar (per-agent score visualization)
  - [x] SynthesisPanel (streaming synthesis output)
  - [x] StatusBar (elapsed time, tokens, cost)
  - [x] Cancel button (abort pipeline)
- [x] Page 3: Result View
  - [x] Formatted markdown → HTML output
  - [x] Generated files list + download buttons
  - [x] Per-agent breakdown accordion
  - [x] Quality scores visualization
  - [x] Execution timeline (parallel/sequential bar chart)
  - [x] Metadata: time, tokens, cost
  - [x] "Run Again" + "New Task" buttons
  - [x] Export: clipboard, PDF, DOCX
- [x] Page 4: History — past runs table/cards, search/filter, delete

## Phase 4: Frontend — Enhancements (IN PROGRESS)

### Milestone 4.1 ✅ COMPLETE
- [x] Error handling: connection state machine (idle/connecting/connected/failed)
- [x] Error handling: connection-lost banners with honest messaging
- [x] Error handling: pipeline error cards with partial result preservation
- [x] Error handling: toast notification system (success/warning/error/info)
- [x] Error handling: error normalization utility
- [x] Export: clipboard copy with metadata
- [x] Export: PDF via print stylesheet
- [x] Export: DOCX via backend `/api/export/docx` (python-docx)
- [x] MoonIcon/SunIcon dark mode toggle

### Milestone 4.2 ✅ COMPLETE
- [x] Human-in-the-loop modal (queue, risk badges, keyboard shortcuts, auto-timeout, timeline)
- [x] Settings: search backend selector + search API key (with masked input)
- [x] Settings: "Test Connection" button (litellm ping, latency display)
- [x] Settings: backend config sync (debounced save, server merge on load, dirty indicator)
- [x] Settings: inline validation (API key, URL format, timeout sanity)
- [x] Settings: Brain Strategy presets (Balanced/Fast/High Quality/Cost Aware)
- [x] Settings: custom Brain system prompt override (2000 char, expandable textarea)
- [x] Settings: cost estimation toggle (show/hide across StatusBar + ResultView)
- [x] Responsive polish for all pages (mobile/tablet/desktop)

### Security & Reliability Fixes (Applied)
- [x] WebSocket auth handshake timeout (10s)
- [x] WebSocket start_task timeout (30s)
- [x] File path traversal validation (restrict to CWD/upload/output dirs)
- [x] SSRF blocklist: IPv6 link-local (fe80::/10)
- [x] EventBus.close() deadlock prevention + telemetry counters
- [x] stream() pipeline cancel guard (only if not done)
- [x] Mutable defaults: Field(default_factory=...) for models
- [x] DOCX export auth (serverToken prop, not window global)
- [x] DOCX filename sanitization (Content-Disposition injection prevention)
- [x] Config range validation (ge/le/gt bounds on all numeric fields)
- [x] Shell tool: block absolute paths and '..' in arguments
- [x] Python tool: skip symlinks when collecting output files
- [x] Upload endpoint: enforce max_upload_files count limit
- [x] Upload endpoint: reject null/control-char filenames with 400
- [x] REST auth: header-only (removed query param ?token= leak)
- [x] Auth docs: all docstrings consistent with header-only policy

## Phase 5: Build & Deploy ⬅️ NEXT

### 5a: Package & Publish (~1 day)
- [x] Vite builds static files → FastAPI serves from /static (already working)
- [ ] `py.typed` marker for IDE type checking
- [ ] Rename `hydra/` → `hydra_agents/` (avoid import collision with Meta's `hydra-core`)
- [ ] Update all internal imports (`from hydra.` → `from hydra_agents.`)
- [ ] CLI entry point: `hydra-agents serve` / `hydra-agents run "task"` / `hydra-agents --version`
- [ ] Add `[project.scripts]` to pyproject.toml
- [ ] Auto-open browser on `serve` launch
- [ ] Build hook: bundle pre-built frontend dist into wheel (`MANIFEST.in` or setuptools config)
- [ ] Test `pip install .` from clean venv — verify end-to-end works
- [ ] Publish to TestPyPI, verify install
- [ ] Publish to PyPI (`pip install hydra-agents`)

### 5b: Docker (~1 day)
- [ ] Dockerfile: multi-stage (node build → python runtime)
- [ ] docker-compose.yml with volume mounts for output/config
- [ ] `--network none` sandboxing option for run_python/run_shell tools
- [ ] README quickstart update (pip install + Docker sections)

### 5c: CI/CD (~0.5 day)
- [ ] GitHub Actions: tag → build wheel → publish to PyPI
- [ ] GitHub Actions: build + push Docker image to GHCR
- [ ] Version bumping strategy (manual tag or `bump2version`)

### 5d: Standalone exe (optional, 3-5 days — only if demand exists)
- [ ] PyInstaller spec file with hidden imports (litellm, httpx, pydantic, etc.)
- [ ] `--add-data` for frontend dist, fonts, icons
- [ ] Platform builds: macOS, Windows, Linux
- [ ] Test on clean machines (not just dev env)

> **Note:** 5d is high-effort, high-pain (PyInstaller + litellm dynamic imports = rabbit holes).
> Skip unless users specifically ask for a standalone binary. Docker + pip covers 95% of users.

## Phase 6: Future (v2+)
- [ ] MCP integration (tools wrapping MCP servers)
- [ ] Webhook triggers (external event → task)
- [ ] Custom Brain strategies per domain
- [ ] Vector store / RAG tool
- [ ] Data classification / sensitivity routing (policy-driven tool/model restrictions)
- [ ] User accounts + team features

---
*Last updated: 2026-04-03*
