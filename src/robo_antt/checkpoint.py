"""
Estado persistente entre execuções do robô (ver CLAUDE.md, item 6 da
arquitetura): quais autos já foram processados com sucesso, e quais
falharam (pra tentar de novo na próxima execução, sem reprocessar os que já
deram certo). Guarda também a lista de falhas com o motivo, pra quem for
olhar depois entender o que precisa de atenção manual.

Isso é sobre falhas de DOCUMENTO específico (ex.: PDF não abriu, campo não
extraiu). Falha de sessão/infraestrutura (SessaoExpiradaError,
PortalIndisponivelError) não entra aqui - o orquestrador para a execução
inteira nesse caso, sem marcar nada como "falha", porque não é culpa do
documento.
"""
import json
from datetime import datetime
from pathlib import Path

from robo_antt.config import OUTPUT_DIR

CHECKPOINT_FILE = OUTPUT_DIR / "checkpoint.json"


def carregar() -> dict:
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    return {"processados": [], "falhas": {}, "ultima_execucao": None}


def salvar(estado: dict) -> None:
    """Mesmo cuidado de gravação das outras saídas (arquivo temporário +
    troca), já que essa pasta também pode ficar sincronizada com o SharePoint."""
    estado["ultima_execucao"] = datetime.now().isoformat(timespec="seconds")
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    caminho_tmp = CHECKPOINT_FILE.with_name(f"_tmp_{CHECKPOINT_FILE.name}")
    caminho_tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    caminho_tmp.replace(CHECKPOINT_FILE)


def ja_processado(estado: dict, auto_infracao: str) -> bool:
    return auto_infracao in estado["processados"]


def marcar_processado(estado: dict, auto_infracao: str) -> None:
    if auto_infracao not in estado["processados"]:
        estado["processados"].append(auto_infracao)
    estado["falhas"].pop(auto_infracao, None)  # se tinha falhado antes e agora deu certo, tira da lista de falhas


def marcar_falha(estado: dict, auto_infracao: str, motivo: str) -> None:
    estado["falhas"][auto_infracao] = motivo
