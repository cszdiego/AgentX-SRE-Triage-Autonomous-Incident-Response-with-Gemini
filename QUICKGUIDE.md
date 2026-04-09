# Quick Guide — AgentX SRE-Triage v1.2

Get the full system running in under 5 minutes.

---

## Prerequisites

- **Docker Desktop** — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop) (must be running)
- **Gemini API key** — free tier at [ai.google.dev](https://ai.google.dev/) (gemini-2.5-flash works on free tier)
- **Langfuse account** — free at [us.cloud.langfuse.com](https://us.cloud.langfuse.com) (create a project, copy keys)
- **Slack Incoming Webhook** — create at [api.slack.com/apps](https://api.slack.com/apps) → Your App → Incoming Webhooks
- **Jira API token** — create at [id.atlassian.com/manage-profile/security](https://id.atlassian.com/manage-profile/security) → API tokens
- **Gmail App Password** — enable 2FA, then generate at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)

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
# Required
GEMINI_API_KEY=AIzaSy...          # From ai.google.dev
GEMINI_MODEL=gemini-2.5-flash
LANGFUSE_SECRET_KEY=sk-lf-...     # From Langfuse project settings
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com

# Real Slack integration
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Real Jira integration
JIRA_SITE_URL=your-site.atlassian.net
JIRA_USER_EMAIL=your-email@example.com
JIRA_API_TOKEN=ATATT3x...
JIRA_PROJECT_KEY=SRE              # Your Jira project key prefix

# Gmail SMTP_SSL (real email delivery)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx  # 16-char App Password (no spaces)
SMTP_FROM=your-email@gmail.com
SRE_TEAM_EMAIL=your-team@example.com
```

> **Note:** Langfuse, Slack, Jira, and Gmail all fall back gracefully if not configured. The triage pipeline never fails due to a missing integration.

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
| http://localhost:8000/api/v1/health/metrics | **Live metrics** — incidents, tokens, guardrail blocks, Jira count |
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
- Internal ticket `SRE-XXXX` created
- **Jira issue created** (e.g., `KAN-42`) with a direct link in the UI
- **Slack alert** in `#sre-alerts` with severity, service, and Jira link
- **HTML email** delivered to the configured Gmail inbox (professional dark theme)

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
The system marks the ticket resolved and sends a resolution email to the original reporter (visible in Mailhog).

Or via API (replace `<ticket_id>` with the UUID from the incident detail):
```bash
curl -X PATCH http://localhost:8000/api/v1/tickets/<ticket_id>/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution_note": "Redis connection pool restored. Pod restarted."}'
```

---

## Live Metrics (for demo video close)

```bash
curl http://localhost:8000/api/v1/health/metrics | jq
```

Returns:
```json
{
  "incidents_total": 5,
  "incidents_last_24h": 3,
  "avg_triage_ms": 4200,
  "guardrail_blocks_total": 2,
  "jira_tickets_created": 3,
  "slack_delivered": 3,
  "email_delivered": 6,
  "tokens_input_total": 14500
}
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 413 Request Entity Too Large | Already handled — nginx limit set to 100MB |
| Triage hangs >30s | Check Gemini API key quota at [aistudio.google.com](https://aistudio.google.com) |
| Dashboard shows no incidents | Check backend logs: `docker compose logs backend` |
| Jira issue not created | Check `JIRA_API_TOKEN` and `JIRA_PROJECT_KEY` in `.env` — see backend logs for error details |
| Slack not receiving messages | Check `SLACK_WEBHOOK_URL` is a valid `https://hooks.slack.com/...` URL |
| Emails not arriving | Check `SMTP_USER`/`SMTP_PASSWORD` in `.env`. Verify Gmail App Password (not account password). Check spam folder. |
| Port 3000 in use | Change in `docker-compose.yml`: `"3001:80"` |
| Containers stopped | `docker compose up` (no `--build` needed) |
