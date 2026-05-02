@echo off
setlocal EnableExtensions
title FABOuanes - Build installateur Windows

set "PROJECT_ROOT=%~dp0..\.."
set "EXE_BUILDER=%~dp0COMPILER_EXE_AVEC_TESTS.bat"
set "ISS_FILE=%~dp0FABOuanes_Setup.iss"
set "ISCC_CMD="
set "CALLER_NO_PAUSE=%FAB_NO_PAUSE%"
set "FAB_NO_PAUSE=1"

cd /d "%PROJECT_ROOT%"
color 0B

echo.
echo  ==========================================
echo   FABOuanes - EXE puis installateur Windows
echo  ==========================================
echo.

call "%EXE_BUILDER%"
if errorlevel 1 (
    echo.
    echo  ERREUR: la construction de l'EXE a echoue.
    if not defined CALLER_NO_PAUSE pause
    exit /b 1
)

if not exist "dist\FABOuanes\FABOuanes.exe" (
    echo.
    echo  ERREUR: dist\FABOuanes\FABOuanes.exe est introuvable.
    if not defined CALLER_NO_PAUSE pause
    exit /b 1
)

where iscc.exe >nul 2>&1
if not errorlevel 1 set "ISCC_CMD=iscc.exe"
if not defined ISCC_CMD if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_CMD if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_CMD if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC_CMD (
    echo.
    echo  ERREUR: Inno Setup 6 est introuvable.
    echo  Installe Inno Setup 6 puis relance ce script.
    echo  Fichier attendu: ISCC.exe
    if not defined CALLER_NO_PAUSE pause
    exit /b 1
)

if not exist "installer_output" mkdir "installer_output" >nul 2>&1

echo.
echo  Compilation de l'installateur avec Inno Setup...
"%ISCC_CMD%" "%ISS_FILE%"
if errorlevel 1 (
    echo.
    echo  ERREUR: la creation de l'installateur a echoue.
    if not defined CALLER_NO_PAUSE pause
    exit /b 1
)

if not exist "installer_output\FABOuanes_Setup.exe" (
    echo.
    echo  ERREUR: installer_output\FABOuanes_Setup.exe introuvable.
    if not defined CALLER_NO_PAUSE pause
    exit /b 1
)

echo.
echo  ==========================================
echo   SUCCES !  installer_output\FABOuanes_Setup.exe
echo  ==========================================
echo.
if not defined CALLER_NO_PAUSE pause
endlocal
