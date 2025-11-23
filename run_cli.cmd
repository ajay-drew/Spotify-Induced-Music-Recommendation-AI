@echo off
setlocal

rem SIMRAI CLI helper for Windows.
rem
rem Usage:
rem   run_cli.cmd "<mood text>" [--length N] [--intense] [--soft]
rem
rem Example:
rem   run_cli.cmd "rainy midnight drive with someone you miss" --soft --length 15
rem
rem Requirements:
rem   - In this repo: pip install -e .

cd /d "%~dp0"

if "%~1"=="" (
  echo Usage: %~n0 "mood text" [--length N] [--intense] [--soft]
  echo.
  echo Example:
  echo   %~n0 "rainy midnight drive with someone you miss" --soft --length 15
  goto :eof
)

echo SIMRAI CLI :: running ^"simrai queue^" with arguments: %*
echo.

simrai queue %*

endlocal


