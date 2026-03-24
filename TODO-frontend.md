# Hydra Frontend — Development TODO

> Track progress here. Check off items as completed.

## Phase 1: Framework Additions (before frontend)
- [ ] Human-in-the-loop confirmation gates (requires_confirmation tools pause + await approval)
- [ ] Audit logging (structured JSON log of every LLM call, tool exec, state mutation)
- [ ] Output sanitization in StateManager context injection (prevent prompt injection)

## Phase 2: FastAPI Backend
- [ ] `hydra/server.py` — main server file
- [ ] `GET /` — serve frontend static files
- [ ] `GET /api/config` — return current config (sans API key)
- [ ] `POST /api/config` — update config at runtime
- [ ] `GET /api/tools` — list registered tools + descriptions
- [ ] `GET /api/models` — suggested model list
- [ ] `POST /api/upload` — file upload → FileProcessor → return FileAttachments
- [ ] `WS /ws/task` — WebSocket: send task, receive HydraEvent stream
- [ ] `POST /api/task` — REST trigger for webhooks/programmatic use (non-WebSocket)
- [ ] `GET /api/history` — list past task runs
- [ ] `GET /api/history/{id}` — full result for a past run
- [ ] History DB (SQLite: task_id, text, timestamp, status, duration, tokens, cost, result JSON)
- [ ] Audit log integration (tap EventBus → write to audit.log)

## Phase 3: Frontend — Core Pages
- [ ] Page 1: Home (IDLE) — HYDRA title, input bar, recent tasks cards from history
- [ ] Page 2: Orchestration View — real-time pipeline visualization
  - [ ] BrainPanel (planning status)
  - [ ] GroupPanel (wraps parallel agent cards)
  - [ ] AgentCard (role, status, progress, tool calls, score, tokens, expandable)
  - [ ] QualityBar (per-agent score visualization)
  - [ ] SynthesisPanel (streaming synthesis output)
  - [ ] StatusBar (elapsed time, tokens, cost)
  - [ ] Cancel button (abort pipeline)
- [ ] Page 3: Result View
  - [ ] Formatted markdown → HTML output
  - [ ] Generated files list + download buttons
  - [ ] Per-agent breakdown accordion
  - [ ] Quality scores visualization
  - [ ] Execution timeline (parallel/sequential bar chart)
  - [ ] Metadata: time, tokens, cost
  - [ ] "Run Again" + "New Task" buttons
  - [ ] Export: clipboard, PDF, DOCX
- [ ] Page 4: History — past runs table/cards, search/filter, delete

## Phase 4: Frontend — Enhancements
- [ ] Human-in-the-loop modal (tool confirmation approve/reject via WebSocket)
- [ ] Settings: search API key + backend selection
- [ ] Settings: "Test Connection" button (ping LLM)
- [ ] Settings: Brain Strategy selector / custom system prompt override
- [ ] Settings: cost estimation toggle
- [ ] Settings: data classification / sensitivity routing config
- [ ] MoonIcon/SunIcon toggle (done ✅)
- [ ] Responsive polish for all pages (mobile/tablet/desktop)
- [ ] Error handling: connection lost, server down, LLM errors

## Phase 5: Build & Deploy
- [ ] Vite builds static files → FastAPI serves from /static
- [ ] PyInstaller: bundle FastAPI + Hydra + static frontend into single exe
- [ ] Auto-open browser on launch
- [ ] PyPI publish (`pip install hydra-agents`)
- [ ] `py.typed` marker for IDE type checking

## Phase 6: Future (v2+)
- [ ] MCP integration (tools wrapping MCP servers)
- [ ] Webhook triggers (external event → task)
- [ ] Custom Brain strategies per domain
- [ ] Vector store / RAG tool
- [ ] User accounts + team features
- [ ] Docker deployment with --network none sandboxing

---
*Last updated: 2026-03-25*
