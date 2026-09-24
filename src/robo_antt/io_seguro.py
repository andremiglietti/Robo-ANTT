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


def adquirir_trava(checkpoint_path: Path, tentativas: int = 5, espera_segundos: float = 0.3) -> Path:
    """Cria um arquivo de trava (.lock) ao lado do checkpoint, impedindo 2
    execuções simultâneas usando o MESMO checkpoint - levanta
    ChecklistEmUsoError se já existir uma trava de um processo AINDA
    rodando. Se a trava for de um processo que já morreu (crash, kill
    manual, computador desligado no meio) sem limpar depois de si, remove
    a trava velha sozinho e segue em frente - não trava o robô pra sempre
    por causa de uma trava "fantasma".

    ⚠️ Revisão em 24/09/2026 (auditoria crítica pedida pelo usuário): a
    versão original fazia `trava.exists()` e só depois `trava.write_text(...)`
    - 2 passos separados, sem nada atômico entre eles (TOCTOU: 2 processos
    podiam passar pela checagem "não existe" quase juntos, e o 2º write
    sobrescrevia o 1º sem erro nenhum). Corrigido usando criação atômica
    (`os.open(..., O_CREAT | O_EXCL)`, que no SO só cria o arquivo se ele
    realmente não existir ainda, e falha com `FileExistsError` se outro
    processo criou primeiro) - só um dos processos concorrentes consegue
    criar o arquivo de verdade.

    Também corrigido: a versão original tratava QUALQUER trava com
    conteúdo ilegível (`ValueError`/`OSError` ao converter pra int) como
    "fantasma" e apagava na hora - mas um conteúdo ilegível também pode ser
    só a janela estreitíssima entre o processo concorrente ter CRIADO o
    arquivo e ainda não ter escrito o PID dentro - apagar nesse caso podia
    deixar os 2 processos pensando que têm a trava. Agora só apaga uma
    trava depois de CONFIRMAR (via `_processo_ainda_rodando`) que o PID
    gravado nela está morto de verdade - conteúdo ilegível vira uma
    retentativa curta (a suposição é que vai resolver sozinho em
    milissegundos), não uma remoção otimista.

    Chamar sempre em par com liberar_trava(), idealmente num try/finally
    que cubra a execução inteira (ver orquestrador.rodar())."""
    trava = checkpoint_path.with_name(checkpoint_path.name + ".lock")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    for tentativa in range(tentativas):
        try:
            fd = os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pid_antigo = _ler_pid_da_trava(trava)
            if pid_antigo is None:
                # conteúdo vazio/ilegível - provavelmente outro processo no
                # meio da própria criação (ver docstring acima) - espera um
                # pouco e tenta de novo, em vez de assumir "fantasma".
                if tentativa < tentativas - 1:
                    time.sleep(espera_segundos)
                continue
            if _processo_ainda_rodando(pid_antigo):
                raise ChecklistEmUsoError(
                    f"Já existe outra execução usando '{checkpoint_path.name}' agora mesmo "
                    f"(processo {pid_antigo} ainda rodando) - espere ela terminar antes de "
                    "rodar de novo com o mesmo worker/checkpoint. Se tiver certeza de que "
                    f"aquele processo já não existe mais (ex.: apagado sem querer), apague "
                    f"manualmente o arquivo '{trava.name}' e tente de novo."
                )
            trava.unlink(missing_ok=True)  # trava "fantasma" CONFIRMADA (PID morto) - remove e tenta de novo
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            return trava

    raise ChecklistEmUsoError(
        f"Não foi possível adquirir a trava de '{checkpoint_path.name}' depois de {tentativas} "
        f"tentativas - o arquivo '{trava.name}' continua num estado ambíguo (conteúdo ilegível "
        "que não resolveu sozinho). Verifique manualmente se há outro processo rodando antes de "
        "apagar esse arquivo."
    )


def _ler_pid_da_trava(trava: Path) -> int | None:
    try:
        return int(trava.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


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
