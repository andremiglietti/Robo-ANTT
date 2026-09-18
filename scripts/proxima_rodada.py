"""
Rebalanceamento por rodadas (18/09/2026 - ver CLAUDE.md e o plano da
sessão): depois de uma rodada de workers terminar, calcula quais CNPJs
ainda têm pelo menos 1 tipo de fiscalização não confirmado como completo
(juntando os checkpoints de TODOS os workers já rodados até agora - mesma
lógica de scripts/relatorio_completude.py) e dispara uma NOVA rodada de
workers cobrindo só esses CNPJs restantes, redistribuídos entre quantos
workers estiverem disponíveis agora.

Por que existe: a partição original (índice % total_workers) é fixa pros
61 CNPJs completos - se um worker termina rápido (CNPJs pequenos) enquanto
outro ainda tem CNPJs pesados pela frente, o primeiro fica ocioso sem
ajudar o outro. Rodar em RODADAS (em vez de tentar coordenar os workers em
tempo real, o que exigiria uma fila compartilhada com trava entre
processos - mais arriscado de dar bug) resolve isso de forma simples: cada
rodada nova redistribui só o que falta entre quantos workers estiverem com
sessão pronta naquele momento.

PRÉ-REQUISITO: sessões dos workers desta rodada já capturadas
(scripts/capturar_sessao_worker.py) - não precisa ser o mesmo número de
workers de rodadas anteriores.

USO:
    python scripts/proxima_rodada.py --workers 3
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt import checkpoint as checkpoint_mod  # noqa: E402
from robo_antt import config  # noqa: E402
from robo_antt.config import OUTPUT_DIR, SESSAO_DIR, SESSION_FILE, TIPOS_FISCALIZACAO  # noqa: E402
from robo_antt.portal import PortalIndisponivelError, SessaoExpiradaError, abrir_contexto, abrir_tela_processos, listar_cnpjs  # noqa: E402

LOG_DIR = BASE_DIR / "data" / "logs"
ARQUIVO_PENDENTES = OUTPUT_DIR / "cnpjs_pendentes.json"


def _achar_sessao_valida() -> Path:
    candidatas = [SESSION_FILE, *sorted(SESSAO_DIR.glob("sessao_worker_*.json"))]
    for caminho in candidatas:
        if caminho.exists():
            return caminho
    raise FileNotFoundError(
        "Nenhuma sessão encontrada pra listar os CNPJs. Rode scripts/capturar_sessao_worker.py primeiro."
    )


def _cnpjs_pendentes() -> list[dict] | None:
    """Lista os CNPJs que ainda têm pelo menos 1 tipo de fiscalização não
    confirmado como completo, juntando os checkpoints de todos os workers
    já rodados. Devolve None se não conseguir nem listar os CNPJs (sessão
    expirada/portal indisponível)."""
    sessao = _achar_sessao_valida()
    print(f"Usando sessão: {sessao}")
    with sync_playwright() as p:
        browser, context, page = abrir_contexto(p, headless=True, session_file=sessao)
        try:
            abrir_tela_processos(page)
            cnpjs = listar_cnpjs(page)
        except (SessaoExpiradaError, PortalIndisponivelError) as e:
            print(f"\nNão foi possível listar os CNPJs: {e}")
            return None
        finally:
            browser.close()

    completas: set[str] = set()
    for caminho in OUTPUT_DIR.glob("checkpoint_worker_*.json"):
        estado = json.loads(caminho.read_text(encoding="utf-8"))
        completas.update(estado.get("varreduras_completas", []))
    if checkpoint_mod.CHECKPOINT_FILE.exists():
        estado = json.loads(checkpoint_mod.CHECKPOINT_FILE.read_text(encoding="utf-8"))
        completas.update(estado.get("varreduras_completas", []))

    pendentes = [
        cnpj
        for cnpj in cnpjs
        if any(f"{cnpj['value']}|{tipo_value}" not in completas for tipo_value in TIPOS_FISCALIZACAO)
    ]
    return pendentes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, required=True, help="Quantos workers usar nesta rodada")
    args = parser.parse_args()
    total_workers = args.workers

    faltando_sessao = [i for i in range(total_workers) if not config.sessao_worker(i).exists()]
    if faltando_sessao:
        print("Faltam sessões pros seguintes workers - rode scripts/capturar_sessao_worker.py pra cada um deles:")
        for i in faltando_sessao:
            print(f"  worker {i}: {config.sessao_worker(i)}")
        return

    pendentes = _cnpjs_pendentes()
    if pendentes is None:
        return
    if not pendentes:
        print("\n[OK] Nenhum CNPJ pendente - a empresa inteira já está 100% confirmada completa!")
        return

    print(
        f"\n{len(pendentes)} CNPJ(s) ainda têm tipo(s) de fiscalização pendente(s) - "
        f"redistribuindo entre {total_workers} worker(s) nesta rodada."
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARQUIVO_PENDENTES.write_text(json.dumps([c["value"] for c in pendentes]), encoding="utf-8")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    processos = []
    for worker_id in range(total_workers):
        log_path = LOG_DIR / f"worker_{worker_id}.log"
        comando = [
            sys.executable,
            "-u",
            "-m",
            "robo_antt.worker_cli",
            "--worker-id",
            str(worker_id),
            "--total-workers",
            str(total_workers),
            "--cnpjs-arquivo",
            str(ARQUIVO_PENDENTES),
        ]
        log_file = open(log_path, "w", encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(BASE_DIR / "src")}
        processo = subprocess.Popen(comando, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(BASE_DIR), env=env)
        processos.append((worker_id, processo, log_file, log_path))
        print(f"Worker {worker_id} iniciado (PID {processo.pid}) - log em {log_path}")

    print(f"\n{total_workers} worker(s) rodando esta rodada. Esperando todos terminarem...\n")
    for worker_id, processo, log_file, log_path in processos:
        codigo = processo.wait()
        log_file.close()
        status = "OK" if codigo == 0 else f"código de saída {codigo}"
        print(f"Worker {worker_id} terminou ({status}) - log completo em {log_path}")

    print(
        "\nTodos os workers desta rodada terminaram. Rode scripts/relatorio_completude.py pra conferir "
        "o status atualizado, e scripts/proxima_rodada.py de novo se ainda faltar algo."
    )


if __name__ == "__main__":
    main()
