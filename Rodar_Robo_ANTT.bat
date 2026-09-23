@echo off
REM Atalho de execucao do robo ANTT - de clique duplo (Dia 12 do
REM cronograma, ver CLAUDE.md). Abre a IHM grafica (Tkinter,
REM scripts/executar_robo_gui.py) - decisao de 23/09/2026 de trocar o
REM terminal simples por uma janela de verdade. Usa pythonw.exe (sem
REM console) pra nao deixar uma janela preta atras da interface grafica.
cd /d "%~dp0"
start "" .venv\Scripts\pythonw.exe scripts\executar_robo_gui.py
