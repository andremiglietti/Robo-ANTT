"""
Entrypoint de um worker individual (arquitetura de múltiplos workers,
17/09/2026 - ver CLAUDE.md e o plano da sessão).

Resolve os caminhos de sessão/checkpoint/planilha PRÓPRIOS desse worker (ver
robo_antt.config) e chama orquestrador.rodar() com eles - cada worker é um
processo de SO separado, com seu próprio navegador Playwright, cuidando só
do pedaço de CNPJs que cai nele (índice % total_workers == worker_id).

Uso direto (normalmente chamado por scripts/lancar_workers.py, não à mão):
    python -m robo_antt.worker_cli --worker-id 0 --total-workers 3
"""
import argparse

from robo_antt import config
from robo_antt.orquestrador import rodar


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", type=int, required=True, help="Número deste worker (0, 1, 2, ...)")
    parser.add_argument("--total-workers", type=int, required=True, help="Quantos workers no total")
    parser.add_argument(
        "--limite-cnpjs",
        type=int,
        default=None,
        help="Opcional: limita quantos CNPJs (já filtrados pra este worker) processar - útil pra teste",
    )
    args = parser.parse_args()

    rodar(
        limite_cnpjs=args.limite_cnpjs,
        session_file=config.sessao_worker(args.worker_id),
        checkpoint_file=config.checkpoint_worker(args.worker_id),
        planilha_path=config.planilha_worker(args.worker_id),
        worker_id=args.worker_id,
        total_workers=args.total_workers,
    )


if __name__ == "__main__":
    main()
