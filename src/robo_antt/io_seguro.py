"""
Gravação segura de arquivos em pastas sincronizadas com o OneDrive/SharePoint
(ver CLAUDE.md, "Cuidado técnico na gravação").

Usado por checkpoint.py e planilha.py, que gravam do mesmo jeito: escrevem
num arquivo temporário primeiro e só then trocam pelo arquivo final, pra
nunca deixar a pasta com um arquivo pela metade caso o OneDrive tente
sincronizar no meio da escrita.
"""
import os
import subprocess
import time
from pathlib import Path


def substituir_com_retentativa(origem: Path, destino: Path, tentativas: int = 5, espera_segundos: float = 1.0) -> None:
    """Troca `origem` por `destino` (`Path.replace()`), com retentativa
    curta em caso de `PermissionError`.

    ⚠️ Achado ao vivo em 18-19/09/2026: numa execução de ~4h30 (751
    documentos processados), o worker parou com
    `[WinError 5] Access is denied` bem nesse `replace()`. Causa provável:
    o projeto inteiro mora dentro de uma pasta sincronizada pelo OneDrive
    (`Desktop\\Robo-ANTT`) - então até `data/output/` (checkpoint,
    planilhas-fatia dos workers), que devia ser só local, acaba sendo
    sincronizado também. Depois de centenas de gravações ao longo de
    várias horas, é bem provável que o OneDrive tenha segurado o arquivo
    (escaneando/subindo) bem na hora do `replace()`. Esse tipo de trava
    costuma ser passageiro (resolve sozinho em segundos) - por isso
    retentativa curta em vez de desistir na primeira falha, que derrubava a
    execução inteira por causa de um lock temporário de terceiros.
    """
    for tentativa in range(tentativas):
        try:
            origem.replace(destino)
            return
        except PermissionError:
            if tentativa == tentativas - 1:
                raise
            time.sleep(espera_segundos)


class ChecklistEmUsoError(Exception):
    """Já existe outro processo usando este mesmo checkpoint (mesmo
    worker) agora mesmo - ver adquirir_trava().

    ⚠️ Achado ao vivo em 22/09/2026: rodando a IHM (scripts/executar_robo.py)
    e uma varredura sequencial manual ao mesmo tempo, os dois acabaram
    usando o MESMO checkpoint_worker_0.json/planilha_worker_0.xlsx (a IHM
    sempre começa pelo worker 0, e não havia nada que detectasse ou
    impedisse isso) - 2 processos escrevendo no mesmo arquivo, um risco
    real de perder progresso (identificado e encerrado a tempo naquela
    vez, sem dano, mas por pouco - ver CLAUDE.md). Essa trava existe pra
    isso nunca mais depender de alguém perceber a tempo."""


def adquirir_trava(checkpoint_path: Path) -> Path:
    """Cria um arquivo de trava (.lock) ao lado do checkpoint, impedindo 2
    execuções simultâneas usando o MESMO checkpoint - levanta
    ChecklistEmUsoError se já existir uma trava de um processo AINDA
    rodando. Se a trava for de um processo que já morreu (crash, kill
    manual, computador desligado no meio) sem limpar depois de si, remove
    a trava velha sozinho e segue em frente - não trava o robô pra sempre
    por causa de uma trava "fantasma".

    Chamar sempre em par com liberar_trava(), idealmente num try/finally
    que cubra a execução inteira (ver orquestrador.rodar())."""
    trava = checkpoint_path.with_name(checkpoint_path.name + ".lock")
    if trava.exists():
        pid_antigo = None
        try:
            pid_antigo = int(trava.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pass
        if pid_antigo and _processo_ainda_rodando(pid_antigo):
            raise ChecklistEmUsoError(
                f"Já existe outra execução usando '{checkpoint_path.name}' agora mesmo "
                f"(processo {pid_antigo} ainda rodando) - espere ela terminar antes de "
                "rodar de novo com o mesmo worker/checkpoint. Se tiver certeza de que "
                f"aquele processo já não existe mais (ex.: apagado sem querer), apague "
                f"manualmente o arquivo '{trava.name}' e tente de novo."
            )
        trava.unlink(missing_ok=True)  # trava "fantasma" de um processo que já morreu - remove e segue
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    trava.write_text(str(os.getpid()), encoding="utf-8")
    return trava


def liberar_trava(trava: Path) -> None:
    trava.unlink(missing_ok=True)


def _processo_ainda_rodando(pid: int) -> bool:
    """Confere se um PID ainda existe de verdade no Windows.

    ⚠️ Não dá pra usar `os.kill(pid, 0)` aqui, do jeito que se faz no
    Linux/Mac pra só testar existência sem matar nada - no Windows, a
    implementação de os.kill() pra qualquer sinal que não seja CTRL_C/
    CTRL_BREAK chama TerminateProcess() de verdade, ou seja, sinal 0
    MATARIA o processo em vez de só checar se ele existe (gotcha conhecido
    da stdlib do Python no Windows). Usa `tasklist` em vez disso."""
    resultado = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"],
        capture_output=True,
        text=True,
    )
    return str(pid) in resultado.stdout
