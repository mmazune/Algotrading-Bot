@echo off
chcp 65001 > nul
setlocal

    REM Change directory to your project folder
    cd /d "C:\Users\user\OneDrive\Desktop\Algotrading_Bot"
    REM ^^^ IMPORTANT: Replace "C:\Users\YourUser\OneDrive\Desktop\Algotrading_Bot" with YOUR actual full path to your Algotrading_Bot folder

    REM Set environment variables for this session.
    REM These values MUST match exactly what you set in your Windows Environment Variables.
    REM This is crucial because Task Scheduler's environment might not inherit all user variables.
    set FINNHUB_API_KEY="YOUR_FINNHUB_KEY_HERE"
    set TWELVEDATA_API_KEY="YOUR_TWELVEDATA_KEY_HERE"
    set MINIO_ENDPOINT="http://localhost:9000"
    set MINIO_ACCESS_KEY="YOUR_MINIO_ACCESS_KEY_HERE"
    set MINIO_SECRET_KEY="YOUR_MINIO_SECRET_KEY_HERE"

    REM ^^^ IMPORTANT: Replace YOUR_..._HERE with your actual keys/credentials.
    REM ^^^ If your MinIO keys were "minioadmin", use "minioadmin" (with quotes as shown).
    REM ^^^ You can adjust MINIO_ENDPOINT if your MinIO instance is not on localhost:9000.

    REM --- Run the Data Collector Script ---
    echo.
    echo Running main_data_collector.py...
    "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe" main_data_collector.py >> pipeline_log.txt 2>&1
    REM ^^^ IMPORTANT: Replace "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"
    REM ^^^ with the actual full path to your Python executable (e.g., from where you installed Python).
    REM ^^^ The `>> pipeline_log.txt 2>&1` part redirects all output (stdout and stderr) to a log file.

    REM Check if the collector ran successfully (basic check based on exit code)
    if %errorlevel% neq 0 (
        echo Error: main_data_collector.py failed. Check pipeline_log.txt for details.
        goto :eof
    ) else (
        echo main_data_collector.py completed successfully.
    )

    REM Small delay before running the transformer to ensure files are written
    timeout /t 10 /nobreak >nul

    REM --- Run the Data Transformer Script ---
    echo.
    echo Running data_transformer.py...
    "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe" data_transformer.py >> pipeline_log.txt 2>&1
    REM ^^^ IMPORTANT: Replace "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"
    REM ^^^ with the actual full path to your Python executable.

    REM Check if the transformer ran successfully
    if %errorlevel% neq 0 (
        echo Error: data_transformer.py failed. Check pipeline_log.txt for details.
        goto :eof
    ) else (
        echo data_transformer.py completed successfully.
    )

    echo.
    echo Pipeline finished.

endlocal
