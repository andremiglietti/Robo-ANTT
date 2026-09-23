"""
Migra as linhas JÁ REGISTRADAS na planilha final de texto puro pro tipo
nativo do Excel (datetime.date pras colunas de data, float pras de
valor) - ver CLAUDE.md, 23/09/2026.

Por que existe: a conversão em planilha.py (_converter_para_tipo_nativo())
só vale pra gravações NOVAS a partir de agora - as ~4187 linhas já
escritas antes continuam como texto puro pra sempre, a menos que alguém
migre elas explicitamente (mesmo padrão dos outros backfills de hoje/ontem
- `processar_linha()` pula por completo qualquer auto já conhecido).

NÃO precisa migrar as planilhas-fatia de worker (planilha_worker_*.xlsx) -
toda vez que uma linha delas for consolidada na planilha final (agora ou
no futuro), `adicionar_registro()` já aplica a conversão sozinho no
caminho de entrada.

100% local, sem sessão nem contato com o portal.

USO:
    python scripts/migrar_tipos_nativos.py           # aplica de verdade
    python scripts/migrar_tipos_nativos.py --dry-run  # só mostra o que faria
"""
import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt.config import PLANILHA_PATH  # noqa: E402
from robo_antt.planilha import (  # noqa: E402
    COLUNAS,
    NOME_ABA,
    _aplicar_formato_numerico,
    _converter_para_tipo_nativo,
    abrir_ou_criar,
    salvar,
)

_COLUNAS_ALVO = [c for c in COLUNAS if c in {"Valor", "Valor Desconto"} or "Data" in c]
_INDICES_ALVO = [(c, COLUNAS.index(c) + 1) for c in _COLUNAS_ALVO]  # (nome, coluna 1-based)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que faria, não grava nada")
    args = parser.parse_args()

    print(f"Planilha: {PLANILHA_PATH}")
    wb = abrir_ou_criar(PLANILHA_PATH)
    ws = wb[NOME_ABA] if NOME_ABA in wb.sheetnames else wb.active

    total_linhas = 0
    total_celulas_migradas = 0
    total_celulas_nao_convertiveis = 0
    amostra_nao_convertivel = []

    for numero_linha in range(2, ws.max_row + 1):
        total_linhas += 1
        for nome_coluna, indice_coluna in _INDICES_ALVO:
            celula = ws.cell(row=numero_linha, column=indice_coluna)
            if celula.value is None or not isinstance(celula.value, str):
                continue  # já é nativo (migração anterior) ou está vazio
            valor_convertido = _converter_para_tipo_nativo(nome_coluna, celula.value)
            if isinstance(valor_convertido, str):
                # a conversão não conseguiu (formato atípico) - fica como texto mesmo
                total_celulas_nao_convertiveis += 1
                if len(amostra_nao_convertivel) < 10:
                    auto = ws.cell(row=numero_linha, column=COLUNAS.index("Auto de Infração") + 1).value
                    amostra_nao_convertivel.append((auto, nome_coluna, celula.value))
                continue
            if not args.dry_run:
                celula.value = valor_convertido
                _aplicar_formato_numerico(celula, nome_coluna)
            total_celulas_migradas += 1

    print(f"Linhas verificadas: {total_linhas}")
    print(f"Células migradas pro tipo nativo: {total_celulas_migradas}")
    print(f"Células que continuam como texto (formato atípico, não convertido): {total_celulas_nao_convertiveis}")
    if amostra_nao_convertivel:
        print("Amostra das não convertidas:")
        for item in amostra_nao_convertivel:
            print(f"  {item}")

    if not args.dry_run and total_celulas_migradas:
        salvar(wb, PLANILHA_PATH)
        print("\nPlanilha salva.")
    elif args.dry_run:
        print("\n(--dry-run: nada foi gravado)")
    else:
        print("\nNada pra migrar.")


if __name__ == "__main__":
    main()
