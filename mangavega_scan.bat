@echo off
cd /d "%~dp0"
echo ============================================
echo   MangaVega Tracker V7
echo ============================================
echo.

REM Charger les variables depuis le fichier .env (s'il existe)
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        REM Ignorer les commentaires (lignes commençant par #)
        echo %%A | findstr /b "#" >nul || set "%%A=%%B"
    )
    echo   .env charge
) else (
    echo   ATTENTION : fichier .env introuvable !
    echo   Creez-le en copiant .env.example :
    echo     copy .env.example .env
    echo   Puis remplissez votre token dedans.
    echo.
    pause
    exit /b 1
)

REM Activer Anaconda
call C:\Users\e.morterol\AppData\Local\anaconda3\Scripts\activate.bat

echo   Demarrage du scan...
echo.

python app.py

echo.
echo ============================================
echo   Scan termine
echo ============================================
pause
