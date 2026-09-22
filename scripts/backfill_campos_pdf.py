"""
Backfill de campos do PDF em linhas JÁ REGISTRADAS na planilha final -
100% local, sem sessão nem contato com o portal (o PDF já está em disco).

Por que existe (22/09/2026, ver CLAUDE.md): 2 bugs de extração foram
corrigidos hoje (hífen suave U+00AD, prefixo de placa opcional), mas
`processar_linha()` pula por completo qualquer auto já conhecido
(`ja_registrado()`) - então uma correção de extração só vale pra
documentos NOVOS a partir de agora; linhas já escritas ficam com a lacuna
pra sempre, mesmo com o código corrigido. Este script fecha essa lacuna
pras linhas específicas afetadas, sem precisar rebaixar nada.

Só reprocessa linhas com pelo menos 1 destes campos vazio - os campos
"normalmente sempre presentes" (Data Autuação, Data Emissão Doc. Fiscal,
Data Emissão Notificação, Placa, Descrição da Infração). Não usa os campos
do BOLETO (Data Emissão Boleto/Vencimento/Valor/Valor Desconto/Código de
Barras) como gatilho de propósito - ~17% das linhas legitimamente não tem
boleto ainda (processo sem notificação gerada, ver CLAUDE.md), reprocessar
essas PDFs de novo só confirmaria "continua vazio" à toa. Se uma linha
reprocessada por outro motivo TAMBÉM tiver boleto vazio, o backfill
completo (extrair_todos_campos) tenta preencher esses campos de graça -
só não é o GATILHO principal.

Nunca sobrescreve um valor que já existe (ver planilha.atualizar_campos_vazios) -
só preenche célula vazia.

USO:
    python scripts/backfill_campos_pdf.py           # aplica de verdade
    python scripts/backfill_campos_pdf.py --dry-run  # só mostra o que faria
"""
import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt.config import PLANILHA_PATH  # noqa: E402
from robo_antt.orquestrador import extrair_todos_campos  # noqa: E402
from robo_antt.planilha import COLUNAS, NOME_ABA, abrir_ou_criar, atualizar_campos_vazios, registro_da_linha, salvar  # noqa: E402

# Campos "normalmente sempre presentes" usados como gatilho pra reprocessar
# uma linha (ver docstring do módulo - não inclui os campos do boleto).
# Coluna -> campo (mesmo mapeamento de planilha._CAMPO_POR_COLUNA).
_GATILHO = {
    "Data Autuação": "data_autuacao",
    "Data Emissão Doc. Fiscal": "data_emissao_doc_fiscal",
    "Data Emissão Notificação": "data_emissao_notificacao",
    "Placa": "placa",
    "Descrição da Infração": "descricao_infracao",
}
_INDICES_GATILHO = [COLUNAS.index(c) for c in _GATILHO]
_CAMPOS_GATILHO = list(_GATILHO.values())


def _vazio(valor) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que faria, não grava nada")
    args = parser.parse_args()

    print(f"Planilha: {PLANILHA_PATH}")
    wb = abrir_ou_criar(PLANILHA_PATH)
    ws = wb[NOME_ABA] if NOME_ABA in wb.sheetnames else wb.active

    alvos = []
    for linha in ws.iter_rows(min_row=2, values_only=True):
        if any(_vazio(linha[i]) for i in _INDICES_GATILHO):
            alvos.append(registro_da_linha(linha))

    print(f"Linhas candidatas (pelo menos 1 campo-gatilho vazio): {len(alvos)}")

    total_preenchidos = 0
    linhas_melhoradas = 0
    arquivo_nao_encontrado = 0
    erro_extracao = 0

    for registro in alvos:
        auto = registro["auto_infracao"]
        caminho_pdf = Path(registro["link_arquivo"]) if registro["link_arquivo"] else None
        if not caminho_pdf or not caminho_pdf.exists():
            arquivo_nao_encontrado += 1
            continue

        try:
            campos_novos = extrair_todos_campos(caminho_pdf)
        except Exception as e:
            print(f"  [ERRO] {auto}: falha ao extrair ({e})")
            erro_extracao += 1
            continue

        if args.dry_run:
            resolveria = [c for c in _CAMPOS_GATILHO if _vazio(registro.get(c)) and not _vazio(campos_novos.get(c))]
            if resolveria:
                print(f"  {auto}: resolveria {resolveria}")
                linhas_melhoradas += 1
            continue

        preenchidos = atualizar_campos_vazios(wb, auto, campos_novos)
        if preenchidos:
            total_preenchidos += preenchidos
            linhas_melhoradas += 1
            print(f"  {auto}: {preenchidos} campo(s) preenchido(s)")

    print(f"\nArquivo não encontrado em disco: {arquivo_nao_encontrado}")
    print(f"Erro ao extrair: {erro_extracao}")
    print(f"Linhas melhoradas: {linhas_melhoradas}")
    if not args.dry_run:
        print(f"Total de células preenchidas: {total_preenchidos}")
        if total_preenchidos:
            salvar(wb, PLANILHA_PATH)
            print("Planilha salva.")
        else:
            print("Nada pra salvar (nenhuma célula preenchida).")
    else:
        print("(--dry-run: nada foi gravado)")


if __name__ == "__main__":
    main()
