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
from robo_antt.io_seguro import substituir_com_retentativa

CHECKPOINT_FILE = OUTPUT_DIR / "checkpoint.json"


class CheckpointCorrompidoError(Exception):
    """O arquivo de checkpoint existe mas não é um JSON válido (achado na
    revisão crítica de 24/09/2026: `carregar()` não tinha NENHUM tratamento
    pra isso - um checkpoint truncado/corrompido, por qualquer motivo,
    derrubava a execução inteira com um `json.JSONDecodeError` cru, sem a
    mesma cortesia de relatório limpo que o resto do projeto garante pra
    outras falhas de infraestrutura (SessaoExpiradaError/
    PortalIndisponivelError).

    Levantada em vez de simplesmente devolver um estado vazio - silenciar
    e recomeçar do zero perderia a lista de milhares de autos já
    processados e de falhas pendentes sem avisar ninguém, o oposto da
    filosofia de "nunca esconder problema" do resto do projeto."""


def carregar(caminho: Path = CHECKPOINT_FILE) -> dict:
    if caminho.exists():
        try:
            estado = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise CheckpointCorrompidoError(
                f"O checkpoint '{caminho}' existe mas não é um JSON válido ({e}) - "
                "não é seguro continuar automaticamente (recomeçar do zero perderia o "
                "histórico de autos já processados). Restaure de um backup ou apague "
                "manualmente o arquivo se tiver certeza de que pode perder o progresso."
            ) from e
        # setdefault - compatível com checkpoints salvos antes de 17/09/2026,
        # de quando esse campo ainda não existia (ver "varreduras_completas" abaixo)
        estado.setdefault("varreduras_completas", [])
        # Migração (19/09/2026, ver marcar_falha() e falhas_retentaveis()):
        # "falhas" passou de {auto: "motivo"} pra {auto: {"motivo","cnpj",
        # "tipo_value"}} - entradas antigas (checkpoints salvos antes de
        # hoje) viram um dict equivalente com cnpj/tipo_value=None, o que
        # sinaliza "não sabemos onde retentar essa - só descobrindo de novo
        # por acaso numa varredura que passe por aquela combinação".
        estado["falhas"] = {
            auto: (info if isinstance(info, dict) else {"motivo": info, "cnpj": None, "tipo_value": None})
            for auto, info in estado.get("falhas", {}).items()
        }
        # Achado na revisão crítica de 24/09/2026: "processados" ficava
        # como list (igual ao JSON) - ja_processado() virava um scan O(n)
        # a cada chamada, e com checkpoints reais passando de 4000 entradas
        # isso significa milhares de comparações de string por documento
        # checado. planilha.ja_registrado() já tinha ganhado esse mesmo
        # fix em 22/09/2026 (comparar contra um set em vez de escanear uma
        # lista) - aqui é o mesmo problema, na estrutura irmã. Convertido
        # pra set em memória; salvar() converte de volta pra list (ordenada,
        # pra o JSON continuar legível/diffável) na hora de gravar.
        estado["processados"] = set(estado.get("processados", []))
        return estado
    return {"processados": set(), "falhas": {}, "varreduras_completas": [], "ultima_execucao": None}


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
    # "processados" fica como set() em memória (ver carregar()) - json não
    # serializa set, então converte pra list ordenada só na hora de gravar,
    # sem mutar o dict `estado` que o resto da execução continua usando.
    estado_serializavel = {**estado, "processados": sorted(estado["processados"])}
    caminho_tmp.write_text(json.dumps(estado_serializavel, ensure_ascii=False, indent=2), encoding="utf-8")
    substituir_com_retentativa(caminho_tmp, caminho)


def ja_processado(estado: dict, auto_infracao: str) -> bool:
    return auto_infracao in estado["processados"]


def marcar_processado(estado: dict, auto_infracao: str) -> None:
    estado["processados"].add(auto_infracao)
    estado["falhas"].pop(auto_infracao, None)  # se tinha falhado antes e agora deu certo, tira da lista de falhas


def marcar_falha(estado: dict, auto_infracao: str, motivo: str, cnpj: str | None = None, tipo_value: str | None = None) -> None:
    """`cnpj`/`tipo_value` (19/09/2026, achado ao vivo - ver CLAUDE.md):
    gravar ONDE essa falha aconteceu permite retentá-la diretamente depois
    (ver falhas_retentaveis()), em vez de depender de a mesma combinação
    CNPJ×tipo ser revisitada por acaso numa execução futura - confirmado ao
    vivo que isso podia deixar falhas pendentes indefinidamente sem erro
    nenhum, sempre que o particionamento entre workers mudava de uma
    execução pra outra."""
    estado["falhas"][auto_infracao] = {"motivo": motivo, "cnpj": cnpj, "tipo_value": tipo_value}


def falhas_retentaveis(estado: dict) -> list[tuple[str, str, str]]:
    """[(auto_infracao, cnpj, tipo_value), ...] só das falhas que sabemos
    exatamente onde encontrar de novo (registradas por marcar_falha() com
    cnpj/tipo_value) - exclui falhas legadas (checkpoints de antes de
    19/09/2026) que não têm essa informação. Usado por rodar() pra retentar
    falhas de documento DIRETAMENTE, sem depender de o particionamento
    entre workers revisitar a mesma combinação por acaso."""
    return [
        (auto, info["cnpj"], info["tipo_value"])
        for auto, info in estado["falhas"].items()
        if info.get("cnpj") and info.get("tipo_value")
    ]


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
