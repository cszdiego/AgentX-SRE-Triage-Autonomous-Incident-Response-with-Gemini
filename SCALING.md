# SCALING.md — AgentX SRE-Triage v1.1

## Current Architecture Capacity

| Component | Current Config | Estimated Capacity |
|-----------|---------------|-------------------|
| FastAPI backend | 2 Uvicorn workers | ~200 req/s (non-AI) |
| Triage pipeline | Async background tasks | ~10-20 concurrent triages |
| PostgreSQL | Single instance | ~5,000 incidents/day |
| Gemini API | Free/pay-as-you-go | Subject to quota (60 req/min free) |
| File uploads | Local volume | Disk-bound (~100GB default) |

---

## Bottlenecks Identified

### 1. Gemini API Rate Limits (Primary Bottleneck)
- **Problem:** Gemini free tier allows ~60 requests/minute. Each triage = 1 multimodal request.
- **Impact:** At >1 incident/second, new requests queue behind the rate limit.
- **Current mitigations (already implemented):**
  - `202 Accepted` pattern: HTTP response is immediate; triage runs in background — no user-facing timeout
  - **Dedup suppression:** Duplicate incidents detected in Stage 2 skip the Gemini call entirely (0 tokens spent)
  - **Fallback model:** On `RESOURCE_EXHAUSTED` / 429 errors, the pipeline automatically retries with `gemini-2.0-flash`
  - **Rate limiting on `/incidents`:** SlowAPI limits intake to 10 req/min per IP, preventing burst overload
- **Stage 2 mitigation:** Rotate across multiple Gemini API keys with round-robin load balancing
- **Stage 3 mitigation:** Decouple via message queue — worker pods consume at Gemini's rate regardless of API traffic spikes

### 2. Single PostgreSQL Instance
- **Problem:** No read replicas. All reads/writes go to one instance.
- **Impact:** At high volume, DB becomes the bottleneck for dashboard queries.
- **Mitigation:** Indexes on `status`, `severity`, `created_at`. Dashboard queries use aggregates.

### 3. Synchronous Code Context Loading
- **Problem:** First triage for each service loads files from disk, subsequent ones use DB cache.
- **Impact:** Cold start latency of ~200-500ms for the first incident per service.
- **Mitigation:** DB caching after first load. Pre-indexing script available.

---

## Horizontal Scaling Plan

### Stage 1: Current (MVP)
```
Browser → Nginx → FastAPI (2 workers) → PostgreSQL
                     ↓
                 Gemini API
```

### Stage 2: Medium Load (10-50 incidents/min)
```
Browser → CDN → Nginx LB
                   ↓
         FastAPI × 4 instances
                   ↓
    PostgreSQL (primary + 1 read replica)
                   ↓
    Gemini API (paid tier, higher quota)
```
Changes needed:
- Add `replicas: 4` to backend service in docker-compose
- Add PgBouncer for connection pooling
- Add Redis for session/dedup caching

### Stage 3: High Load (100+ incidents/min)
```
Browser → CDN → API Gateway (Kong/Traefik)
                       ↓
             Kubernetes Deployment (auto-scaling)
             ├── API pods (HPA: 2-20 replicas)
             └── Worker pods (triage queue consumers)
                       ↓
              Message Queue (RabbitMQ / AWS SQS)
                       ↓
              PostgreSQL (RDS Multi-AZ + read replicas)
              Redis (ElastiCache) — dedup & caching
```

Key changes:
- Decouple API (accept incident) from Worker (run triage) via message queue
- This decoupling means the API pod load is independent of AI processing time
- Workers scale based on queue depth, not API traffic

---

## Queue-Based Architecture (Stage 3 Detail)

```python
# API pod: fast, stateless
POST /incidents → validate → write to DB → publish to queue → return 202

# Worker pod: slow, AI-intensive
consume queue → run Gemini triage → update DB → send notifications
```

Benefits:
- API response time: <50ms (no AI latency)
- Workers scale independently (Gemini quota = constraint, not pods)
- Failed triages auto-retry via queue dead-letter queue
- Zero dropped incidents during traffic spikes

---

## File Storage Scaling

| Stage | Solution | Capacity |
|-------|----------|----------|
| Current | Docker volume (local disk) | Host disk limit |
| Medium | NFS shared volume | Multi-host compatible |
| Production | AWS S3 / GCS / Azure Blob | Unlimited |

For S3 migration, change `UPLOAD_DIR` to an S3 bucket path and add `boto3` + `python-multipart` S3 upload handler.

---

## Database Scaling Assumptions

1. **Incident volume:** Baseline assumption of ~500 incidents/day for a mid-size e-commerce team.
2. **Retention:** Incidents retained indefinitely (no archival policy in MVP). Add partition by month at Scale Stage 2.
3. **Attachment storage:** Separate from relational DB; scale independently via object storage.
4. **Dedup window:** 48-hour rolling window. Scales linearly with incident volume; index on `created_at` keeps query fast.

---

## Gemini API Cost Projections

| Volume | Requests/day | Estimated tokens/request | Monthly cost (Gemini 2.0 Flash) |
|--------|-------------|--------------------------|--------------------------------|
| Low (MVP) | 50 | ~3,000 | ~$0.10 |
| Medium | 500 | ~3,000 | ~$1.00 |
| High | 5,000 | ~3,000 | ~$10.00 |

*Gemini 2.0 Flash pricing: ~$0.075/1M input tokens, $0.30/1M output tokens (as of April 2026)*

---

## Observability at Scale

- **Langfuse** handles distributed tracing natively (no changes needed for horizontal scaling)
- **`/api/v1/health/metrics`** endpoint exposes structured JSON metrics: incidents processed, avg triage time, guardrail blocks, Jira tickets created, Slack/email delivery counts
- Add **Prometheus** metrics via `prometheus-fastapi-instrumentator` for pod-level metrics
- Add **Grafana** dashboard for real-time incident pipeline throughput
- Alert on: queue depth > 100, triage failure rate > 5%, P1 incident not triaged within 30s

---

## Real Integration Bottlenecks (v1.1 — Live Integrations)

With real Slack, Jira, and SMTP now enabled, two additional bottlenecks emerge:

| Integration | Limit | Current Handling |
|-------------|-------|-----------------|
| Slack Webhooks | 1 req/s per channel | Fire-and-forget in background; failure logged, pipeline continues |
| Jira REST API | 10 req/s (Cloud) | Single call per incident; failure logged, local ticket still created |
| SMTP (Mailhog/prod) | Mailhog: unlimited; prod SMTP: provider-dependent | Failure logged, DB record marks status='failed' for retry |

All external calls use try/except isolation — a Jira timeout or Slack 429 never blocks the triage pipeline.
