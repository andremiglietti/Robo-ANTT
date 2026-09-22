"""
Auditoria local: PDFs em disco (Autos/) x autos realmente registrados em
alguma planilha (final ou fatias de worker ainda não consolidadas).

Por que existe (achado de 21/09/2026, ver CLAUDE.md): o CNPJ
92.660.604/0013-16 teve 687 PDFs baixados sem nunca virar linha na
planilha (falha silenciosa de uma execução antiga) - só foi descoberto
comparando contagem de arquivos com contagem de linhas. Esse script
generaliza essa comparação pra TODOS os CNPJs/tipos de uma vez, sem
precisar de sessão nem tocar no portal - só lê arquivos locais e a
planilha, então é seguro rodar mesmo com uma varredura de verdade em
andamento em paralelo (não compete por nada que ela usa).

Um PDF é considerado "órfão" se o número do Auto de Infração dele não
aparece em NENHUMA planilha conhecida (a final do SharePoint + todas as
planilha_worker_*.xlsx locais, que podem ter resultados novos ainda não
consolidados - não é bug já são só "não juntados ainda"). Isso é mais
preciso que só comparar contagens: aponta exatamente quais autos faltam.

USO:
    python scripts/auditoria_disco_planilha.py
"""
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt.config import DOWNLOAD_DIR, OUTPUT_DIR, PLANILHA_PATH  # noqa: E402
from robo_antt.planilha import COLUNAS, NOME_ABA  # noqa: E402

_COL_AUTO = COLUNAS.index("Auto de Infração")


def _autos_registrados(caminho: Path) -> set[str]:
    """Lê só a coluna 'Auto de Infração' de uma planilha (final ou fatia de
    worker), sem carregar o resto - rápido mesmo com milhares de linhas."""
    if not caminho.exists():
        return set()
    wb = load_workbook(str(caminho), read_only=True)
    ws = wb[NOME_ABA] if NOME_ABA in wb.sheetnames else wb.active
    autos = set()
    for linha in ws.iter_rows(min_row=2, values_only=True):
        if len(linha) > _COL_AUTO and linha[_COL_AUTO]:
            autos.add(str(linha[_COL_AUTO]))
    wb.close()
    return autos


def _pdfs_em_disco() -> list[tuple[str, str, str, Path]]:
    """Devolve (cnpj, tipo_multa, auto_infracao, caminho) pra cada PDF real
    encontrado em Autos/{cnpj}/{tipo}/{auto}.pdf."""
    if not DOWNLOAD_DIR.exists():
        return []
    encontrados = []
    for caminho in DOWNLOAD_DIR.glob("*/*/*.pdf"):
        cnpj = caminho.parent.parent.name
        tipo = caminho.parent.name
        auto = caminho.stem
        encontrados.append((cnpj, tipo, auto, caminho))
    return encontrados


def main() -> None:
    print(f"Planilha final: {PLANILHA_PATH}")
    print(f"Pasta de PDFs: {DOWNLOAD_DIR}\n")

    fontes_planilha = [PLANILHA_PATH] + sorted(OUTPUT_DIR.glob("planilha_worker_*.xlsx"))
    autos_registrados: set[str] = set()
    for caminho in fontes_planilha:
        antes = len(autos_registrados)
        autos_registrados |= _autos_registrados(caminho)
        if caminho.exists():
            print(f"  lida: {caminho.name} (+{len(autos_registrados) - antes} auto(s) novo(s) no conjunto)")

    pdfs = _pdfs_em_disco()
    print(f"\nTotal de PDFs em disco: {len(pdfs)}")
    print(f"Total de autos registrados (final + fatias de worker, deduplicado): {len(autos_registrados)}")

    orfaos_por_chave: dict[tuple[str, str], list[str]] = defaultdict(list)
    for cnpj, tipo, auto, _caminho in pdfs:
        if auto not in autos_registrados:
            orfaos_por_chave[(cnpj, tipo)].append(auto)

    total_orfaos = sum(len(v) for v in orfaos_por_chave.values())
    if not total_orfaos:
        print(
            "\n[OK] Nenhum PDF orfao encontrado - todo PDF em disco tem uma linha "
            "correspondente em alguma planilha (final ou fatia de worker)."
        )
        return

    print(f"\n[ATENCAO] {total_orfaos} PDF(s) em disco SEM linha correspondente em nenhuma planilha:")
    for (cnpj, tipo), autos in sorted(orfaos_por_chave.items(), key=lambda kv: -len(kv[1])):
        print(f"  - CNPJ {cnpj} | {tipo}: {len(autos)} orfao(s)")
        if len(autos) <= 5:
            for auto in autos:
                print(f"      {auto}")

    print(
        "\nCada orfao listado acima tem PDF baixado, mas nenhuma linha na planilha final nem "
        "em nenhuma planilha-fatia de worker ainda nao consolidada. Provavel causa: mesmo tipo "
        "de falha silenciosa ja documentado no CLAUDE.md (crash durante gravacao, ou combinacao "
        "com volume grande demais pro prazo de espera do portal). Nao precisa refazer o download "
        "(o PDF ja existe) - precisa so reprocessar a extracao+registro desses autos especificos."
    )


if __name__ == "__main__":
    main()
