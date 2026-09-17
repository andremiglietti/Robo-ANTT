"""
TESTE DE CONCORRÊNCIA — sessões independentes (Sessão A x Sessão B)
=====================================================================

Continuação do teste de 16/09/2026 (2 abas da MESMA sessão, que ficaram na
fila uma atrás da outra - achado documentado no CLAUDE.md). Esse aqui é
diferente: usa a Sessão A e a Sessão B (2 logins de verdade, 2 cookies
distintos - ver scripts/teste_sessao_dupla_*_capturar.py e
teste_sessao_dupla_verificar.py, que já confirmou que as duas continuam
válidas ao mesmo tempo).

Pergunta que este teste responde: o enfileiramento do servidor (achado de
16/09/2026) é por SESSÃO (cookie) ou pela CONTA/CPF inteira? Se as duas
buscas, com sessões DIFERENTES, terminarem rápido e ao mesmo tempo (sem
uma esperar a outra), significa que dá pra ter workers de verdade. Se uma
ficar esperando a outra mesmo com sessões diferentes, o gargalo é da conta,
não da sessão, e múltiplas sessões não ajudam em nada.

Mesmo CNPJ/tipo do teste de 16/09/2026 (pra comparar direito):
  Sessão A -> CNPJ índice 1 (matriz), tipo "Excesso de Peso"
  Sessão B -> CNPJ índice 2, tipo "Cargas"

Rode sozinho (sem interação manual) - as sessões já foram capturadas antes.
"""
import asyncio
import time

from playwright.async_api import async_playwright

from robo_antt.config import SEL, TIPOS_FISCALIZACAO, VISTAS_URL
from pathlib import Path

ARQUIVO_A = Path(__file__).resolve().parent.parent / "data" / "sessao" / "teste_dupla_sessao_A.json"
ARQUIVO_B = Path(__file__).resolve().parent.parent / "data" / "sessao" / "teste_dupla_sessao_B.json"

TIMEOUT_GENEROSO = 120000  # ms - mesmo valor do teste confirmatório de 16/09/2026

inicio_global = time.time()


def _log(rotulo: str, msg: str) -> None:
    print(f"[{rotulo}] {time.time() - inicio_global:.2f}s {msg}", flush=True)


async def _buscar(playwright, arquivo_sessao: Path, rotulo: str, cnpj_indice: int, tipo_value: str, tipo_nome: str) -> None:
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(storage_state=str(arquivo_sessao))
    page = await context.new_page()

    t0 = time.time()
    await page.goto(VISTAS_URL, wait_until="commit", timeout=60000)
    await page.wait_for_selector(SEL["representado"], state="attached", timeout=30000)
    _log(rotulo, "página carregada")

    # seleção de CNPJ via chosen.js (mesmo truque de portal.selecionar_cnpj)
    await page.click(SEL["representado_chosen"])
    await page.click(f'{SEL["representado_chosen"]} li[data-option-array-index="{cnpj_indice}"]')
    await page.wait_for_timeout(300)
    _log(rotulo, f"cnpj índice {cnpj_indice} selecionado")

    await page.select_option(SEL["tipo_fiscalizacao"], value=tipo_value)
    _log(rotulo, f"tipo '{tipo_nome}' selecionado, clicando pesquisar")

    await page.click(SEL["btn_pesquisar"])
    _log(rotulo, "clicou pesquisar, esperando resultado (timeout generoso)")

    try:
        await page.wait_for_function(
            """(sel) => {
                const tabela = document.querySelector(sel);
                return !!tabela && tabela.querySelectorAll('tr').length > 0;
            }""",
            arg=SEL["tabela_resultado"],
            timeout=TIMEOUT_GENEROSO,
        )
        dt = time.time() - t0
        linhas = await page.locator(f'{SEL["tabela_resultado"]} tr').all_inner_texts()
        primeiras = [l.split("\n")[0].strip() for l in linhas if l.strip()][:5]
        _log(rotulo, f"resultado chegou depois de {dt:.1f}s: {primeiras}")
    except Exception as e:
        dt = time.time() - t0
        _log(rotulo, f"NÃO respondeu dentro do timeout generoso ({dt:.1f}s): {e}")

    await browser.close()


async def main():
    print("Disparando 2 buscas SIMULTÂNEAS com SESSÕES INDEPENDENTES (timeout generoso de 120s cada)...", flush=True)
    async with async_playwright() as p:
        await asyncio.gather(
            _buscar(p, ARQUIVO_A, "Sessão A", 1, "2", TIPOS_FISCALIZACAO["2"]),
            _buscar(p, ARQUIVO_B, "Sessão B", 2, "3", TIPOS_FISCALIZACAO["3"]),
        )
    print(f"\nTempo total (as 2 juntas): {time.time() - inicio_global:.1f}s", flush=True)
    print("Se as duas terminaram rápido e perto uma da outra (não uma esperando a outra),", flush=True)
    print("o enfileiramento é por sessão, não por conta - workers de verdade seriam viáveis.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
