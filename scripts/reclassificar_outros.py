"""
Reclassifica linhas da planilha final que caíram em "Tipo de Multa" =
"Outros" mas que, com as correções de identificar_tipo_multa() de
23/09/2026 (regex sem re.DOTALL + 2 tipos novos: "Evasão de Pesagem" e
"Cargas - RNTRC" - ver CLAUDE.md), agora são classificáveis de verdade.

Diferente dos outros scripts de correção de hoje/ontem, este também MOVE
o PDF em disco pra pasta do tipo certo (`Autos/{cnpj}/{tipo}/{auto}.pdf`)
- a coluna "Tipo de Multa" e o "Link do Arquivo" precisam continuar
consistentes entre si (senão a planilha diz um tipo e o link aponta pra
uma pasta "Outros" que não bate).

Autos que CONTINUAM "Outros" depois da reclassificação (ex.: os
documentos de Dívida Ativa, onde a página 1 genuinamente não é o auto)
não são tocados - nem o arquivo nem a linha.

100% local, sem sessão nem contato com o portal.

USO:
    python scripts/reclassificar_outros.py           # aplica de verdade
    python scripts/reclassificar_outros.py --dry-run  # só mostra o que faria
"""
import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt.config import PLANILHA_PATH  # noqa: E402
from robo_antt.extracao import extrair_texto_pagina1, identificar_tipo_multa  # noqa: E402
from robo_antt.planilha import COLUNAS, NOME_ABA, abrir_ou_criar, salvar  # noqa: E402

_COL_AUTO = COLUNAS.index("Auto de Infração") + 1  # openpyxl é 1-based
_COL_TIPO = COLUNAS.index("Tipo de Multa") + 1
_COL_LINK = COLUNAS.index("Link do Arquivo") + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que faria, não move nem grava nada")
    args = parser.parse_args()

    print(f"Planilha: {PLANILHA_PATH}")
    wb = abrir_ou_criar(PLANILHA_PATH)
    ws = wb[NOME_ABA] if NOME_ABA in wb.sheetnames else wb.active

    alvos = []
    for numero_linha in range(2, ws.max_row + 1):
        if ws.cell(row=numero_linha, column=_COL_TIPO).value == "Outros":
            alvos.append(numero_linha)

    print(f"Linhas com 'Tipo de Multa' = Outros: {len(alvos)}")

    reclassificados = 0
    continuam_outros = 0
    erros = []
    for numero_linha in alvos:
        auto = ws.cell(row=numero_linha, column=_COL_AUTO).value
        link_atual = ws.cell(row=numero_linha, column=_COL_LINK).value
        caminho_atual = Path(link_atual) if link_atual else None
        if not caminho_atual or not caminho_atual.exists():
            erros.append((auto, "arquivo não encontrado"))
            continue

        try:
            texto = extrair_texto_pagina1(caminho_atual)
            novo_tipo = identificar_tipo_multa(texto)
        except Exception as e:
            erros.append((auto, f"erro ao reextrair: {e}"))
            continue

        if novo_tipo == "Outros":
            continuam_outros += 1
            continue

        caminho_novo = caminho_atual.parent.parent / novo_tipo / caminho_atual.name
        print(f"  {auto}: Outros -> {novo_tipo}")
        print(f"    {caminho_atual} -> {caminho_novo}")

        if not args.dry_run:
            caminho_novo.parent.mkdir(parents=True, exist_ok=True)
            caminho_atual.rename(caminho_novo)
            ws.cell(row=numero_linha, column=_COL_TIPO, value=novo_tipo)
            ws.cell(row=numero_linha, column=_COL_LINK, value=str(caminho_novo))
        reclassificados += 1

    print(f"\nReclassificados: {reclassificados}")
    print(f"Continuam 'Outros' (página 1 não é o auto - revisão manual): {continuam_outros}")
    if erros:
        print(f"Erros ({len(erros)}):")
        for item in erros:
            print(f"  {item}")

    if not args.dry_run and reclassificados:
        salvar(wb, PLANILHA_PATH)
        print("\nPlanilha salva.")
    elif args.dry_run:
        print("\n(--dry-run: nada foi movido nem gravado)")
    else:
        print("\nNada pra salvar.")


if __name__ == "__main__":
    main()
