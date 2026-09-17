"""
Launcher da arquitetura de múltiplos workers (17/09/2026 - ver CLAUDE.md e
o plano da sessão).

O QUE ESTE SCRIPT FAZ:
1. Confere que a sessão de CADA worker já foi capturada (ver
   scripts/capturar_sessao_worker.py) - falha rápido e claro se faltar
   alguma, em vez de começar a rodar pela metade.
2. Sobe um processo por worker (cada um com seu próprio navegador
   Playwright), cada um cuidando de um pedaço dos CNPJs (índice %
   total_workers == worker_id - ver orquestrador.rodar()).
3. Cada worker escreve seu progresso (mesma saída detalhada de sempre) num
   arquivo de log próprio em data/logs/, pra não embaralhar a saída de N
   processos num terminal só.
4. Espera todos terminarem e avisa onde ficou cada log.

DEPOIS: rode scripts/consolidar_planilhas.py pra juntar o que cada worker
achou na planilha real do SharePoint.

USO:
    python scripts/lancar_workers.py --workers 3
    python scripts/lancar_workers.py --workers 3 --limite-cnpjs 5   (teste pequeno)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt import config  # noqa: E402

LOG_DIR = BASE_DIR / "data" / "logs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, required=True, help="Quantos workers rodar em paralelo")
    parser.add_argument(
        "--limite-cnpjs", type=int, default=None, help="Opcional: limita CNPJs por worker (útil pra teste pequeno)"
    )
    args = parser.parse_args()
    total_workers = args.workers

    faltando = [i for i in range(total_workers) if not config.sessao_worker(i).exists()]
    if faltando:
        print("Faltam sessões pros seguintes workers - rode scripts/capturar_sessao_worker.py pra cada um deles:")
        for i in faltando:
            print(f"  worker {i}: {config.sessao_worker(i)}")
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    processos = []
    for worker_id in range(total_workers):
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
        if args.limite_cnpjs:
            comando += ["--limite-cnpjs", str(args.limite_cnpjs)]

        log_file = open(log_path, "w", encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(BASE_DIR / "src")}
        processo = subprocess.Popen(
            comando,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(BASE_DIR),
            env=env,
        )
        processos.append((worker_id, processo, log_file, log_path))
        print(f"Worker {worker_id} iniciado (PID {processo.pid}) - log em {log_path}")

    print(f"\n{total_workers} worker(s) rodando em paralelo. Acompanhe cada log em tempo real (ex.: Get-Content -Wait).")
    print("Esperando todos terminarem...\n")

    for worker_id, processo, log_file, log_path in processos:
        codigo = processo.wait()
        log_file.close()
        status = "OK" if codigo == 0 else f"código de saída {codigo}"
        print(f"Worker {worker_id} terminou ({status}) - log completo em {log_path}")

    print("\nTodos os workers terminaram. Rode scripts/consolidar_planilhas.py pra juntar os resultados.")


if __name__ == "__main__":
    main()
