@echo off
echo Starting financial data pipeline...

echo Running data transformer...
python data_transformer.py
if %ERRORLEVEL% NEQ 0 (
    echo Error in data transformer
    exit /b 1
)

echo Pipeline completed successfully.
