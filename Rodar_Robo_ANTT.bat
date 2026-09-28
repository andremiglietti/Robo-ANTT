@echo off
setlocal
REM Atalho de execucao do robo ANTT - de clique duplo (Dia 12 do
REM cronograma, ver CLAUDE.md). Abre a IHM grafica (Tkinter,
REM scripts/executar_robo_gui.py).
REM
REM 28/09/2026, pedido do usuario ("as pessoas que vao usar sao muito
REM leigas"): este MESMO atalho agora tambem faz a instalacao automatica
REM na 1a vez que roda num computador novo (Python, ambiente virtual,
REM bibliotecas, navegador do robo) - a pessoa nao precisa saber o que
REM e nenhuma dessas coisas, so dar 2 cliques e esperar. Depois da 1a
REM vez, .venv ja existe e o atalho pula direto pra abrir o programa,
REM exatamente como sempre funcionou (pythonw.exe, sem janela preta).
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto :abrir

REM ===================== Primeira vez neste computador =====================
echo ============================================================
echo   Robo ANTT - preparando o programa neste computador (1a vez)
echo   Isso pode levar alguns minutos. Nao feche esta janela.
echo   (Da proxima vez, o programa abre direto, sem essa espera.)
echo ============================================================
echo.

REM --- Passo 1: localizar o Python 3.13 ja instalado, se houver ---
set PYEXE=
py -3.13 -c "" >nul 2>&1
if not errorlevel 1 (
    set PYEXE=py -3.13
    goto :python_ok
)
python --version 2>&1 | findstr /C:"3.13" >nul
if not errorlevel 1 (
    set PYEXE=python
    goto :python_ok
)

echo O Python 3.13 nao foi encontrado neste computador.
echo Tentando instalar automaticamente (isso pode levar alguns minutos)...
echo.
where winget >nul 2>&1
if errorlevel 1 goto :sem_winget

winget install --id Python.Python.3.13 -e --silent --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :sem_winget

echo.
echo O Python foi instalado agora. Por seguranca, feche esta janela e
echo clique de novo no atalho "Rodar_Robo_ANTT" para continuar a
echo preparacao do programa.
pause
exit /b 0

:sem_winget
echo.
echo Nao foi possivel instalar o Python automaticamente neste computador.
echo Siga estes passos (uma unica vez):
echo   1. Uma pagina de download vai abrir no navegador.
echo   2. Baixe e execute o instalador do Windows (versao 3.13).
echo   3. Na PRIMEIRA tela do instalador, MARQUE a caixa
echo      "Add python.exe to PATH" antes de continuar.
echo   4. Depois de instalar, clique de novo neste atalho
echo      "Rodar_Robo_ANTT" para continuar.
start "" https://www.python.org/downloads/
pause
exit /b 1

:python_ok
echo Python encontrado - continuando a preparacao...
echo.

REM --- Passo 2: criar o ambiente do programa ---
echo Criando o ambiente do programa...
%PYEXE% -m venv .venv
if errorlevel 1 (
    echo.
    echo ERRO ao criar o ambiente do programa. Copie esta mensagem e envie
    echo para o suporte tecnico ^(Andre Miglietti^).
    pause
    exit /b 1
)

REM --- Passo 3: instalar os componentes necessarios ---
echo Instalando os componentes necessarios ^(pode levar alguns minutos^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO ao instalar os componentes necessarios. Verifique a conexao
    echo com a internet e clique de novo no atalho. Se persistir, copie
    echo esta mensagem e envie para o suporte tecnico ^(Andre Miglietti^).
    pause
    exit /b 1
)

REM --- Passo 4: instalar o navegador usado pelo robo ---
echo Baixando o navegador usado pelo robo ^(pode levar alguns minutos^)...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
    echo.
    echo ERRO ao baixar o navegador do robo. Verifique a conexao com a
    echo internet e clique de novo no atalho. Se persistir, copie esta
    echo mensagem e envie para o suporte tecnico ^(Andre Miglietti^).
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Preparacao concluida! Abrindo o programa...
echo ============================================================
timeout /t 2 >nul

:abrir
if not exist ".venv\Scripts\pythonw.exe" (
    echo.
    echo ERRO: o programa nao foi preparado corretamente neste computador
    echo ^(arquivo esperado nao encontrado^). Copie esta mensagem e envie
    echo para o suporte tecnico ^(Andre Miglietti^).
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "scripts\executar_robo_gui.py"
