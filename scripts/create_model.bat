@echo off
cd /d %%~dp0..
ollama create mindagent-phi -f .\Modelfile
echo Model created! Use 'ollama run mindagent-phi' to test
pause
