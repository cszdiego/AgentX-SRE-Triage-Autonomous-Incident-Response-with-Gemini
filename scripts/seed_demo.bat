@echo off
:: AgentX SRE-Triage — Demo Database Seeder
:: Run this ONCE before recording the video.
:: Requires: Docker Desktop running, containers up (docker compose up --build)

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  AgentX SRE-Triage — Demo Seed Script               ║
echo ║  Inserts 2 Catalog.API incidents + guardrail logs    ║
echo ╚══════════════════════════════════════════════════════╝
echo.

:: Check containers are running
docker ps --filter "name=sre_postgres" --filter "status=running" --format "{{.Names}}" | findstr "sre_postgres" >nul
if %errorlevel% neq 0 (
    echo [ERROR] sre_postgres container is not running.
    echo         Run: docker compose up --build
    echo         Wait for: sre_postgres ^| database system is ready
    pause
    exit /b 1
)

echo [1/3] Copying seed SQL into container...
docker cp "%~dp0seed_demo.sql" sre_postgres:/tmp/seed_demo.sql

echo [2/3] Running seed SQL...
docker exec sre_postgres psql -U sre_user -d sre_triage -f /tmp/seed_demo.sql

if %errorlevel% equ 0 (
    echo.
    echo [3/3] Generating error screenshot...
    docker exec sre_backend python /app/../scripts/generate_screenshot.py 2>nul
    :: Fallback: try from host if container path doesn't work
    python "%~dp0generate_screenshot.py" 2>nul
    echo.
    echo ✓ SEED COMPLETE — Dashboard should show 2 Catalog.API incidents
    echo   Open: http://localhost:3000
) else (
    echo [WARN] Seed may have partially run. Check output above.
    echo        If incidents already exist, that is OK - run is idempotent for guardrail_logs.
)

pause
