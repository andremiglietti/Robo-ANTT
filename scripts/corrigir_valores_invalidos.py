"""
Corrige células de colunas monetárias que têm um formato claramente
inválido (não é "NNN,NN" nem "N.NNN,NN") - diferente de
scripts/backfill_campos_pdf.py (que só PREENCHE célula vazia), este
script SOBRESCREVE um valor errado já gravado, então só mexe em linhas
cujo valor atual falha o teste de formato - nunca em linhas que já
parecem válidas.

Por que existe (22/09/2026, ver CLAUDE.md): a extração de "Valor" e
"Valor Desconto" usava regex no texto corrido da página do boleto - em
alguns sub-layouts, o texto corrido intercala colunas/quebra linha entre
o rótulo e o valor de verdade, e a regex capturava lixo (ex.: "Valor" =
'92.660.604', um pedaço de CNPJ; "Valor Desconto" = ',' ou '4').
Corrigido em extracao.py (trocado pra extração por células de tabela,
imune a esse problema, com fallback de subtração Valor - Valor com
Desconto pros casos onde nem a célula nem o texto corrido têm o dado) -
este script aplica a correção nas linhas que já tinham o valor errado
gravado.

100% local, sem sessão nem contato com o portal (reabre o PDF já em disco).

USO:
    python scripts/corrigir_valores_invalidos.py                    # Valor + Valor Desconto
    python scripts/corrigir_valores_invalidos.py --coluna Valor      # só uma coluna
    python scripts/corrigir_valores_invalidos.py --dry-run           # só mostra o que faria
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

# Coluna da planilha -> chave correspondente no dict devolvido por
# extrair_campos_boleto() (ver extracao.py).
_COLUNAS_CORRIGIVEIS = {
    "Valor": "valor",
    "Valor Desconto": "valor_desconto",
}

_COL_AUTO = COLUNAS.index("Auto de Infração") + 1  # openpyxl é 1-based
_COL_LINK = COLUNAS.index("Link do Arquivo") + 1


def _valido(valor) -> bool:
    return bool(valor) and bool(_PADRAO_VALOR_VALIDO.fullmatch(str(valor)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--coluna",
        choices=list(_COLUNAS_CORRIGIVEIS),
        help="corrigir só esta coluna (padrão: todas as monetárias conhecidas)",
    )
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que faria, não grava nada")
    args = parser.parse_args()

    colunas_alvo = [args.coluna] if args.coluna else list(_COLUNAS_CORRIGIVEIS)

    print(f"Planilha: {PLANILHA_PATH}")
    wb = abrir_ou_criar(PLANILHA_PATH)
    ws = wb[NOME_ABA] if NOME_ABA in wb.sheetnames else wb.active

    total_corrigido = 0
    for nome_coluna in colunas_alvo:
        campo = _COLUNAS_CORRIGIVEIS[nome_coluna]
        col_indice = COLUNAS.index(nome_coluna) + 1

        alvos = []
        for numero_linha in range(2, ws.max_row + 1):
            valor_atual = ws.cell(row=numero_linha, column=col_indice).value
            if valor_atual and not _valido(valor_atual):
                auto = ws.cell(row=numero_linha, column=_COL_AUTO).value
                link = ws.cell(row=numero_linha, column=_COL_LINK).value
                alvos.append((numero_linha, auto, valor_atual, link))

        print(f"\n=== {nome_coluna}: {len(alvos)} linha(s) em formato inválido ===")

        corrigidos = 0
        nao_resolvido = []
        cache_pdf: dict[str, dict] = {}  # evita reextrair o mesmo PDF 2x se --coluna nao for passado
        for numero_linha, auto, valor_antigo, link in alvos:
            caminho_pdf = Path(link) if link else None
            if not caminho_pdf or not caminho_pdf.exists():
                nao_resolvido.append((auto, valor_antigo, "arquivo nao encontrado"))
                continue
            if str(caminho_pdf) not in cache_pdf:
                pg = localizar_pagina_boleto(caminho_pdf)
                cache_pdf[str(caminho_pdf)] = extrair_campos_boleto(caminho_pdf, pg) if pg else None
            campos = cache_pdf[str(caminho_pdf)]
            if campos is None:
                nao_resolvido.append((auto, valor_antigo, "sem pagina de boleto"))
                continue

            valor_novo = campos[campo]
            if not _valido(valor_novo):
                nao_resolvido.append((auto, valor_antigo, f"reextracao ainda invalida ({valor_novo!r})"))
                continue

            print(f"  {auto}: {valor_antigo!r} -> {valor_novo!r}")
            if not args.dry_run:
                ws.cell(row=numero_linha, column=col_indice, value=valor_novo)
            corrigidos += 1

        print(f"Corrigidos: {corrigidos}")
        if nao_resolvido:
            print(f"Nao resolvidos ({len(nao_resolvido)}):")
            for item in nao_resolvido:
                print(f"  {item}")
        total_corrigido += corrigidos

    if not args.dry_run and total_corrigido:
        salvar(wb, PLANILHA_PATH)
        print("\nPlanilha salva.")
    elif args.dry_run:
        print("\n(--dry-run: nada foi gravado)")
    else:
        print("\nNada pra salvar.")


if __name__ == "__main__":
    main()
