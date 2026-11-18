@echo off
start "" /wait "%~dp0MailPilot.exe" enable
if errorlevel 1 exit /b 1
start "" "%~dp0MailPilot.exe"
