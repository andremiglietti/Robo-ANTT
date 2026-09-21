"""
Relatório de completude da EMPRESA INTEIRA (18/09/2026 - ver CLAUDE.md e o
plano da sessão): junta os checkpoints de todos os workers (e o checkpoint
único, se usado) e compara com a lista completa de CNPJs × tipos de
fiscalização, pra saber com certeza se já chegamos a 100% - e, se não,
exatamente quais combinações ainda faltam.

Por que existe: cada worker só sabe o que ELE viu (seus próprios CNPJs, na
própria execução dele) - "garantia de varredura completa" (ver
orquestrador.py) já garante que NENHUM worker termina achando que tudo foi
verificado quando não foi, mas não dá uma visão consolidada da empresa
inteira, nem acumula entre execuções diferentes num lugar só. Este script é
o jeito de responder com certeza: "já temos 100% de todos os CNPJs em todos
os tipos, ou falta alguma coisa - e o quê, exatamente?"

Precisa de UMA sessão válida (qualquer uma - a principal ou de algum
worker) só pra listar os CNPJs reais (rápido, não baixa nada).

USO:
    python scripts/relatorio_completude.py
    python scripts/relatorio_completude.py --session data/sessao/sessao_worker_1.json
"""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt import checkpoint as checkpoint_mod  # noqa: E402
from robo_antt.config import OUTPUT_DIR, SESSAO_DIR, SESSION_FILE, TIPOS_FISCALIZACAO  # noqa: E402
from robo_antt.portal import PortalIndisponivelError, SessaoExpiradaError, abrir_contexto, abrir_tela_processos, listar_cnpjs  # noqa: E402


def _achar_sessao_valida(preferida: Path | None) -> Path:
    """Devolve a primeira sessão que existir: a preferida (se passada), a
    principal, ou qualquer sessao_worker_*.json encontrada - só precisamos
    de UMA sessão válida pra listar os CNPJs, não importa qual."""
    candidatas = []
    if preferida:
        candidatas.append(preferida)
    candidatas.append(SESSION_FILE)
    candidatas.extend(sorted(SESSAO_DIR.glob("sessao_worker_*.json")))

    for caminho in candidatas:
        if caminho.exists():
            return caminho
    raise FileNotFoundError(
        "Nenhuma sessão encontrada (nem a principal, nem nenhum sessao_worker_*.json). "
        "Rode scripts/teste_sessao_1_capturar.py ou scripts/capturar_sessao_worker.py primeiro."
    )


def _todos_os_checkpoints() -> list[Path]:
    caminhos = list(OUTPUT_DIR.glob("checkpoint_worker_*.json"))
    if checkpoint_mod.CHECKPOINT_FILE.exists():
        caminhos.append(checkpoint_mod.CHECKPOINT_FILE)
    return caminhos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", type=Path, default=None, help="Sessão específica a usar (opcional)")
    args = parser.parse_args()

    sessao = _achar_sessao_valida(args.session)
    print(f"Usando sessão: {sessao}")

    with sync_playwright() as p:
        browser, context, page = abrir_contexto(p, headless=True, session_file=sessao)
        try:
            abrir_tela_processos(page)
            cnpjs = listar_cnpjs(page)
        except (SessaoExpiradaError, PortalIndisponivelError) as e:
            print(f"\nNão foi possível listar os CNPJs: {e}")
            print("Capture uma sessão válida (scripts/capturar_sessao_worker.py ou "
                  "teste_sessao_1_capturar.py) e rode de novo.")
            return
        finally:
            browser.close()

    total_cnpjs = len(cnpjs)
    total_tipos = len(TIPOS_FISCALIZACAO)
    esperadas = {f"{cnpj['value']}|{tipo_value}" for cnpj in cnpjs for tipo_value in TIPOS_FISCALIZACAO}
    total_esperado = len(esperadas)

    completas: set[str] = set()
    # ⚠️ Achado em 19/09/2026 (revisão de robustez pedida pelo usuário): este
    # relatório só olhava pra "varreduras_completas" (a PAGINAÇÃO foi
    # percorrida até o fim) - nunca olhava pra "falhas" (um auto que a
    # paginação VIU, mas cujo download/extração não deu certo). Dava pra
    # terminar aqui com "[OK] 100% completas" pra empresa inteira e mesmo
    # assim faltar dezenas de autos reais na planilha, sem nenhum aviso -
    # exatamente o tipo de garantia falsa que este script existe pra evitar.
    # Agora as falhas de TODOS os checkpoints também são somadas e viram
    # parte do veredito final.
    falhas_por_checkpoint: dict[str, dict] = {}
    caminhos_checkpoint = _todos_os_checkpoints()
    for caminho in caminhos_checkpoint:
        estado = json.loads(caminho.read_text(encoding="utf-8"))
        completas.update(estado.get("varreduras_completas", []))
        falhas = estado.get("falhas", {})
        if falhas:
            falhas_por_checkpoint[caminho.name] = falhas

    confirmadas = esperadas & completas
    faltando = esperadas - completas
    total_falhas = sum(len(f) for f in falhas_por_checkpoint.values())
    paginacao_completa = not faltando

    print(f"\nCheckpoints lidos: {len(caminhos_checkpoint)} ({', '.join(c.name for c in caminhos_checkpoint)})")
    print(f"CNPJs reais no portal: {total_cnpjs} | Tipos de fiscalização: {total_tipos}")
    print(f"Combinações CNPJ×tipo esperadas: {total_esperado}")
    print(f"Paginação confirmada 100% completa: {len(confirmadas)} ({100 * len(confirmadas) / total_esperado:.1f}%)")
    print(f"Autos com falha de download/extração pendente: {total_falhas}")

    if not paginacao_completa:
        print(f"\n[ATENÇÃO] Faltam {len(faltando)} combinação(ões) CNPJ×tipo (paginação) - agrupadas por CNPJ:")
        texto_por_cnpj = {c["value"]: c["texto"] for c in cnpjs}
        nome_por_tipo = {v: n for v, n in TIPOS_FISCALIZACAO.items()}
        faltando_por_cnpj: dict[str, list[str]] = {}
        for chave in faltando:
            cnpj_value, tipo_value = chave.split("|", 1)
            faltando_por_cnpj.setdefault(cnpj_value, []).append(nome_por_tipo.get(tipo_value, tipo_value))

        for cnpj_value, tipos_faltando in sorted(faltando_por_cnpj.items()):
            texto = texto_por_cnpj.get(cnpj_value, cnpj_value)
            print(f"  - {texto}: {', '.join(sorted(tipos_faltando))}")

        print(
            "\nEsses CNPJs/tipos ainda não foram confirmados 100% completos em NENHUMA execução até agora - "
            "rode os workers de novo (ou uma execução sequencial) cobrindo eles pra fechar o restante."
        )

    if total_falhas:
        print(
            f"\n[ATENÇÃO] {total_falhas} auto(s) foram VISTOS na tabela em alguma execução, mas NÃO foram "
            "baixados/extraídos com sucesso (falha de documento específico - independente da paginação estar "
            "completa ou não). Por checkpoint:"
        )
        for nome_checkpoint, falhas in sorted(falhas_por_checkpoint.items()):
            print(f"  - {nome_checkpoint}: {len(falhas)} falha(s)")
        print(
            "\nIsso significa que, mesmo com a paginação 100% completa, a planilha final pode não ter 100% dos "
            "autos reais até essas falhas serem resolvidas. Rode os workers/execução de novo pra retentar "
            "(falhas pendentes são tentadas de novo automaticamente, sem precisar de nenhuma ação manual além "
            "de rodar)."
        )

    if paginacao_completa and not total_falhas:
        print(
            "\n[OK] TODAS as combinações CNPJ×tipo da empresa estão 100% completas - paginação percorrida por "
            "inteiro E nenhuma falha de documento pendente em nenhum checkpoint."
        )
    elif paginacao_completa and total_falhas:
        print(
            "\n[QUASE OK] Paginação 100% completa (vimos todos os autos que existem no portal), mas ainda há "
            "falhas de download/extração pendentes (ver acima) - a planilha final pode não refletir 100% dos "
            "autos reais até elas serem resolvidas."
        )


if __name__ == "__main__":
    main()
