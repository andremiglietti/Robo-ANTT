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

REM --- Passo 1: localizar um Python 3.13 REAL ja instalado, se houver ---
REM 29/09/2026, achado ao vivo noutro computador: o Windows costuma ter
REM um "python"/"py" no PATH que na verdade e so um atalho da Microsoft
REM Store (pasta AppData\Local\Microsoft\WindowsApps\...) - ele responde
REM "3.13" no --version, mas e uma instalacao incompleta, sem
REM pythonw.exe, e o "python -m venv" quebra com um erro tecnico
REM confuso. A checagem agora confirma que existe um pythonw.exe de
REM verdade do lado do python.exe encontrado, nao so a versao - se nao
REM tiver, trata como "nao encontrado" e tenta instalar uma versao
REM completa (mesmo fluxo de sempre).
set PYEXE=
py -3.13 -c "" >nul 2>&1
if errorlevel 1 goto :tentar_python_generico
set PYEXE=py -3.13
call :tem_pythonw_de_verdade
if not errorlevel 1 goto :python_ok

:tentar_python_generico
python --version 2>&1 | findstr /C:"3.13" >nul
if errorlevel 1 goto :python_nao_encontrado
set PYEXE=python
call :tem_pythonw_de_verdade
if not errorlevel 1 goto :python_ok

:python_nao_encontrado
echo Nao encontramos uma instalacao completa do Python 3.13 neste
echo computador (se houver uma versao da Microsoft Store, ela nao
echo funciona para este programa).
echo Tentando instalar automaticamente a versao completa (isso pode
echo levar alguns minutos)...
echo.
where winget >nul 2>&1
if errorlevel 1 goto :sem_winget

REM --source winget forca a fonte oficial (Python Software Foundation),
REM nao a Microsoft Store, que e a origem provavel do problema acima.
winget install --id Python.Python.3.13 -e --source winget --silent --scope user --accept-package-agreements --accept-source-agreements
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

REM Confirma que o ambiente recem-criado funciona de verdade (nao so que
REM os arquivos foram criados) - pega qualquer problema aqui, cedo e com
REM mensagem clara, em vez de descobrir so no final tentando abrir o
REM programa.
".venv\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERRO: o ambiente criado nao funciona corretamente. Copie esta
    echo mensagem e envie para o suporte tecnico ^(Andre Miglietti^).
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
exit /b 0

REM Sub-rotina (so chamada via "call") - confirma que o Python encontrado
REM em PYEXE e um Python de verdade, nao o atalho incompleto da
REM Microsoft Store (pasta ...\WindowsApps\...).
REM
REM 29/09/2026, achado ao vivo em 2 computadores diferentes: a 1a versao
REM dessa checagem so confirmava que um "pythonw.exe" existe do lado do
REM python.exe encontrado - nao bastou, porque a Microsoft Store deixa
REM um ARQUIVO "pythonw.exe" de mentira la (um atalho/placeholder do
REM Windows, existe no disco mas nao funciona de verdade) - a checagem
REM de existencia sozinha aceitava esse atalho por engano, o "venv" era
REM criado apontando pra ele, e o erro so aparecia DEPOIS, tentando abrir
REM o programa de verdade ("Python venv launcher is sorry to say...").
REM Corrigido: agora tambem rejeita explicitamente qualquer Python cujo
REM caminho contenha "WindowsApps" - o sinal mais direto e confiavel de
REM que e o atalho da Store, nao uma instalacao completa.
:tem_pythonw_de_verdade
%PYEXE% -c "import sys, os; exe = sys.executable; pyw = os.path.join(os.path.dirname(exe), 'pythonw.exe'); ok = os.path.exists(pyw) and 'windowsapps' not in exe.lower(); sys.exit(0 if ok else 1)" >nul 2>&1
exit /b %errorlevel%
