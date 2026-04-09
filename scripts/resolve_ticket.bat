@echo off
:: AgentX SRE-Triage — Resolve Ticket Script
:: Usage: resolve_ticket.bat SRE-1000
:: Or run without args to resolve the latest in_progress ticket.
::
:: This calls PATCH /api/v1/tickets/{key}/resolve
:: which: updates status=resolved, fires reporter email notification (Stage 5).

set TICKET_KEY=%1
set API_BASE=http://localhost:8000/api/v1

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  AgentX SRE-Triage — Resolve Ticket                 ║
echo ╚══════════════════════════════════════════════════════╝
echo.

if "%TICKET_KEY%"=="" (
    echo [INFO] No ticket key provided. Looking up latest in_progress ticket...
    echo.
    curl -s "%API_BASE%/tickets?status=in_progress&limit=1" | python -c "import sys,json; data=json.load(sys.stdin); t=data[0] if data else None; print(t['ticket_key'] if t else 'NONE')" > tmp_key.txt
    set /p TICKET_KEY=<tmp_key.txt
    del tmp_key.txt
    if "%TICKET_KEY%"=="NONE" (
        echo [ERROR] No in_progress tickets found. Submit an incident first.
        pause
        exit /b 1
    )
    echo [INFO] Found ticket: %TICKET_KEY%
)

echo [RESOLVING] Ticket: %TICKET_KEY%
echo.

curl -s -X PATCH ^
  "%API_BASE%/tickets/%TICKET_KEY%/resolve" ^
  -H "Content-Type: application/json" ^
  -d "{\"resolution_note\": \"Redis connection pool restored. Basket.API reconnected. All checkouts operational. Runbook step 3 applied: FLUSHDB on the dead session pool and pod restart.\"}" ^
  | python -m json.tool

echo.
echo ✓ Ticket %TICKET_KEY% marked RESOLVED
echo   → Reporter notification sent (check Dashboard → Notifications section)
echo   → Stage 5 (resolve) trace logged to Langfuse
echo.
pause
