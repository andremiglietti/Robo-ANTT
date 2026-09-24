"""
Exporta a lista de autos com falha de download/extração pendente (vistos na
tabela do portal, mas nunca baixados/extraídos com sucesso) numa planilha
separada pra revisão manual - achado em 24/09/2026 (ver CLAUDE.md).

Decisão do usuário em 24/09/2026: depois de vários ciclos de retentativa
automática (19-23/09/2026) confirmando que o mesmo cluster de ~180
documentos falha de forma IDÊNTICA sempre (timeout esperando o evento de
download - problema do lado do servidor da ANTT, não do robô), não vale
mais gastar ciclos de login/workers retentando - a lista vira o entregável
final: candidatos a verificação manual direta no portal ou contato com a
ANTT.

100% local - lê só os checkpoints já salvos em disco, sem sessão nem
contato com o portal.

USO:
    python scripts/exportar_falhas_pendentes.py
"""
import json
import sys
from pathlib import Path

from openpyxl import Workbook

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt.config import SHAREPOINT_DIR, TIPOS_FISCALIZACAO  # noqa: E402
from robo_antt.io_seguro import substituir_com_retentativa  # noqa: E402

CHECKPOINT_DIR = BASE_DIR / "data" / "output"
DESTINO = SHAREPOINT_DIR / "Falhas_Pendentes_Revisao_Manual.xlsx"

COLUNAS = ["Auto de Infração", "CNPJ", "Tipo de Fiscalização", "Motivo da Falha", "Visto em (checkpoint(s))"]


def _formatar_cnpj(cnpj: str | None) -> str:
    """row["cnpj"] (portal.py) é o valor cru do <select> (só dígitos) -
    formata pro padrão XX.XXX.XXX/XXXX-XX pra facilitar busca manual no
    portal por quem for revisar essa planilha."""
    if not cnpj or not cnpj.isdigit() or len(cnpj) != 14:
        return cnpj or "(desconhecido - falha legada sem esse registro)"
    return f"{cnpj[0:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"


def _coletar_falhas() -> dict:
    """{auto: {"motivo", "cnpj", "tipo_value", "origens": [nomes de checkpoint]}}
    - dá preferência à entrada com cnpj/tipo conhecido quando o mesmo auto
    aparece em mais de 1 checkpoint (achado ao vivo em 24/09/2026: o mesmo
    auto pode ter sido tentado por checkpoints diferentes ao longo do
    tempo, por causa de reparticionamento entre execuções)."""
    todos: dict = {}
    for arquivo in sorted(CHECKPOINT_DIR.glob("checkpoint*.json")):
        estado = json.loads(arquivo.read_text(encoding="utf-8"))
        for auto, info in estado.get("falhas", {}).items():
            motivo = info.get("motivo", "") if isinstance(info, dict) else str(info)
            cnpj = info.get("cnpj") if isinstance(info, dict) else None
            tipo_value = info.get("tipo_value") if isinstance(info, dict) else None

            existente = todos.get(auto)
            if existente is None:
                todos[auto] = {"motivo": motivo, "cnpj": cnpj, "tipo_value": tipo_value, "origens": [arquivo.name]}
            else:
                existente["origens"].append(arquivo.name)
                if not existente["cnpj"] and cnpj:
                    existente["motivo"] = motivo
                    existente["cnpj"] = cnpj
                    existente["tipo_value"] = tipo_value
    return todos


def main() -> None:
    falhas = _coletar_falhas()
    print(f"Falhas únicas encontradas: {len(falhas)}")

    wb = Workbook()
    ws = wb.active
    ws.title = "Falhas Pendentes"
    ws.append(COLUNAS)

    for auto in sorted(falhas):
        info = falhas[auto]
        tipo_nome = TIPOS_FISCALIZACAO.get(info["tipo_value"], "(desconhecido - falha legada sem esse registro)")
        # só a 1ª linha do motivo - o resto é o "call log" técnico do
        # Playwright (útil pra debug, não pra quem for revisar essa lista).
        motivo_resumido = info["motivo"].split("\n", 1)[0]
        ws.append(
            [
                auto,
                _formatar_cnpj(info["cnpj"]),
                tipo_nome,
                motivo_resumido,
                ", ".join(info["origens"]),
            ]
        )

    for coluna in ws.columns:
        maior = max(len(str(c.value)) for c in coluna)
        ws.column_dimensions[coluna[0].column_letter].width = min(maior + 2, 60)

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    tmp = DESTINO.parent / f"_tmp_{DESTINO.name}"
    wb.save(tmp)
    substituir_com_retentativa(tmp, DESTINO)

    print(f"Planilha salva em: {DESTINO}")


if __name__ == "__main__":
    main()
