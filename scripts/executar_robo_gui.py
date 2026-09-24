"""
IHM gráfica (Tkinter) do robô ANTT - pedido do usuário em 22/09/2026,
retomado em 23/09/2026 (ver CLAUDE.md): substitui o terminal rolando texto
(scripts/executar_robo.py) por uma janela de verdade, com campo pra
escolher workers, botão "Iniciar", um botão "Já fiz login" no lugar do
"aperte ENTER", e uma barra de progresso por worker.

Reaproveita TODA a lógica de scripts/executar_robo.py sem duplicar nada
(_iniciar_worker, _status_legivel, _consolidar_planilha_final, LOG_DIR,
PORTAL_LOGIN_URL, config) - só troca a CAMADA DE INTERAÇÃO: onde a versão
terminal bloqueia com `input()`, esta versão bloqueia numa
`threading.Event` que o clique do botão "Já fiz login" libera.

⚠️ Design (análise de custo feita em 21/09/2026, retomada hoje): Tkinter
trava se tudo rodar na mesma thread - login (navegador Playwright) e
acompanhamento de progresso (polling de arquivos de log) rodam numa
thread de fundo separada (`_orquestrar`), que nunca toca em nenhum widget
diretamente. Toda comunicação de volta pra tela usa uma `queue.Queue` -
a thread de fundo só posta mensagens nela; só a thread principal (dentro
do loop do Tkinter, via `after()`) lê a fila e atualiza a tela. Esse é o
jeito seguro de fazer isso em Tkinter (nunca mexer em widget de outra
thread diretamente).

USO:
    python scripts/executar_robo_gui.py
"""
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from executar_robo import (  # noqa: E402
    LOG_DIR,
    PORTAL_LOGIN_URL,
    _consolidar_planilha_final,
    _iniciar_worker,
    _status_legivel,
    config,
)
from relatorio_completude import calcular_completude  # noqa: E402

_RE_PERCENTUAL = re.compile(r"^(\d+)% conclu")


def _resumo_completude_legivel(resultado: dict) -> str:
    """Traduz o dict de calcular_completude() (ver relatorio_completude.py)
    pra 1-2 frases em português comum, sem termos técnicos - achado ao
    vivo em 23/09/2026 (ver CLAUDE.md): a tela de conclusão dizia "peça
    pra rodar scripts/relatorio_completude.py", pedindo pra pessoa
    NÃO-técnica que usa essa tela recorrer a alguém que sabe rodar script -
    contradiz o motivo dessa IHM existir. Agora a checagem roda sozinha,
    automaticamente, e o resultado já aparece aqui em português."""
    if "erro" in resultado:
        return (
            "Não foi possível confirmar se a varredura está 100% completa agora "
            "(ex.: portal em manutenção ou sessão expirada) - rode este programa de "
            "novo mais tarde pra conferir."
        )
    if resultado["cem_por_cento"]:
        return "Confirmado: a varredura da empresa inteira está 100% completa - nenhuma multa real ficou de fora."

    partes = []
    if not resultado["paginacao_completa"]:
        n = sum(len(v) for v in resultado["faltando_por_cnpj"].values())
        partes.append(f"ainda falta verificar {n} combinação(ões) de CNPJ/tipo de multa")
    if resultado["total_falhas"]:
        partes.append(f"{resultado['total_falhas']} documento(s) específico(s) ainda não baixaram com sucesso")
    # ⚠️ Achado na revisão crítica de 24/09/2026: se "cem_por_cento" for
    # False só por causa de checkpoint(s) corrompido(s) (paginação completa
    # e zero falhas, mas 1+ checkpoint ilegível), as 2 checagens acima não
    # disparavam - "detalhe" ficava vazio, gerando a frase quebrada "Ainda
    # não está 100% completo: . É só rodar...". Corrigido com essa 3ª causa
    # possível, sempre que checkpoints_corrompidos existir.
    if resultado.get("checkpoints_corrompidos"):
        n = len(resultado["checkpoints_corrompidos"])
        partes.append(f"{n} arquivo(s) de progresso interno ficaram ilegíveis e precisam de atenção técnica")
    detalhe = " e ".join(partes) if partes else "não foi possível confirmar todos os detalhes"
    return f"Ainda não está 100% completo: {detalhe}. É só rodar este programa de novo que ele tenta terminar sozinho."


def _percentual_de(status_texto: str) -> int:
    """Extrai o número de "43% concluído - ..." pra virar valor de
    Progressbar - 100 se já terminou ("[OK]"), 0 se ainda não tem número."""
    if status_texto.startswith("[OK]"):
        return 100
    m = _RE_PERCENTUAL.match(status_texto)
    return int(m.group(1)) if m else 0


class AppRobo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Robô ANTT - Varredura de Autos de Infração")
        self.geometry("700x480")
        self.minsize(560, 400)
        self.resizable(True, True)

        self._fila: queue.Queue = queue.Queue()
        self._evento_login: threading.Event | None = None
        self._linhas_worker: dict[int, dict] = {}
        self._processos: list[subprocess.Popen] = []

        self._montar_tela_inicial()
        self.after(150, self._processar_fila)

    # ------------------------------------------------------------------
    # Tela inicial: só pergunta quantos workers
    # ------------------------------------------------------------------
    def _montar_tela_inicial(self) -> None:
        self._frame_inicial = tk.Frame(self, padx=20, pady=20)
        self._frame_inicial.pack(fill="both", expand=True)

        tk.Label(
            self._frame_inicial,
            text="Robô ANTT - Varredura completa de autos de infração",
            font=("Segoe UI", 12, "bold"),
            wraplength=500,
            justify="left",
        ).pack(anchor="w")

        tk.Label(
            self._frame_inicial,
            text=(
                "Essa é a execução padrão: sempre varre a empresa inteira, sempre "
                "salva tudo automaticamente. Você pode fechar a janela do navegador "
                "depois de cada login - o trabalho continua sozinho."
            ),
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(10, 20))

        linha = tk.Frame(self._frame_inicial)
        linha.pack(anchor="w")
        tk.Label(linha, text="Quantos 'trabalhadores' (workers) usar? ").pack(side="left")
        self._campo_workers = tk.Spinbox(linha, from_=1, to=15, width=5)
        self._campo_workers.delete(0, "end")
        self._campo_workers.insert(0, "5")
        self._campo_workers.pack(side="left")

        tk.Label(
            self._frame_inicial,
            text="(recomendado: 5 - mais rápido, mas exige um login por worker)",
            fg="gray30",
        ).pack(anchor="w", pady=(2, 20))

        self._botao_iniciar = tk.Button(
            self._frame_inicial, text="Iniciar", font=("Segoe UI", 10, "bold"), command=self._ao_clicar_iniciar
        )
        self._botao_iniciar.pack(anchor="w")

    def _ao_clicar_iniciar(self) -> None:
        try:
            total_workers = int(self._campo_workers.get())
            if total_workers < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Robô ANTT", "Digite um número inteiro de 1 ou mais.")
            return

        self._frame_inicial.destroy()
        self._montar_tela_execucao(total_workers)

        thread = threading.Thread(target=self._orquestrar, args=(total_workers,), daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Tela de execução: 1 linha por worker (status + barra de progresso)
    # + botão único "Já fiz login" (logins acontecem 1 de cada vez)
    # ------------------------------------------------------------------
    def _montar_tela_execucao(self, total_workers: int) -> None:
        self._frame_exec = tk.Frame(self, padx=20, pady=20)
        self._frame_exec.pack(fill="both", expand=True)

        self._label_status_geral = tk.Label(
            self._frame_exec, text="Preparando...", font=("Segoe UI", 10, "bold"), wraplength=500, justify="left"
        )
        self._label_status_geral.pack(anchor="w", pady=(0, 10))

        self._botao_login = tk.Button(
            self._frame_exec,
            text="Já fiz login - continuar",
            font=("Segoe UI", 10, "bold"),
            state="disabled",
            command=self._ao_clicar_ja_fiz_login,
        )
        self._botao_login.pack(anchor="w", pady=(0, 15))

        area_workers = tk.Frame(self._frame_exec)
        area_workers.pack(fill="both", expand=True)
        for worker_id in range(total_workers):
            linha = tk.Frame(area_workers)
            linha.pack(fill="x", pady=3)
            # ⚠️ Achado ao vivo em 23/09/2026 (ver CLAUDE.md): com a janela em
            # tamanho fixo e o rótulo com largura fixa em caracteres, texto
            # mais longo (ex.: "94% concluído - 680 multas no total
            # (histórico, inclui execuções anteriores)") ficava cortado sem
            # aviso nenhum - a pessoa não conseguia nem redimensionar a
            # janela pra ver o resto. Corrigido: janela agora é redimension
            # ável (ver __init__), a barra de progresso fica fixa à direita
            # (empacotada primeiro, com side="right"), e o rótulo ocupa todo
            # o espaço restante (`fill="x", expand=True`) - se ainda não
            # couber, quebra em 2+ linhas (`wraplength`) em vez de cortar.
            barra = ttk.Progressbar(linha, length=150, maximum=100)
            barra.pack(side="right", padx=(10, 0))
            label = tk.Label(linha, text=f"Worker {worker_id + 1}: aguardando...", anchor="w", justify="left", wraplength=450)
            label.pack(side="left", fill="x", expand=True)
            self._linhas_worker[worker_id] = {"label": label, "barra": barra}

        self._label_resultado_final = tk.Label(
            self._frame_exec, text="", wraplength=500, justify="left", fg="darkgreen"
        )
        self._label_resultado_final.pack(anchor="w", pady=(15, 0))

    def _ao_clicar_ja_fiz_login(self) -> None:
        if self._evento_login is not None:
            self._botao_login.config(state="disabled")
            self._evento_login.set()

    # ------------------------------------------------------------------
    # Thread de fundo - nunca toca em widget diretamente, só posta na fila
    # ------------------------------------------------------------------
    def _orquestrar(self, total_workers: int) -> None:
        try:
            for worker_id in range(total_workers):
                self._fila.put(("status_geral", f"Login {worker_id + 1} de {total_workers} - abrindo o portal..."))
                self._login_worker_gui(worker_id)
                self._fila.put(("worker_status", worker_id, "login feito - iniciando em segundo plano..."))
                processo = _iniciar_worker(worker_id, total_workers)
                self._processos.append(processo)

            self._fila.put(
                (
                    "status_geral",
                    f"Todos os {total_workers} login(s) feitos - os workers estão trabalhando em segundo plano. "
                    "Isso pode levar horas dependendo do volume de multas novas.",
                )
            )

            while True:
                for worker_id in range(total_workers):
                    log_path = LOG_DIR / f"worker_{worker_id}.log"
                    status = _status_legivel(log_path)
                    self._fila.put(("worker_status", worker_id, status))
                if all(p.poll() is not None for p in self._processos):
                    break
                time.sleep(5)

            self._fila.put(("status_geral", "Juntando os resultados de todos os workers na planilha final..."))
            _consolidar_planilha_final()

            self._fila.put(("status_geral", "Verificando se a varredura da empresa inteira já está 100% completa..."))
            try:
                resultado_completude = calcular_completude()
            except FileNotFoundError:
                # não deveria acontecer (acabamos de logar pelo menos 1 worker),
                # mas por segurança trata como "não deu pra verificar agora".
                resultado_completude = {"erro": "nenhuma sessão disponível"}
            resumo_completude = _resumo_completude_legivel(resultado_completude)

            self._fila.put(("concluido", str(config.PLANILHA_PATH), resumo_completude))
        except Exception as e:  # nunca deixa a thread de fundo morrer em silêncio
            self._fila.put(("erro", str(e)))

    def _login_worker_gui(self, worker_id: int) -> None:
        """Mesma mecânica de executar_robo._login_worker(), trocando o
        `input()` bloqueante por um `threading.Event` que o botão "Já fiz
        login" da tela libera."""
        arquivo_sessao = config.sessao_worker(worker_id)
        evento = threading.Event()
        self._evento_login = evento

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(PORTAL_LOGIN_URL)

            self._fila.put(("aguardando_login", worker_id))
            evento.wait()

            context.storage_state(path=arquivo_sessao)
            browser.close()
        self._evento_login = None

    # ------------------------------------------------------------------
    # Thread principal - único lugar que mexe em widgets
    # ------------------------------------------------------------------
    def _processar_fila(self) -> None:
        try:
            while True:
                mensagem = self._fila.get_nowait()
                self._tratar_mensagem(mensagem)
        except queue.Empty:
            pass
        self.after(150, self._processar_fila)

    def _tratar_mensagem(self, mensagem: tuple) -> None:
        tipo = mensagem[0]
        if tipo == "status_geral":
            self._label_status_geral.config(text=mensagem[1])
        elif tipo == "aguardando_login":
            worker_id = mensagem[1]
            self._label_status_geral.config(
                text=f"Faça o login manualmente (CPF/senha + verificação de segurança) "
                f"na janela do navegador que abriu (Worker {worker_id + 1})."
            )
            self._botao_login.config(state="normal")
        elif tipo == "worker_status":
            worker_id, status = mensagem[1], mensagem[2]
            linha = self._linhas_worker[worker_id]
            linha["label"].config(text=f"Worker {worker_id + 1}: {status}")
            linha["barra"]["value"] = _percentual_de(status)
        elif tipo == "concluido":
            caminho_planilha, resumo_completude = mensagem[1], mensagem[2]
            self._label_status_geral.config(text="CONCLUÍDO")
            self._label_resultado_final.config(
                text=(
                    f"Planilha final: {caminho_planilha}\n\n"
                    f"{resumo_completude}\n\n"
                    "Se algum worker parou antes de terminar (sessão expirada, internet caiu, etc.), "
                    "é só rodar este programa de novo - ele continua de onde parou, sem perder nada."
                )
            )
        elif tipo == "erro":
            self._label_status_geral.config(text=f"[ATENÇÃO] Ocorreu um erro: {mensagem[1]}", fg="red")


def main() -> None:
    app = AppRobo()
    app.mainloop()


if __name__ == "__main__":
    main()
