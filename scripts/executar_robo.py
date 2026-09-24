"""
IHM (interface simplificada de execução) do robô ANTT - pensada pra pessoa
responsável, que NÃO é técnica (Dia 12 do cronograma, ver CLAUDE.md e o
plano combinado em 21-22/09/2026).

Diferente de scripts/capturar_sessao_worker.py + scripts/lancar_workers.py
(que continuam existindo do jeito que estão, pra teste/depuração), este
script é o ÚNICO que a pessoa responsável precisa saber usar no dia a dia:

    1. Pergunta só UMA coisa: quantos workers usar (recomendado: 5).
    2. Pra cada worker, abre o navegador e pede o login manual (CPF/senha +
       captcha) - a única parte que precisa de uma pessoa de verdade. Assim
       que loga, o worker já começa a trabalhar sozinho em segundo plano -
       sem perguntar mais nada (sempre varredura completa, nunca limitada;
       sempre inicia sozinho).
    3. Depois do último login, mostra um painel de andamento simples
       (sem termos técnicos), atualizado a cada 1 minuto, até todos os
       workers terminarem - achado de 22/09/2026: sem isso, a pessoa fica
       olhando pra uma tela parada por horas, sem saber se está
       funcionando ou travado (o progresso de verdade vai pra arquivos de
       log, que ela não tem motivo pra saber ler).
    4. Junta os resultados de todos na planilha final automaticamente (não
       depende de lembrar de rodar scripts/consolidar_planilhas.py à parte -
       achado de 21/09/2026: esse passo manual é fácil de esquecer).
    5. Mostra um resumo final em português simples, sem termos técnicos.

Se a sessão de algum worker expirar no meio (acontece, duração imprevisível -
ver CLAUDE.md) ou a internet cair, esse worker específico para sozinho de
forma segura (nada se perde) e informa isso no resumo final - é só rodar
este mesmo script de novo depois pra continuar de onde parou.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt import config  # noqa: E402

PORTAL_LOGIN_URL = "https://appweb1.antt.gov.br/spmi/Site/Login.aspx?ReturnUrl=%2fspmi%2fSite%2fBoleto%2fListar.aspx"
LOG_DIR = BASE_DIR / "data" / "logs"


def _log(msg: str) -> None:
    """print com fallback defensivo contra UnicodeEncodeError (mesmo padrão
    de orquestrador.py) - essa é a tela que a pessoa NÃO-técnica está
    olhando, então nunca pode quebrar por causa de 1 caractere estranho no
    console dela (achado repetido várias vezes ao longo do projeto - ver
    CLAUDE.md)."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(encoding, errors="replace").decode(encoding), flush=True)


def _ler_quantidade_workers() -> int:
    while True:
        texto = input(
            "\nQuantos 'trabalhadores' (workers) usar nesta varredura? "
            "(recomendado: 5 - mais rápido, mas exige um login por worker)\n"
            "Quantidade: "
        ).strip()
        try:
            n = int(texto)
            if n >= 1:
                return n
        except ValueError:
            pass
        _log("Digite um número inteiro de 1 ou mais.")


def _login_worker(worker_id: int) -> None:
    """Abre o navegador, espera o login manual, e salva a sessão - mesma
    mecânica de scripts/capturar_sessao_worker.py, sem as perguntas extras
    (limite de CNPJs, "iniciar agora?") que só fazem sentido em teste."""
    arquivo_sessao = config.sessao_worker(worker_id)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        _log(f"\nAbrindo o portal da ANTT pro login {worker_id + 1}...")
        page.goto(PORTAL_LOGIN_URL)

        _log(f">>> Faça o login manualmente (CPF/senha + verificação de segurança) na janela que abriu.")
        input(">>> Quando a tela principal do portal aparecer, volte aqui e aperte ENTER... ")

        context.storage_state(path=arquivo_sessao)
        browser.close()
    _log(f"Login {worker_id + 1} salvo com sucesso.")


def _iniciar_worker(worker_id: int, total_workers: int) -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
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
    ]
    log_file = open(log_path, "w", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(BASE_DIR / "src")}
    processo = subprocess.Popen(comando, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(BASE_DIR), env=env)
    _log(f"Worker {worker_id} começou a trabalhar em segundo plano (log em {log_path.name}).")
    return processo


# Casa com o formato exato de "[Progresso]" gravado por orquestrador.py -
# só usa a parte sem acento (mais robusta contra mojibake em consoles que
# não são UTF-8, achado repetido várias vezes ao longo do projeto - ver
# CLAUDE.md) pra achar o número de itens e de multas processadas.
_RE_PROGRESSO = re.compile(r"\[Progresso\]\s*(\d+)/(\d+).*?total geral:\s*(\d+)\s*processado", re.DOTALL)

# "[Item X/Y | ...]" é impressa a cada COMBINAÇÃO tentada (a cada item, não
# só a cada 10 como o "[Progresso]" acima) - usada como fallback pra ter
# algum sinal de vida antes do primeiro checkpoint de 10. Não depende do
# que vem depois do "|" (CNPJ pode até vir vazio em alguns casos raros).
_RE_ITEM = re.compile(r"\[Item\s+(\d+)/(\d+)\s*\|")


def _status_legivel(log_path: Path) -> str:
    """Lê o log de 1 worker e devolve 1 linha de status em português comum,
    sem termos técnicos (nada de 'checkpoint', 'CNPJ×tipo', 'exceção' etc.)
    - pensado pra pessoa não-técnica acompanhar sem precisar entender nada
    de programação. Achado em 22/09/2026: sem isso, depois dos logins a
    tela fica parada por horas sem nenhum sinal de vida."""
    if not log_path.exists():
        return "iniciando..."
    texto = log_path.read_text(encoding="utf-8", errors="replace")
    if "[PAROU]" in texto:
        return "[PAROU] parou antes de terminar (sessão expirada ou problema de conexão) - rode o programa de novo pra continuar"
    if "VERIFICA" in texto and "COMPLETUDE" in texto:
        # ⚠️ não depende de nenhuma palavra acentuada no meio do padrão -
        # achado ao vivo em 22/09/2026: logs gravados em console não-UTF8
        # (cp1252, comum no Windows) corrompem acentos como "�" (replace),
        # não "o"/"ó" - um regex que só previa essas 2 opções não batia.
        m = re.search(r"Total processados.*?:\s*(\d+)", texto)
        total = m.group(1) if m else "vários"
        return f"[OK] concluído - {total} multas no total (histórico completo)"
    achados = _RE_PROGRESSO.findall(texto)
    if achados:
        atual, total, _processados_historico = achados[-1]  # não usado mais aqui - ver comentário abaixo
        atual_i, total_i = int(atual), int(total)
        pct = atual_i * 100 // total_i if total_i else 0
        # ⚠️ Achado ao vivo em 23/09/2026 (durante o teste de login real da
        # GUI): "processados" aqui é o total HISTÓRICO acumulado no
        # checkpoint (soma de TODAS as execuções anteriores desse worker,
        # não só desta) - mostrar isso na linha de andamento ("4189 multas
        # no total...") confundia o usuário, que via um número grande logo
        # nos primeiros % de uma varredura recém-começada.
        # ⚠️ Achado ao vivo em 24/09/2026 (pedido do usuário): mostrar só o
        # % escondia em qual etapa exata o worker estava (ex.: "24/427") -
        # útil pra saber se está travado num ponto específico ou avançando
        # de verdade. Fração explícita acrescentada, mantendo o %.
        # ⚠️ Achado em 24/09/2026 (workers encerrados à força mostravam
        # "100% concluído" com dezenas de falhas pendentes nunca
        # reportadas): "100%" aqui só significa que o LOOP PRINCIPAL passou
        # por todas as combinações - não que terminou sem pendência (as
        # retentativas de paginação/falha de documento, e o relatório final,
        # podem nem ter rodado ainda). Só o ramo "[OK] concluído" acima
        # (que exige a seção VERIFICAÇÃO DE COMPLETUDE já escrita no log)
        # representa conclusão de verdade - este texto não pode parecer
        # igual a esse.
        # ⚠️ Achado ao vivo em 24/09/2026 (pedido do usuário, revendo a GUI
        # depois das mudanças de hoje): o total histórico ("4191 multas no
        # total...") na linha de andamento não ajudava - só o progresso
        # (%/fração) importa enquanto ainda está rodando. O total de verdade
        # (quantas foram verificadas, quantas são novas) passou a aparecer
        # só no resumo final, depois de consolidar (ver executar_robo_gui.py).
        if total_i and atual_i >= total_i:
            return f"passada principal terminou ({atual}/{total}) - conferindo pendências antes de confirmar 100%..."
        return f"{pct}% concluído ({atual}/{total})"

    # ⚠️ Achado ao vivo em 23/09/2026 (mesmo teste): com "[Progresso]" só
    # aparecendo a cada 10 itens, e cada worker cobrindo ~85 itens no
    # total, a pessoa ficava olhando pra "trabalhando... (ainda sem número
    # de progresso disponível)" por vários minutos sem nenhum sinal de que
    # o robô estava fazendo alguma coisa de verdade (mesmo já tendo
    # processado itens reais, alguns com centenas de registros). Usa a
    # última linha "[Item X/Y | ...]" (impressa a cada item, não só a cada
    # 10) como sinal de vida imediato antes do 1º checkpoint de 10.
    achados_item = _RE_ITEM.findall(texto)
    if achados_item:
        atual, total = achados_item[-1]
        atual_i, total_i = int(atual), int(total)
        pct = atual_i * 100 // total_i if total_i else 0
        # mesma ressalva do ramo "[Progresso]" acima: 100% aqui é só o loop
        # principal, não uma conclusão confirmada de verdade.
        if total_i and atual_i >= total_i:
            return f"passada principal terminou ({atual}/{total}) - conferindo pendências antes de confirmar 100%..."
        return f"{pct}% concluído ({atual}/{total}) - trabalhando..."

    return "trabalhando... (ainda sem número de progresso disponível)"


def _acompanhar_progresso(processos: list[subprocess.Popen], intervalo_segundos: int = 60) -> None:
    """Mostra um painel de status simples, atualizado periodicamente, até
    TODOS os workers terminarem - em vez de só esperar em silêncio (ver
    achado na docstring de _status_legivel())."""
    while True:
        _log(f"\n--- Andamento às {time.strftime('%H:%M:%S')} ---")
        for worker_id in range(len(processos)):
            log_path = LOG_DIR / f"worker_{worker_id}.log"
            _log(f"  Worker {worker_id + 1}: {_status_legivel(log_path)}")
        if all(p.poll() is not None for p in processos):
            break
        time.sleep(intervalo_segundos)


def _contar_linhas_planilha(caminho: Path) -> int:
    """Quantas linhas de dado a planilha final tem agora (sem contar o
    cabeçalho) - 0 se o arquivo ainda não existir (1ª execução de sempre).
    Usado pra reportar, no resumo final, quantas multas são novas nesta
    execução (diferença entre a contagem antes e depois de consolidar -
    ver executar_robo_gui.py, pedido do usuário em 24/09/2026)."""
    if not caminho.exists():
        return 0
    from openpyxl import load_workbook

    wb = load_workbook(str(caminho), read_only=True)
    try:
        return max(wb.active.max_row - 1, 0)
    finally:
        wb.close()


def _consolidar_planilha_final() -> None:
    _log("\nJuntando os resultados de todos os workers na planilha final...")
    resultado = subprocess.run(
        [sys.executable, str(BASE_DIR / "scripts" / "consolidar_planilhas.py")],
        cwd=str(BASE_DIR),
        env={**os.environ, "PYTHONPATH": str(BASE_DIR / "src")},
        capture_output=True,
        text=True,
    )
    _log(resultado.stdout)
    if resultado.returncode != 0:
        _log("[ATENÇÃO] A consolidação da planilha final teve um problema:")
        _log(resultado.stderr)


def main() -> None:
    _log("=" * 70)
    _log("ROBÔ ANTT - Varredura completa de autos de infração")
    _log("=" * 70)
    _log(
        "\nEssa é a execução PADRÃO: sempre varre a empresa inteira, sempre "
        "salva tudo automaticamente. Pode fechar a janela do navegador "
        "depois de cada login - o trabalho continua sozinho."
    )

    total_workers = _ler_quantidade_workers()

    processos: list[subprocess.Popen] = []
    for worker_id in range(total_workers):
        _log(f"\n--- Login {worker_id + 1} de {total_workers} ---")
        _login_worker(worker_id)
        processos.append(_iniciar_worker(worker_id, total_workers))

    _log(
        f"\nTodos os {total_workers} login(s) feitos - os workers estão trabalhando em segundo plano.\n"
        "Isso pode levar horas dependendo do volume de multas novas - pode deixar "
        "rodando e voltar de vez em quando pra conferir (o andamento abaixo "
        f"atualiza sozinho a cada {60} segundos)."
    )
    _acompanhar_progresso(processos)

    _consolidar_planilha_final()

    _log("\n" + "=" * 70)
    _log("CONCLUÍDO")
    _log("=" * 70)
    _log(f"Planilha final: {config.PLANILHA_PATH}")
    _log(
        "\nSe algum worker parou antes de terminar (sessão expirada, internet "
        "caiu, etc.), é só rodar este mesmo programa de novo - ele continua "
        "de onde parou, sem perder nada nem repetir trabalho já feito."
    )
    _log(
        "Pra saber se a varredura da empresa toda já está 100% completa, "
        "peça pra rodar scripts/relatorio_completude.py."
    )


if __name__ == "__main__":
    main()

