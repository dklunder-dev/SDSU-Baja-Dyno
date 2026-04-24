@echo off
cd /d "%~dp0"

start cmd /k python serial_logger.py
start cmd /k python -m streamlit run dyno_dashboard.py