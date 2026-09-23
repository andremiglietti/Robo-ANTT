"""
Preenche a coluna "Situação" das linhas JÁ REGISTRADAS na planilha final,
revisitando o portal (ver CLAUDE.md, 23/09/2026).

Por que precisa do portal (diferente dos outros backfills de hoje, que
eram 100% locais): "Situação" vem da tabela de RESULTADOS DE BUSCA do
portal, não do PDF - não tem como descobrir isso reabrindo um arquivo já
em disco.

Bem mais rápido que uma varredura normal: pula completamente o
download/extração de PDF - só faz busca + leitura de tabela pra cada
combinação CNPJ×tipo, e atualiza a planilha com o que encontrar. Nunca
sobrescreve uma célula que já tem valor (mesma garantia de
atualizar_campos_vazios()).

⚠️ A partir de 23/09/2026, orquestrador.processar_linha() já faz esse
backfill sozinho durante qualquer varredura normal (ver
_atualizar_situacao_se_necessario()) - rodar este script é só pra um
catch-up pontual das ~4187 linhas que já existiam ANTES dessa correção,
sem precisar esperar a próxima varredura completa (que pode levar
várias horas) só por causa disso.

USO:
    python scripts/backfill_situacao.py --session data/sessao/sessao_worker_0.json
"""
import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt.config import PAUSA_ENTRE_ACOES_MS, PLANILHA_PATH, TIPOS_FISCALIZACAO  # noqa: E402
from robo_antt.planilha import abrir_ou_criar, atualizar_campos_vazios, salvar  # noqa: E402
from robo_antt.portal import (  # noqa: E402
    PortalIndisponivelError,
    SessaoExpiradaError,
    abrir_contexto,
    abrir_tela_processos,
    buscar,
    iterar_paginas_resultado,
    listar_cnpjs,
    selecionar_cnpj,
    selecionar_tipo_fiscalizacao,
)


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(encoding, errors="replace").decode(encoding), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", type=Path, required=True, help="Sessão válida a usar (ex.: data/sessao/sessao_worker_0.json)")
    args = parser.parse_args()

    if not args.session.exists():
        _log(f"[ATENÇÃO] Sessão não encontrada: {args.session}")
        return

    _log(f"Planilha: {PLANILHA_PATH}")
    wb = abrir_ou_criar(PLANILHA_PATH)

    total_atualizado = 0
    total_combinacoes_tentadas = 0

    with sync_playwright() as p:
        browser, context, page = abrir_contexto(p, headless=True, session_file=args.session)
        try:
            abrir_tela_processos(page)
            cnpjs = listar_cnpjs(page)
            _log(f"{len(cnpjs)} CNPJs encontrados.\n")

            for i, cnpj in enumerate(cnpjs, start=1):
                try:
                    selecionar_cnpj(page, cnpj["value"], valor_esperado=cnpj["value"])
                except Exception as e:
                    _log(f"  [{i}/{len(cnpjs)}] {cnpj['texto']}: falha ao selecionar CNPJ ({e}) - pulando")
                    continue
                time.sleep(PAUSA_ENTRE_ACOES_MS / 1000)

                atualizados_neste_cnpj = 0
                for tipo_value, tipo_nome in TIPOS_FISCALIZACAO.items():
                    total_combinacoes_tentadas += 1
                    try:
                        selecionar_tipo_fiscalizacao(page, tipo_value)
                        buscar(page)
                        for pagina in iterar_paginas_resultado(page):
                            for row in pagina:
                                situacao = row.get("situacao")
                                if not situacao:
                                    continue
                                preenchidos = atualizar_campos_vazios(wb, row["auto_infracao"], {"situacao": situacao})
                                atualizados_neste_cnpj += preenchidos
                    except (SessaoExpiradaError, PortalIndisponivelError) as e:
                        _log(f"\n[PAROU] {e}")
                        salvar(wb, PLANILHA_PATH)
                        _log(
                            f"Planilha salva com o progresso até aqui - {total_atualizado + atualizados_neste_cnpj} "
                            "Situação(ões) preenchida(s). Rode de novo mais tarde pra continuar."
                        )
                        return
                    except Exception as e:
                        _log(f"  [{i}/{len(cnpjs)}] {cnpj['texto']} | {tipo_nome}: erro ({e}) - pulando esse tipo")
                        continue

                total_atualizado += atualizados_neste_cnpj
                _log(
                    f"[{i}/{len(cnpjs)}] {cnpj['texto']}: {atualizados_neste_cnpj} preenchida(s) "
                    f"({total_atualizado} no total até agora)"
                )
                # salva a cada CNPJ - mesmo cuidado dos outros scripts (não perder
                # progresso de uma execução longa se algo interromper no meio).
                salvar(wb, PLANILHA_PATH)
        finally:
            browser.close()

    _log(
        f"\nConcluído. {total_atualizado} célula(s) de Situação preenchida(s), "
        f"{total_combinacoes_tentadas} combinação(ões) CNPJ×tipo tentada(s)."
    )


if __name__ == "__main__":
    main()
