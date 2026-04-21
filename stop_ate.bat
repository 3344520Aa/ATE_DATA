@echo off
echo Stopping Chip ATE Analysis System...

:: Kill backend and frontend processes (Node and Python)
echo Killing Backend and Frontend processes...
taskkill /F /FI "WINDOWTITLE eq ATE-Backend*" /T 2>nul
taskkill /F /FI "WINDOWTITLE eq ATE-Frontend*" /T 2>nul

:: Stop Docker infrastructure only
echo Stopping Docker infrastructure (DB + Redis)...
docker-compose stop db redis

echo System stopped successfully.
pause
