@echo off
REM ---------------------------------------------------------------
REM  Double-click to run the 3-scenario demo with a LOCAL model.
REM  1) Install Ollama, then run once:   ollama pull qwen3:8b
REM  2) If you pulled a different model, change MODEL below.
REM  Other uses (open a terminal in this folder):
REM      run_demo.bat --chat        chat with the patient agent
REM      run_demo.bat --compare     rule-based comparison, no AI needed
REM ---------------------------------------------------------------
set MODEL=qwen3:8b

set MOCK_LLM=0
set LLM_BASE_URL=http://localhost:11434/v1
set FAST_MODEL=%MODEL%
set REASONING_MODEL=%MODEL%
set LLM_TIMEOUT=180

if "%~1"=="" (
    python main.py --reset
) else (
    python main.py %*
)
pause
