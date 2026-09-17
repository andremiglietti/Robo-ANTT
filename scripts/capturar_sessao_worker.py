"""
Captura a sessão de UM worker (arquitetura de múltiplos workers, 17/09/2026
- ver CLAUDE.md e o plano da sessão).

Versão reutilizável do padrão já usado em teste_sessao_dupla_A_capturar.py /
_B_capturar.py - roda esse script UMA VEZ PRA CADA WORKER que for usar
(informando o número quando perguntado), sempre logando com o MESMO
CPF/senha (já confirmado que o portal aceita várias sessões simultâneas com
a mesma conta - ver teste_sessao_dupla_verificar.py).

O QUE ESTE SCRIPT FAZ:
1. Pergunta o número do worker (0, 1, 2, ...).
2. Abre um navegador (visível).
3. Você faz o login manualmente (CPF/senha + captcha) - o de sempre.
4. Volta aqui no terminal e aperta ENTER.
5. Salva em data/sessao/sessao_worker_{N}.json.

DEPOIS DE CAPTURAR A SESSÃO DE TODOS OS WORKERS: rode
scripts/lancar_workers.py --workers N
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt import config  # noqa: E402

PORTAL_LOGIN_URL = "https://appweb1.antt.gov.br/spmi/Site/Login.aspx?ReturnUrl=%2fspmi%2fSite%2fBoleto%2fListar.aspx"


def main() -> None:
    texto = input("Número deste worker (0, 1, 2, ...): ").strip()
    try:
        worker_id = int(texto)
    except ValueError:
        print(f"'{texto}' não é um número válido. Rode de novo e informe só o número (ex.: 0).")
        return

    arquivo_sessao = config.sessao_worker(worker_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"Abrindo o portal: {PORTAL_LOGIN_URL}")
        page.goto(PORTAL_LOGIN_URL)

        print(f"\n>>> Faça o login manualmente (Worker {worker_id}) na janela do navegador que abriu.")
        print(">>> Resolva o captcha/verificação de segurança normalmente.")
        input(">>> Quando estiver logado e a tela principal do portal aparecer, volte aqui e aperte ENTER... ")

        context.storage_state(path=arquivo_sessao)
        print(f"\nSessão do worker {worker_id} salva com sucesso em: {arquivo_sessao}")
        print("Pode fechar o navegador. Se tiver mais workers, rode este script de novo pro próximo número.")

        browser.close()


if __name__ == "__main__":
    main()
