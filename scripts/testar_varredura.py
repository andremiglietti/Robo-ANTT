"""
TESTE — varredura de CNPJs e paginação (Dia 5 do cronograma)
================================================================

Só LEITURA: lista os CNPJs, busca os processos do primeiro CNPJ (iterando por
todos os tipos de fiscalização - buscar sem filtro trava o portal) e percorre
todas as páginas de resultado. NÃO clica na lupa/"Vistas" - não baixa nenhum
PDF nem solicita vistas a nenhum processo, só lê a tabela.

O código já espera um pouco entre cada ação pra não sobrecarregar o portal
(ver PAUSA_ENTRE_ACOES_MS em config.py) - rodar esse script inteiro pode levar
alguns minutos, e é assim mesmo, não é bug.

Requer que data/sessao/sessao_antt.json já exista e esteja válida.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from playwright.sync_api import sync_playwright

from robo_antt.portal import (
    PortalIndisponivelError,
    SessaoExpiradaError,
    abrir_contexto,
    abrir_tela_processos,
    listar_cnpjs,
    varrer_cnpj,
)


def main():
    with sync_playwright() as p:
        browser, context, page = abrir_contexto(p, headless=True)
        try:
            print("Abrindo a tela de processos (VistasAoProcesso.aspx)...")
            abrir_tela_processos(page)

            cnpjs = listar_cnpjs(page)
            print(f"\n{len(cnpjs)} CNPJs encontrados no seletor 'Representado':")
            for c in cnpjs[:10]:
                print(f"  - {c['texto']}")
            if len(cnpjs) > 10:
                print(f"  ... e mais {len(cnpjs) - 10}")

            if not cnpjs:
                print("Nenhum CNPJ encontrado - abortando teste.")
                return

            primeiro = cnpjs[0]
            print(f"\nBuscando processos de: {primeiro['texto']} (todos os tipos de fiscalização)...")
            resultados = varrer_cnpj(page, primeiro["indice"], primeiro["value"])

            print(f"\n{len(resultados)} processos encontrados no total (todas as páginas).")
            print("Primeiros 5:")
            for r in resultados[:5]:
                print(f"  - {r['auto_infracao']} | {r['numero_processo']} | {r['situacao']} | {r['data_auto']}")

        except SessaoExpiradaError as e:
            print(f"\n[SESSÃO EXPIRADA] {e}")
        except PortalIndisponivelError as e:
            print(f"\n[PORTAL INDISPONÍVEL] {e}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
