@echo off
cd /d "%~dp0"

REM Charger .env
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        echo %%A | findstr /b "#" >nul || set "%%A=%%B"
    )
)

REM Activer Anaconda et lancer le scan
call C:\Users\e.morterol\AppData\Local\anaconda3\Scripts\activate.bat
python app.py
