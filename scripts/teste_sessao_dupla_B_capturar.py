"""
TESTE DE SESSÕES SIMULTÂNEAS — PARTE 2: capturar a Sessão B
==============================================================

Rode DEPOIS de scripts/teste_sessao_dupla_A_capturar.py.

O QUE ESTE SCRIPT FAZ:
1. Abre um navegador NOVO (visível).
2. Você faz o login manualmente de novo - com o MESMO CPF/senha da
   Sessão A, resolvendo o captcha de novo (é um login de verdade,
   independente do da Sessão A).
3. Volta aqui no terminal e aperta ENTER.
4. Salva em "teste_dupla_sessao_B.json" (arquivo separado, não afeta
   o robô nem a Sessão A já salva).

DEPOIS DE RODAR ESTE: rode scripts/teste_sessao_dupla_verificar.py
(esse eu rodo sozinho, sem precisar de login manual) para ver se as
duas sessões continuam válidas ao mesmo tempo.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

PORTAL_LOGIN_URL = "https://appweb1.antt.gov.br/spmi/Site/Login.aspx?ReturnUrl=%2fspmi%2fSite%2fBoleto%2fListar.aspx"

ARQUIVO_SESSAO = Path(__file__).resolve().parent.parent / "data" / "sessao" / "teste_dupla_sessao_B.json"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"Abrindo o portal: {PORTAL_LOGIN_URL}")
        page.goto(PORTAL_LOGIN_URL)

        print("\n>>> Faça o login manualmente (Sessão B) na janela do navegador que abriu.")
        print(">>> Use o MESMO CPF/senha de sempre - é pra ser um login de verdade,")
        print(">>> separado do que você já fez pra Sessão A.")
        input(">>> Quando estiver logado e a tela principal do portal aparecer, volte aqui e aperte ENTER... ")

        context.storage_state(path=ARQUIVO_SESSAO)
        print(f"\nSessão B salva com sucesso em: {ARQUIVO_SESSAO}")
        print("Pode fechar o navegador agora. Me avise que já rodei a verificação.")

        browser.close()


if __name__ == "__main__":
    main()
