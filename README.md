# AgentX SRE-Triage
### Autonomous Incident Response with Gemini — AgentX Hackathon 2026

> AI-powered SRE incident intake, triage, and resolution for e-commerce platforms.  
> Built with **FastAPI · PydanticAI · Gemini 2.5 Flash · React · PostgreSQL · Langfuse**

---

## What It Does

AgentX SRE-Triage is an autonomous incident management agent. When an engineer submits a failure report (text, screenshot, log file, or MP4 video), the agent:

1. **Scans** input through 15 prompt-injection guardrail patterns in <5ms
2. **Analyzes** the incident with Gemini 2.5 Flash — multimodal (text + image + log + video)
3. **Cross-references** real .NET eShop microservice source code for grounded root-cause analysis
4. **Classifies** severity P1–P4 based on business impact
5. **Deduplicates** against the last 48 hours of incidents
6. **Creates** a structured SRE ticket (SRE-XXXX format)
7. **Notifies** the SRE team via Slack + email
8. **Streams live reasoning** to the UI — engineers see every AI thought in real time
9. **Closes the loop** — one-click resolve triggers automatic reporter notification

All steps are traced in Langfuse and persisted to PostgreSQL for full auditability.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AgentX SRE-Triage                            │
│                                                                     │
│  ┌──────────────┐    ┌────────────────────────────────────────┐    │
│  │  React 18    │    │           FastAPI Backend               │    │
│  │  Vite + TW   │◀──▶│                                        │    │
│  │  SSE Stream  │    │  ┌─────────────┐  ┌────────────────┐  │    │
│  └──────────────┘    │  │  Guardrails │  │  Triage Agent  │  │    │
│                      │  │  15 patterns│  │  PydanticAI    │  │    │
│  ┌──────────────┐    │  └──────┬──────┘  └───────┬────────┘  │    │
│  │ Gemini 2.5   │◀───│         │                  │           │    │
│  │ Flash        │    │  ┌──────▼──────────────────▼────────┐  │    │
│  │ (multimodal) │───▶│  │  ingest→triage→ticket→notify→resolve│  │    │
│  └──────────────┘    │  └───────────────┬──────────────────┘  │    │
│                      │                  │                      │    │
│  ┌──────────────┐    │  eShop RAG · Langfuse · SSE Streaming  │    │
│  │  PostgreSQL  │◀───│                                        │    │
│  │  (7 tables)  │    └────────────────────────────────────────┘    │
│  └──────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Demo Scenarios (with Evidence)

### Case 1 — Basket.API Redis Outage (P1 CRITICAL)
Checkout completely down — `RedisConnectionException` in `RedisBasketRepository.cs`.  
**Evidence:** [`evidence/demo_log_checkout_failure.log`](evidence/demo_log_checkout_failure.log) · [`evidence/error_screenshot.png`](evidence/error_screenshot.png)

### Case 2 — Identity.API OOMKilled (P2 HIGH)
Pod killed by OOM at 06:00 UTC. JWT validation failing system-wide, users logged out.  
**Evidence:** [`evidence/identity_connection_refused.log`](evidence/identity_connection_refused.log) · [`evidence/deduplication_identity_service.json`](evidence/deduplication_identity_service.json)

### Case 3 — RabbitMQ / Ordering Saga Stuck (P2 HIGH)
89 orders stuck in `AwaitingValidation`. RabbitMQ heartbeat mismatch dropping consumers.  
**Evidence:** [`evidence/demo_log_payment_errors.log`](evidence/demo_log_payment_errors.log)

### Case 4 — Deduplication
Second report for same Redis outage → AI detects >70% similarity → DUPLICATE, no new ticket.  
**Evidence:** [`evidence/deduplication_example.json`](evidence/deduplication_example.json)

### Case 5 — Prompt Injection Blocked
`"Ignore all previous instructions..."` → blocked in <5ms, HTTP 400, logged to audit.  
**Evidence:** [`evidence/guardrail_blocked.json`](evidence/guardrail_blocked.json)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini 2.5 Flash (multimodal: text + image + log + MP4) |
| Agent Framework | PydanticAI 0.0.19 (structured output + validation) |
| Backend | FastAPI 0.115 + Uvicorn (async, SSE streaming) |
| Database | PostgreSQL 16 (psycopg2-binary) |
| Observability | Langfuse 2.57 (LLM traces, span telemetry, local fallback) |
| Frontend | Vite 6 + React 18 + Tailwind CSS (dark industrial theme) |
| Security | 15-pattern regex guardrail engine + `sanitize_for_prompt()` |
| eShop Context | Microsoft eShop .NET microservices (RAG from real `.cs` source files) |
| Containers | Docker Compose — postgres + backend + frontend/nginx |

---

## Quick Start

### Prerequisites
- Docker Desktop (running)
- Google Gemini API key — free tier: [ai.google.dev](https://ai.google.dev/)
- Langfuse account — free: [us.cloud.langfuse.com](https://us.cloud.langfuse.com)

### 1. Clone

```bash
git clone https://github.com/cszdiego/AgentX-SRE-Triage-Autonomous-Incident-Response-with-Gemini.git
cd AgentX-SRE-Triage-Autonomous-Incident-Response-with-Gemini
```

### 2. Configure secrets

```bash
cp .env.example .env
# Open .env and fill in your API keys
```

```env
GEMINI_API_KEY=your_gemini_key_here
GEMINI_MODEL=gemini-2.5-flash
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

### 3. Run

```bash
docker compose up --build
```

Wait for: `sre_backend | INFO:     Application startup complete.`

### 4. Open

| URL | Purpose |
|-----|---------|
| http://localhost:3000 | Dashboard |
| http://localhost:3000/report | Submit incident |
| http://localhost:8000/docs | Interactive API docs |
| http://localhost:8000/health | Health check |

---

## Key Features

### Live Reasoning Stream
After submit, the browser redirects immediately to the incident detail page. A terminal-style sidebar streams each AI reasoning step live via SSE — guardrail scan, code context load, Gemini token usage, dedup result, ticket creation, notifications. Steps are persisted to the `reasoning_steps` table so they survive page refreshes and future visits.

### Multimodal Analysis
Gemini 2.5 Flash processes text, PNG/JPG screenshots, `.log` files, and `.mp4` video recordings in a single API call. Error text visible in images is extracted and correlated with eShop source code.

### Grounded Root Cause (eShop RAG)
Keyword matching maps the incident to an eShop service, then loads the corresponding `.cs` source files into the Gemini prompt. Root cause references real code — not hallucinations.

### Prompt Injection Defense
15 compiled regex patterns block: instruction overrides, DAN jailbreaks, `[SYSTEM]` injection, SQL injection, code execution, and data exfiltration. Blocked before any AI token is consumed. Every attempt logged to `guardrail_logs`.

### Full Observability
Every pipeline stage is traced in Langfuse with token counts, latency, and model name. Local fallback persists traces to `agent_traces` if Langfuse is unavailable.

---

## Project Structure

```
agentx-sre-triage/
├── backend/
│   ├── app/
│   │   ├── agents/triage_agent.py       # Core 5-stage AI pipeline
│   │   ├── api/incidents.py             # REST + SSE endpoints
│   │   ├── api/tickets.py               # Ticket CRUD + resolve
│   │   ├── core/security.py             # Guardrail engine
│   │   ├── core/streaming.py            # SSE + replay buffer
│   │   ├── db/schema.sql                # PostgreSQL schema (7 tables)
│   │   ├── services/code_context.py     # eShop RAG loader
│   │   ├── services/langfuse_service.py # LLM observability
│   │   └── services/notification_service.py
│   └── requirements.txt
├── frontend/src/
│   ├── pages/ReportPage.tsx             # Incident submission form
│   ├── pages/DashboardPage.tsx          # Live dashboard + severity filter
│   ├── pages/IncidentDetailPage.tsx     # Detail + streaming reasoning panel
│   └── api/client.ts                    # Typed API client
├── context-provider/ecommerce-repo/src/ # Microsoft eShop .NET source (RAG)
├── evidence/                            # Demo logs, screenshots, video
├── scripts/                             # DB seed + resolve helpers
├── docker-compose.yml
├── AGENTS_USE.md                        # Hackathon agent documentation
└── QUICKGUIDE.md                        # 5-minute setup guide
```

---

## License

MIT — see [LICENSE](LICENSE)
