# Quick Guide — AgentX SRE-Triage

Get the full system running in under 5 minutes.

---

## Prerequisites

- **Docker Desktop** — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop) (must be running)
- **Gemini API key** — free tier at [ai.google.dev](https://ai.google.dev/) (gemini-2.5-flash works on free tier)
- **Langfuse account** — free at [us.cloud.langfuse.com](https://us.cloud.langfuse.com) (create a project, copy keys)

---

## Step 1 — Clone

```bash
git clone https://github.com/cszdiego/AgentX-SRE-Triage-Autonomous-Incident-Response-with-Gemini.git
cd AgentX-SRE-Triage-Autonomous-Incident-Response-with-Gemini
```

---

## Step 2 — Configure secrets

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
GEMINI_API_KEY=AIzaSy...          # From ai.google.dev
GEMINI_MODEL=gemini-2.5-flash
LANGFUSE_SECRET_KEY=sk-lf-...     # From Langfuse project settings
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

> **Note:** The system works even if Langfuse keys are invalid — it falls back to local PostgreSQL tracing automatically.

---

## Step 3 — Start everything

```bash
docker compose up --build
```

First build takes ~3 minutes (downloads Python + Node images). Subsequent starts are instant.

**Ready when you see:**
```
sre_backend  | INFO:     Application startup complete.
```

---

## Step 4 — Open the app

| URL | What you'll find |
|-----|-----------------|
| http://localhost:3000 | **Dashboard** — all incidents, stats, severity filter |
| http://localhost:3000/report | **Report Incident** — submit text, log, image, or video |
| http://localhost:8000/docs | **API Docs** — Swagger UI for all endpoints |
| http://localhost:8000/health | **Health check** — DB + model status |

---

## Submitting Your First Incident

1. Go to **http://localhost:3000/report**
2. Fill in:
   - **Title:** `Checkout failure — Basket service 503, Redis connection refused`
   - **Description:** `Users can't complete purchases. Redis was restarted for maintenance but Basket.API never reconnected. ~500 orders/hour failing.`
   - **Reporter Email:** `john.doe@company.com`
   - **Environment:** `production`
3. Attach a file from `evidence/` — try `demo_log_checkout_failure.log` or `error_recording.mp4`
4. Click **SUBMIT INCIDENT REPORT**

You'll be redirected to the incident detail page immediately. The **Agent Reasoning** sidebar shows each AI step live. In ~10 seconds you'll see:
- Severity **P1 CRITICAL**
- Root cause referencing `RedisBasketRepository.cs`
- Runbook with numbered remediation steps
- Ticket `SRE-XXXX` created
- Slack + email notifications logged

---

## Stopping and Restarting

**Stop:**
```bash
Ctrl+C   # in the terminal running docker compose
```

**Restart (no rebuild needed):**
```bash
docker compose up
```

**Full reset (clears database):**
```bash
docker compose down -v
docker compose up --build
```

---

## Demo Artifacts

All files in `evidence/` are ready to attach during a demo:

| File | Use for |
|------|---------|
| `demo_log_checkout_failure.log` | Case 1 — Basket/Redis P1 |
| `identity_connection_refused.log` | Case 2 — Identity OOMKilled P2 |
| `demo_log_payment_errors.log` | Case 3 — RabbitMQ/Ordering P2 |
| `error_screenshot.png` | Multimodal image demo |
| `error_recording.mp4` | Multimodal video demo |
| `guardrail_blocked.json` | Security evidence |
| `deduplication_example.json` | Dedup evidence |

---

## Resolving a Ticket

From the incident detail page, click **RESOLVE TICKET** (appears after triage completes).  
The system marks the ticket resolved and sends an email notification to the original reporter.

Or via API (replace SRE-XXXX with actual key):
```bash
curl -X PATCH http://localhost:8000/api/v1/tickets/SRE-XXXX/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution_note": "Redis connection pool restored. Pod restarted."}'
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 413 Request Entity Too Large | Already handled — nginx limit set to 100MB |
| Triage hangs >30s | Check Gemini API key quota at [aistudio.google.com](https://aistudio.google.com) |
| Dashboard shows no incidents | Check backend logs: `docker compose logs backend` |
| Port 3000 in use | Change in `docker-compose.yml`: `"3001:80"` |
| Containers stopped | `docker compose up` (no `--build` needed) |
