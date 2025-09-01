@echo off
echo Starting MindAgent API...
cd /d %~dp0\..
call .venv\Scripts\activate
uvicorn mind.api:app --host 0.0.0.0 --port 8000 --reload
 
