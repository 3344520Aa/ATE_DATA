@echo off
echo ===================================================
echo   Chip ATE Analysis System - Development Startup
echo ===================================================

:: 1. Start Infrastructure only (DB + Redis)
echo [1/3] Starting Docker infrastructure (DB + Redis)...
docker-compose up -d db redis
if %errorlevel% neq 0 (
    echo [ERROR] Failed to start Docker Compose. Please make sure Docker Desktop is running.
    pause
    exit /b %errorlevel%
)

:: 2. Start Backend
echo [2/3] Starting Backend (FastAPI)...
start "ATE-Backend" cmd /c "cd /d %~dp0backend && set PYTHONPATH=.&& venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

:: 3. Start Frontend
echo [3/3] Starting Frontend (Vue/Vite)...
start "ATE-Frontend" cmd /c "cd /d %~dp0frontend && npx vite --host 0.0.0.0 --port 5173"

:: 4. Open Browser
echo.
echo ===================================================
echo   System is starting! 
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo ===================================================
echo.
echo Press any key to stop the infrastructure (Docker containers)...
pause

echo Stopping Docker containers...
docker-compose stop db redis
echo Done.
