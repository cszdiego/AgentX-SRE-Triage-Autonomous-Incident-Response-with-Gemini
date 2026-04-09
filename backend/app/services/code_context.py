"""
eShop Code Context Provider.
Loads and indexes relevant source files from the eShop repository
so the triage agent can ground its analysis in real code.
"""
import os
import re
import logging
from typing import Optional
from app.core.config import get_settings
from app.core.database import fetchall, execute

logger = logging.getLogger(__name__)
settings = get_settings()

# Services in the eShop and their typical failure modes
ESHOP_SERVICES = {
    "Catalog.API": ["catalog", "product", "item", "inventory", "price", "stock"],
    "Basket.API": ["basket", "cart", "session", "redis", "checkout"],
    "Ordering.API": ["order", "payment", "purchase", "checkout", "order-processing"],
    "Identity.API": ["auth", "login", "token", "jwt", "user", "identity"],
    "WebApp": ["frontend", "web", "ui", "page", "render", "spa"],
    "EventBus": ["event", "message", "queue", "rabbitmq", "publish", "subscribe"],
    "PaymentProcessor": ["payment", "card", "stripe", "billing", "transaction"],
    "Webhooks.API": ["webhook", "callback", "notification"],
}

# Key files to index per service (relative to src/)
SERVICE_KEY_FILES = {
    "Catalog.API": [
        "Catalog.API/Program.cs",
        "Catalog.API/Apis/CatalogApi.cs",
        "Catalog.API/Model/CatalogItem.cs",
        "Catalog.API/Infrastructure/CatalogContext.cs",
    ],
    "Basket.API": [
        "Basket.API/Program.cs",
        "Basket.API/Repositories/RedisBasketRepository.cs",
        "Basket.API/Grpc/BasketService.cs",
    ],
    "Ordering.API": [
        "Ordering.API/Program.cs",
        "Ordering.API/Application/Commands/CreateOrderCommandHandler.cs",
        "Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs",
        "Ordering.Infrastructure/OrderingContext.cs",
    ],
    "Identity.API": [
        "Identity.API/Program.cs",
        "Identity.API/Services/ProfileService.cs",
    ],
    "WebApp": [
        "WebApp/Program.cs",
        "WebApp/Services/CatalogService.cs",
        "WebApp/Services/OrderingService.cs",
    ],
    "EventBus": [
        "EventBus/Events/IntegrationEvent.cs",
        "EventBusRabbitMQ/DefaultRabbitMQPersistentConnection.cs",
    ],
}


def get_relevant_context(incident_text: str, max_chars: int = 8000) -> str:
    """
    Given an incident description, return relevant eShop code snippets.
    Strategy:
    1. Check DB cache first
    2. Match service by keyword
    3. Load file snippets from disk
    4. Return formatted context
    """
    # Identify relevant service
    service = _identify_service(incident_text)
    logger.info("Identified affected service: %s", service)

    # Try DB cache
    cached = _get_from_db(service)
    if cached:
        return _format_context(cached, service, max_chars)

    # Load from disk
    snippets = _load_from_disk(service)
    if snippets:
        _cache_in_db(service, snippets)
        return _format_context(snippets, service, max_chars)

    # Fallback: general eShop architecture context
    return _fallback_context(service)


def _identify_service(text: str) -> str:
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for service, keywords in ESHOP_SERVICES.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        scores[service] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "Catalog.API"  # default
    return best


def _load_from_disk(service: str) -> list[dict]:
    base = settings.ESHOP_CONTEXT_PATH
    snippets = []
    files = SERVICE_KEY_FILES.get(service, [])

    for rel_path in files:
        full_path = os.path.join(base, rel_path)
        if os.path.exists(full_path):
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                snippets.append({
                    "file_path": rel_path,
                    "content": content[:3000],  # First 3k chars
                    "service_name": service,
                })
                logger.info("Loaded code context: %s (%d chars)", rel_path, len(content))
            except Exception as e:
                logger.warning("Could not read %s: %s", full_path, e)

    if not snippets:
        # Try to find any .cs file in the service directory
        svc_dir = os.path.join(base, service)
        if os.path.isdir(svc_dir):
            for root, _, files_list in os.walk(svc_dir):
                for fname in files_list[:5]:
                    if fname.endswith(".cs"):
                        fpath = os.path.join(root, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()
                            snippets.append({
                                "file_path": os.path.relpath(fpath, base),
                                "content": content[:2000],
                                "service_name": service,
                            })
                        except Exception:
                            pass

    return snippets


def _get_from_db(service: str) -> list[dict]:
    rows = fetchall(
        "SELECT file_path, content FROM code_context WHERE service_name = %s LIMIT 5",
        (service,),
    )
    return rows or []


def _cache_in_db(service: str, snippets: list[dict]):
    for s in snippets:
        try:
            execute(
                """
                INSERT INTO code_context (service_name, file_path, content)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (service, s["file_path"], s["content"]),
            )
        except Exception as e:
            logger.debug("Code context cache error: %s", e)


def _format_context(snippets: list[dict], service: str, max_chars: int) -> str:
    parts = [f"## eShop Code Context: {service}\n"]
    total = 0
    for s in snippets:
        chunk = f"\n### File: `{s['file_path']}`\n```csharp\n{s['content']}\n```\n"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts)


def _fallback_context(service: str) -> str:
    return f"""## eShop Architecture Reference: {service}

The eShop is a .NET microservices reference app with these services:
- **Catalog.API** — Product catalog (SQL Server + EF Core). Handles product queries, image serving, price management.
- **Basket.API** — Shopping cart (Redis). gRPC-based. Handles add/remove/checkout triggers.
- **Ordering.API** — Order processing (DDD, CQRS, MediatR). EventBus integration for saga pattern.
- **Identity.API** — OAuth2/OIDC via IdentityServer. JWT token issuance.
- **WebApp** — Blazor frontend. Consumes all APIs. SSR + WASM hybrid.
- **EventBus** — RabbitMQ-backed integration events for async communication.
- **PaymentProcessor** — Background worker that processes payment integration events.

Common failure patterns:
- DB connection pool exhaustion → Catalog/Ordering APIs timeout
- Redis unavailable → Basket API 503s
- RabbitMQ disconnect → OrderStarted events lost, orders stuck in "submitted" state
- IdentityServer token validation failure → 401 cascade across all services
- Catalog image volume mount issue → broken product images in WebApp
"""
