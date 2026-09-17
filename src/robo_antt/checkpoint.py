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


def carregar(caminho: Path = CHECKPOINT_FILE) -> dict:
    if caminho.exists():
        estado = json.loads(caminho.read_text(encoding="utf-8"))
        # setdefault - compatível com checkpoints salvos antes de 17/09/2026,
        # de quando esse campo ainda não existia (ver "varreduras_completas" abaixo)
        estado.setdefault("varreduras_completas", [])
        return estado
    return {"processados": [], "falhas": {}, "varreduras_completas": [], "ultima_execucao": None}


def salvar(estado: dict, caminho: Path = CHECKPOINT_FILE) -> None:
    """Mesmo cuidado de gravação das outras saídas (arquivo temporário +
    troca), já que essa pasta também pode ficar sincronizada com o SharePoint.

    `caminho` opcional (default = checkpoint único de sempre) - arquitetura
    de múltiplos workers (17/09/2026) passa o checkpoint próprio de cada
    worker aqui, pra nenhum processo escrever no mesmo arquivo que outro.
    """
    estado["ultima_execucao"] = datetime.now().isoformat(timespec="seconds")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho_tmp = caminho.with_name(f"_tmp_{caminho.name}")
    caminho_tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    caminho_tmp.replace(caminho)


def ja_processado(estado: dict, auto_infracao: str) -> bool:
    return auto_infracao in estado["processados"]


def marcar_processado(estado: dict, auto_infracao: str) -> None:
    if auto_infracao not in estado["processados"]:
        estado["processados"].append(auto_infracao)
    estado["falhas"].pop(auto_infracao, None)  # se tinha falhado antes e agora deu certo, tira da lista de falhas


def marcar_falha(estado: dict, auto_infracao: str, motivo: str) -> None:
    estado["falhas"][auto_infracao] = motivo


def marcar_varredura_completa(estado: dict, cnpj: str, tipo_value: str) -> None:
    """Registra que a paginação de um CNPJ+tipo foi percorrida até o fim de
    verdade (sem nenhuma exceção no meio) - garantia de completude pedida
    pelo usuário em 17/09/2026 (ver CLAUDE.md): documentos "aparecendo" numa
    reexecução do mesmo CNPJ eram, na verdade, varreduras que tinham parado
    no meio sem nenhum aviso. Isso NÃO é usado pra pular buscas em execuções
    futuras (o objetivo é garantir cobertura, não economizar tempo às custas
    dela) - só pra reportar, ao final de cada execução, o que foi
    confirmado de verdade (ver orquestrador.rodar())."""
    chave = f"{cnpj}|{tipo_value}"
    if chave not in estado["varreduras_completas"]:
        estado["varreduras_completas"].append(chave)
