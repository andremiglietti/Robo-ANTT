"""
Corrige células da coluna "Valor" que têm um formato claramente inválido
(não é "NNN,NN" nem "N.NNN,NN") - diferente de scripts/backfill_campos_pdf.py
(que só PREENCHE célula vazia), este script SOBRESCREVE um valor errado já
gravado, então só mexe em linhas cujo valor atual falha o teste de formato -
nunca em linhas que já parecem válidas.

Por que existe (22/09/2026, ver CLAUDE.md): a extração de "Valor" usava
regex no texto corrido da página do boleto - num sub-layout GRU de 3
colunas, o texto corrido intercala colunas, e a regex capturava um CNPJ de
coluna vizinha em vez do valor de verdade (ex.: "Valor" = '92.660.604').
Corrigido em extracao.py (trocado pra extração por células de tabela,
imune a esse problema) - este script aplica a correção nas linhas que já
tinham o valor errado gravado.

100% local, sem sessão nem contato com o portal (reabre o PDF já em disco).

USO:
    python scripts/corrigir_valores_invalidos.py           # aplica de verdade
    python scripts/corrigir_valores_invalidos.py --dry-run  # só mostra o que faria
"""
import argparse
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt.config import PLANILHA_PATH  # noqa: E402
from robo_antt.extracao import extrair_campos_boleto, localizar_pagina_boleto  # noqa: E402
from robo_antt.planilha import COLUNAS, NOME_ABA, abrir_ou_criar, salvar  # noqa: E402

_PADRAO_VALOR_VALIDO = re.compile(r"\d{1,3}(\.\d{3})*,\d{2}|\d+,\d{2}")

_COL_AUTO = COLUNAS.index("Auto de Infração") + 1  # openpyxl é 1-based
_COL_LINK = COLUNAS.index("Link do Arquivo") + 1
_COL_VALOR = COLUNAS.index("Valor") + 1


def _valido(valor) -> bool:
    return bool(valor) and bool(_PADRAO_VALOR_VALIDO.fullmatch(str(valor)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que faria, não grava nada")
    args = parser.parse_args()

    print(f"Planilha: {PLANILHA_PATH}")
    wb = abrir_ou_criar(PLANILHA_PATH)
    ws = wb[NOME_ABA] if NOME_ABA in wb.sheetnames else wb.active

    alvos = []
    for numero_linha in range(2, ws.max_row + 1):
        valor_atual = ws.cell(row=numero_linha, column=_COL_VALOR).value
        if valor_atual and not _valido(valor_atual):
            auto = ws.cell(row=numero_linha, column=_COL_AUTO).value
            link = ws.cell(row=numero_linha, column=_COL_LINK).value
            alvos.append((numero_linha, auto, valor_atual, link))

    print(f"Linhas com Valor em formato invalido: {len(alvos)}")

    corrigidos = 0
    nao_resolvido = []
    for numero_linha, auto, valor_antigo, link in alvos:
        caminho_pdf = Path(link) if link else None
        if not caminho_pdf or not caminho_pdf.exists():
            nao_resolvido.append((auto, valor_antigo, "arquivo nao encontrado"))
            continue
        pg = localizar_pagina_boleto(caminho_pdf)
        if not pg:
            nao_resolvido.append((auto, valor_antigo, "sem pagina de boleto"))
            continue
        campos = extrair_campos_boleto(caminho_pdf, pg)
        valor_novo = campos["valor"]
        if not _valido(valor_novo):
            nao_resolvido.append((auto, valor_antigo, f"reextracao ainda invalida ({valor_novo!r})"))
            continue

        print(f"  {auto}: {valor_antigo!r} -> {valor_novo!r}")
        if not args.dry_run:
            ws.cell(row=numero_linha, column=_COL_VALOR, value=valor_novo)
        corrigidos += 1

    print(f"\nCorrigidos: {corrigidos}")
    if nao_resolvido:
        print(f"Nao resolvidos ({len(nao_resolvido)}):")
        for item in nao_resolvido:
            print(f"  {item}")

    if not args.dry_run and corrigidos:
        salvar(wb, PLANILHA_PATH)
        print("Planilha salva.")
    elif args.dry_run:
        print("(--dry-run: nada foi gravado)")
    else:
        print("Nada pra salvar.")


if __name__ == "__main__":
    main()
