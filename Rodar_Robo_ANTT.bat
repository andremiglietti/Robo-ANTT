@echo off
REM Atalho de execucao do robo ANTT - de clique duplo (Dia 12 do
REM cronograma, ver CLAUDE.md). So chama scripts/executar_robo.py dentro
REM do ambiente virtual ja configurado - nao precisa saber nada de Python
REM ou terminal pra usar isso.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python scripts\executar_robo.py
echo.
echo Pressione qualquer tecla para fechar esta janela...
pause >nul
