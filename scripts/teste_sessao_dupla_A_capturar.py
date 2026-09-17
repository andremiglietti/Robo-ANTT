"""
TESTE DE SESSÕES SIMULTÂNEAS — PARTE 1: capturar a Sessão A
==============================================================

Objetivo do teste (ver CLAUDE.md, ideia discutida em 17/09/2026): saber se
o portal da ANTT permite 2 sessões independentes ativas ao mesmo tempo com
o MESMO CPF - diferente do teste de "duplicar aba" já feito (que usa o
MESMO cookie em 2 abas e sempre fica na fila). Se 2 logins separados
puderem ficar válidos ao mesmo tempo, dá pra ter "workers" de verdade.

O QUE ESTE SCRIPT FAZ:
1. Abre um navegador (visível).
2. Você faz o login manualmente (CPF/senha + captcha) - o de sempre.
3. Volta aqui no terminal e aperta ENTER.
4. Salva a sessão em "teste_dupla_sessao_A.json" (arquivo SEPARADO do
   sessao_antt.json usado pelo robô de verdade - não afeta o robô).

DEPOIS DE RODAR ESTE: feche o navegador e rode
scripts/teste_sessao_dupla_B_capturar.py, logando de novo com o MESMO
CPF/senha numa janela nova.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

PORTAL_LOGIN_URL = "https://appweb1.antt.gov.br/spmi/Site/Login.aspx?ReturnUrl=%2fspmi%2fSite%2fBoleto%2fListar.aspx"

ARQUIVO_SESSAO = Path(__file__).resolve().parent.parent / "data" / "sessao" / "teste_dupla_sessao_A.json"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"Abrindo o portal: {PORTAL_LOGIN_URL}")
        page.goto(PORTAL_LOGIN_URL)

        print("\n>>> Faça o login manualmente (Sessão A) na janela do navegador que abriu.")
        print(">>> Resolva o captcha/verificação de segurança normalmente.")
        input(">>> Quando estiver logado e a tela principal do portal aparecer, volte aqui e aperte ENTER... ")

        context.storage_state(path=ARQUIVO_SESSAO)
        print(f"\nSessão A salva com sucesso em: {ARQUIVO_SESSAO}")
        print("Pode fechar o navegador agora. Em seguida, rode teste_sessao_dupla_B_capturar.py")
        print("(logando de NOVO com o MESMO CPF/senha, numa janela nova).")

        browser.close()


if __name__ == "__main__":
    main()
