"""
TESTE 1.3 — PARTE 1: Capturar a sessão após login manual
=========================================================

O QUE ESTE SCRIPT FAZ:
1. Abre um navegador (visível, não escondido).
2. Você faz o login manualmente (CPF/senha + captcha).
3. Depois de logado, você volta aqui no terminal e aperta ENTER.
4. O script salva a sessão autenticada num arquivo chamado "sessao_antt.json".

ANTES DE RODAR:
- Preencha a variável PORTAL_LOGIN_URL abaixo com a URL real de login do portal.
- Instale as dependências (rode uma vez só, no terminal):
    pip install playwright
    playwright install chromium
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

# >>> PREENCHER: URL da página de login do portal da ANTT <<<
PORTAL_LOGIN_URL = "https://appweb1.antt.gov.br/spmi/Site/Login.aspx?ReturnUrl=%2fspmi%2fSite%2fBoleto%2fListar.aspx"

ARQUIVO_SESSAO = Path(__file__).resolve().parent.parent / "data" / "sessao" / "sessao_antt.json"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=False = navegador visível
        context = browser.new_context()
        page = context.new_page()

        print(f"Abrindo o portal: {PORTAL_LOGIN_URL}")
        page.goto(PORTAL_LOGIN_URL)

        print("\n>>> Faça o login manualmente na janela do navegador que abriu.")
        print(">>> Resolva o captcha/verificação de segurança normalmente.")
        input(">>> Quando estiver logado e a tela principal do portal aparecer, volte aqui e aperte ENTER... ")

        # Salva cookies + estado de login da sessão atual
        context.storage_state(path=ARQUIVO_SESSAO)
        print(f"\nSessão salva com sucesso em: {ARQUIVO_SESSAO}")
        print("Pode fechar o navegador agora. Prossiga para o script 2 (teste_sessao_2_testar.py).")

        browser.close()


if __name__ == "__main__":
    main()
