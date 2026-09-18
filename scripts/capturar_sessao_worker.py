"""
Captura a sessão de UM worker e JÁ COLOCA ELE PRA TRABALHAR (arquitetura de
múltiplos workers, 17-18/09/2026 - ver CLAUDE.md e o plano da sessão).

Versão reutilizável do padrão já usado em teste_sessao_dupla_A_capturar.py /
_B_capturar.py - roda esse script UMA VEZ PRA CADA WORKER que for usar
(informando o número quando perguntado), sempre logando com o MESMO
CPF/senha (já confirmado que o portal aceita várias sessões simultâneas com
a mesma conta - ver teste_sessao_dupla_verificar.py).

⚠️ Achado em 18/09/2026: com vários workers, logar em todas as sessões antes
de começar (via scripts/lancar_workers.py) desperdiça tempo de sessão à toa
- o captcha manual é lento, e a sessão do worker 0 já fica "rodando o
relógio" enquanto você ainda está logando o worker 3, 4, 5... Por isso este
script agora dispara o worker EM SEGUNDO PLANO assim que a sessão dele é
salva, sem esperar os outros - roda esse script de novo pro próximo número
assim que terminar, e cada worker começa a trabalhar o quanto antes.

O QUE ESTE SCRIPT FAZ:
1. Pergunta o número do worker (0, 1, 2, ...), quantos workers no total, e
   (opcional) um limite de CNPJs por worker.
2. Abre um navegador (visível).
3. Você faz o login manualmente (CPF/senha + captcha) - o de sempre.
4. Volta aqui no terminal e aperta ENTER.
5. Salva em data/sessao/sessao_worker_{N}.json e JÁ DISPARA esse worker em
   segundo plano (log em data/logs/worker_{N}.log) - não espera os outros.

Se só quiser capturar a sessão SEM iniciar o trabalho agora (ex.: pra
retomar depois com scripts/lancar_workers.py), responda "n" quando
perguntado se quer iniciar.
"""
import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt import config  # noqa: E402

PORTAL_LOGIN_URL = "https://appweb1.antt.gov.br/spmi/Site/Login.aspx?ReturnUrl=%2fspmi%2fSite%2fBoleto%2fListar.aspx"
LOG_DIR = BASE_DIR / "data" / "logs"


def _ler_inteiro(pergunta: str, obrigatorio: bool = True) -> int | None:
    texto = input(pergunta).strip()
    if not texto and not obrigatorio:
        return None
    try:
        return int(texto)
    except ValueError:
        print(f"'{texto}' não é um número válido.")
        return _ler_inteiro(pergunta, obrigatorio)


def _iniciar_worker(worker_id: int, total_workers: int, limite_cnpjs: int | None) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"worker_{worker_id}.log"
    comando = [
        sys.executable,
        "-u",  # sem buffer - achado de 16/09/2026, senão o log só aparece no fim
        "-m",
        "robo_antt.worker_cli",
        "--worker-id",
        str(worker_id),
        "--total-workers",
        str(total_workers),
    ]
    if limite_cnpjs:
        comando += ["--limite-cnpjs", str(limite_cnpjs)]

    log_file = open(log_path, "w", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(BASE_DIR / "src")}
    subprocess.Popen(comando, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(BASE_DIR), env=env)
    print(f"\nWorker {worker_id} iniciado em segundo plano - log em {log_path}")
    print("Pode fechar esta janela. Se tiver mais workers, rode este script de novo pro próximo número.")


def main() -> None:
    print(
        "⚠️ Importante: informe o MESMO 'quantos workers no total' em TODAS as vezes que rodar "
        "esse script hoje (pros workers 0, 1, 2, ...) - se mudar esse número no meio, a divisão "
        "dos CNPJs entre os workers fica errada (alguns CNPJs pulados, outros repetidos)."
    )
    worker_id = _ler_inteiro("\nNúmero deste worker (0, 1, 2, ...): ")
    total_workers = _ler_inteiro("Quantos workers no total? ")
    limite_cnpjs = _ler_inteiro(
        "Limite de CNPJs por worker (Enter pra não limitar - roda todos os que sobrarem pra esse worker): ",
        obrigatorio=False,
    )

    arquivo_sessao = config.sessao_worker(worker_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"\nAbrindo o portal: {PORTAL_LOGIN_URL}")
        page.goto(PORTAL_LOGIN_URL)

        print(f"\n>>> Faça o login manualmente (Worker {worker_id}) na janela do navegador que abriu.")
        print(">>> Resolva o captcha/verificação de segurança normalmente.")
        input(">>> Quando estiver logado e a tela principal do portal aparecer, volte aqui e aperte ENTER... ")

        context.storage_state(path=arquivo_sessao)
        print(f"\nSessão do worker {worker_id} salva com sucesso em: {arquivo_sessao}")

        browser.close()

    resposta = input("\nIniciar esse worker agora, em segundo plano? (S/n): ").strip().lower()
    if resposta in ("", "s", "sim"):
        _iniciar_worker(worker_id, total_workers, limite_cnpjs)
    else:
        print("Ok, sessão salva mas não iniciada. Use scripts/lancar_workers.py quando quiser começar.")


if __name__ == "__main__":
    main()
