"""
TESTE 1.3 — PARTE 2: Testar se a sessão salva funciona sem novo login
=======================================================================

O QUE ESTE SCRIPT FAZ:
1. Abre um navegador NOVO, carregando a sessão salva pelo script 1.
2. Navega direto para uma página que exige estar logado (ex.: a tela
   de consulta de processos, ou a tela de seleção de CNPJ).
3. Você observa: apareceu a página de LOGIN de novo, ou já apareceu
   o conteúdo interno (sinal de que a sessão funcionou)?

IMPORTANTE: rode este script em um momento diferente / janela diferente
do script 1, para simular de verdade o robô "herdando" a sessão, em vez
de continuar na mesma janela que já estava logada.

ANTES DE RODAR:
- Preencha a variável PORTAL_PAGINA_PROTEGIDA com a URL de uma página
  interna do portal (que só aparece depois de logado).
- Certifique-se de que o script 1 já rodou e gerou o arquivo
  "sessao_antt.json" na mesma pasta.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

# >>> PREENCHER: URL de uma página interna que exige login <<<
PORTAL_PAGINA_PROTEGIDA = "https://appweb1.antt.gov.br/spmi/Site/Default.aspx"

ARQUIVO_SESSAO = Path(__file__).resolve().parent.parent / "data" / "sessao" / "sessao_antt.json"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # Aqui está o pulo do gato: cria o contexto JÁ carregando a sessão salva
        context = browser.new_context(storage_state=ARQUIVO_SESSAO)
        page = context.new_page()

        print(f"Acessando diretamente a página interna: {PORTAL_PAGINA_PROTEGIDA}")
        print("(sem preencher CPF/senha desta vez)")
        page.goto(PORTAL_PAGINA_PROTEGIDA)

        page.wait_for_timeout(3000)  # espera 3 segundos para a página carregar

        print("\n>>> Observe a janela do navegador:")
        print("    - Se apareceu a tela de LOGIN novamente => a sessão NÃO foi reaproveitada (teste falhou).")
        print("    - Se apareceu o conteúdo interno do portal direto => a sessão FOI reaproveitada (teste passou).")
        input("\nApós observar, aperte ENTER para fechar o navegador... ")

        browser.close()


if __name__ == "__main__":
    main()
