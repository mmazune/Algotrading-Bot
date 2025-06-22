@echo off
echo Checking Python installation...
python --version 2>nul || (
    echo Python is not installed or not in PATH
    echo Please install Python and try again
    exit /b 1
)

echo Installing/Updating dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if %ERRORLEVEL% NEQ 0 (
    echo Error installing dependencies
    exit /b 1
)

echo Setup completed successfully.
