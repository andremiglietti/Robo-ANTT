"""
Renomeia as pastas já existentes em `Autos/{cnpj}/` pra
`Autos/{cnpj} - {apelido}/` quando o CNPJ tem apelido cadastrado (pedido
em reunião com o time, 25/09/2026: "colocar junto ao nome da pasta do
CNPJ o Apelido" - ver `src/robo_antt/cadastro.py`).

Autos baixados a partir de hoje já usam esse nome diretamente
(`download.py`) - este script é só o catch-up pontual das pastas que já
existiam ANTES dessa mudança. CNPJs sem apelido cadastrado não são
tocados (ficam com o nome antigo, só CNPJ - `already_downloaded()` já
sabe procurar dos 2 jeitos, ver CLAUDE.md).

Também atualiza a coluna "Link do Arquivo" na planilha final pros autos
afetados - senão o link ficaria apontando pra um caminho que não existe
mais depois do rename.

⚠️ CUIDADO: mexe em pastas/arquivos REAIS na pasta sincronizada com o
SharePoint, e na planilha final. Não é seguro rodar de verdade enquanto
algum worker estiver ativo (pode estar escrevendo dentro da MESMA pasta
que este script renomearia) - o script confere isso antes de aplicar
(mesma checagem de trava usada em io_seguro.adquirir_trava(), só que sem
adquirir nada) e recusa rodar se achar algum checkpoint com trava ativa.

100% seguro rodar --dry-run a qualquer momento (só leitura, não conflita
com nenhum worker rodando).

USO:
    python scripts/migrar_pastas_apelido.py --dry-run
    python scripts/migrar_pastas_apelido.py
"""
import argparse
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt.cadastro import carregar_apelidos, nome_pasta_cnpj  # noqa: E402
from robo_antt.config import DOWNLOAD_DIR, OUTPUT_DIR, PLANILHA_PATH  # noqa: E402
from robo_antt.io_seguro import _ler_pid_da_trava, _processo_ainda_rodando  # noqa: E402
from robo_antt.planilha import COLUNAS, NOME_ABA, abrir_ou_criar, salvar  # noqa: E402

_RE_CNPJ_PURO = re.compile(r"^\d{14}$")
_COL_CNPJ = COLUNAS.index("CNPJ") + 1  # openpyxl é 1-based
_COL_LINK = COLUNAS.index("Link do Arquivo") + 1


def _travas_ativas() -> list[str]:
    """Lista os checkpoints com trava (.lock) ainda com PID vivo - mesma
    checagem de io_seguro.adquirir_trava(), só leitura, não adquire nada."""
    ativas = []
    for trava in OUTPUT_DIR.glob("*.lock"):
        pid = _ler_pid_da_trava(trava)
        if pid and _processo_ainda_rodando(pid):
            ativas.append(trava.name)
    return ativas


def _calcular_renomeacoes() -> dict[str, str]:
    """{cnpj_puro: novo_nome_de_pasta} só pros CNPJs que já têm pasta
    (formato antigo, só dígitos) E têm apelido cadastrado - o resto
    (já renomeado, ou sem apelido conhecido) não entra na lista."""
    renomeacoes: dict[str, str] = {}
    if not DOWNLOAD_DIR.exists():
        return renomeacoes
    for pasta in sorted(DOWNLOAD_DIR.iterdir()):
        if not pasta.is_dir() or not _RE_CNPJ_PURO.match(pasta.name):
            continue
        novo_nome = nome_pasta_cnpj(pasta.name)
        if novo_nome != pasta.name:
            renomeacoes[pasta.name] = novo_nome
    return renomeacoes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que faria, não move nem grava nada")
    args = parser.parse_args()

    if not args.dry_run:
        ativas = _travas_ativas()
        if ativas:
            print(f"[ATENÇÃO] Worker(s) ainda ativo(s) agora ({', '.join(ativas)}) - não é seguro renomear pastas.")
            print("Espere terminar (ou encerre) antes de rodar sem --dry-run.")
            return

    apelidos = carregar_apelidos()
    print(f"CNPJs com apelido cadastrado: {len(apelidos)}")

    renomeacoes = _calcular_renomeacoes()
    print(f"Pastas a renomear: {len(renomeacoes)}")
    for cnpj, novo_nome in renomeacoes.items():
        print(f"  {cnpj} -> {novo_nome}")

    if not renomeacoes:
        print("\nNada a fazer.")
        return

    if args.dry_run:
        print("\n(--dry-run: nada foi renomeado nem gravado)")
        return

    renomeadas_de_verdade: dict[str, str] = {}
    for cnpj, novo_nome in renomeacoes.items():
        origem = DOWNLOAD_DIR / cnpj
        destino = DOWNLOAD_DIR / novo_nome
        if destino.exists():
            print(f"  [PULADO] '{novo_nome}' já existe - não sobrescrevendo.")
            continue
        origem.rename(destino)
        renomeadas_de_verdade[cnpj] = novo_nome
    print(f"\n{len(renomeadas_de_verdade)} pasta(s) renomeada(s).")

    if not renomeadas_de_verdade:
        return

    print("\nAtualizando 'Link do Arquivo' na planilha final...")
    wb = abrir_ou_criar(PLANILHA_PATH)
    ws = wb[NOME_ABA] if NOME_ABA in wb.sheetnames else wb.active
    atualizados = 0
    for numero_linha in range(2, ws.max_row + 1):
        cnpj_linha = ws.cell(row=numero_linha, column=_COL_CNPJ).value
        if cnpj_linha not in renomeadas_de_verdade:
            continue
        link_atual = ws.cell(row=numero_linha, column=_COL_LINK).value
        if not link_atual:
            continue
        prefixo_antigo = str(DOWNLOAD_DIR / cnpj_linha)
        if not link_atual.startswith(prefixo_antigo):
            continue  # link já não bate com o formato esperado - não mexe, pra não arriscar quebrar
        prefixo_novo = str(DOWNLOAD_DIR / renomeadas_de_verdade[cnpj_linha])
        link_novo = prefixo_novo + link_atual[len(prefixo_antigo):]
        ws.cell(row=numero_linha, column=_COL_LINK, value=link_novo)
        atualizados += 1
    print(f"{atualizados} link(s) atualizado(s) na planilha.")
    if atualizados:
        salvar(wb, PLANILHA_PATH)
        print("Planilha salva.")


if __name__ == "__main__":
    main()
