"""
Testes da IHM gráfica (scripts/executar_robo_gui.py, 23/09/2026) - só a
parte que dá pra testar sem navegador/portal: construção da janela,
parsing de percentual de progresso, e o tratamento de mensagens vindas
da thread de fundo (simuladas aqui, sem precisar da thread de verdade).
Login/varredura reais continuam precisando de validação manual ao vivo.

⚠️ A janela Tk() é criada UMA VEZ só, reaproveitada por todos os testes
deste módulo (`scope="module"`) - achado ao vivo: criar/destruir várias
`Tk()` em sequência no mesmo processo deixa o Tcl instável (um dos
testes começou a falhar com um erro de "init.tcl não encontrado" vindo
de uma instalação de Python completamente diferente) - limitação
conhecida do Tkinter, não um bug do código. `_resetar()` limpa e
reconstrói só o CONTEÚDO da janela entre testes, sem recriar o Tk() raiz.
"""
import queue
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import executar_robo_gui  # noqa: E402
from executar_robo_gui import AppRobo, _pasta_e_gravavel, _percentual_de, _resumo_completude_legivel  # noqa: E402
from robo_antt import config  # noqa: E402


@pytest.fixture(scope="module")
def app():
    janela = AppRobo()
    janela.update()
    yield janela
    janela.destroy()


def _resetar(app, total_workers: int | None = None):
    """Limpa a tela atual e reconstrói do zero - tela inicial se
    `total_workers` for None, tela de execução (com N linhas de worker)
    caso contrário. Não recria o Tk() raiz (ver docstring do módulo)."""
    if hasattr(app, "_frame_inicial") and app._frame_inicial.winfo_exists():
        app._frame_inicial.destroy()
    if hasattr(app, "_frame_exec") and app._frame_exec.winfo_exists():
        app._frame_exec.destroy()
    app._linhas_worker = {}
    # Estado de reconexão por worker (25/09/2026) também precisa resetar -
    # senão um teste que marca _execucao_concluida/_workers_parados
    # "vaza" pro próximo teste, já que `app` é reaproveitado (scope="module").
    app._reconectando = False
    app._execucao_concluida = False
    app._workers_parados = set()
    app._processos = {}
    # Cancelamento (29/09/2026) também precisa de um Event novo a cada
    # teste - reaproveitar o mesmo objeto "vazaria" um cancelamento já
    # setado de um teste anterior pro próximo.
    app._cancelado = threading.Event()

    if total_workers is None:
        app._montar_tela_inicial()
    else:
        app._montar_tela_execucao(total_workers)
    app.update()


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("43% concluído - 120 multas encontradas até agora", 43),
        ("[OK] concluído - 500 multas no total (histórico completo)", 100),
        ("iniciando...", 0),
        ("[PAROU] parou antes de terminar...", 0),
        ("trabalhando... (ainda sem número de progresso disponível)", 0),
    ],
)
def test_percentual_de(texto, esperado):
    assert _percentual_de(texto) == esperado


def test_janela_inicial_tem_campo_de_workers_com_default_5(app):
    _resetar(app)
    assert app._campo_workers.get() == "5"


def test_iniciar_com_menos_que_o_minimo_de_workers_mostra_erro_e_nao_avanca(app, monkeypatch):
    """Achado em reunião com o time, 25/09/2026: menos de 5 workers ficava
    lento demais na prática - virou um mínimo obrigatório, não mais só
    uma sugestão."""
    _resetar(app)
    app._campo_workers.delete(0, "end")
    app._campo_workers.insert(0, "3")

    mostrou_erro = []
    monkeypatch.setattr(
        executar_robo_gui.messagebox, "showerror", lambda *a, **k: mostrou_erro.append(a)
    )

    app._ao_clicar_iniciar()

    assert mostrou_erro
    assert "5" in mostrou_erro[0][1]
    assert app._frame_inicial.winfo_exists()  # não avançou pra tela de execução


def test_tela_execucao_cria_1_linha_por_worker(app):
    _resetar(app, total_workers=3)
    assert len(app._linhas_worker) == 3


def test_mensagem_aguardando_login_habilita_botao(app):
    _resetar(app, total_workers=1)

    assert app._botao_login["state"] == "disabled"
    app._tratar_mensagem(("aguardando_login", 0))
    app.update()
    assert app._botao_login["state"] == "normal"


def test_mensagem_worker_status_atualiza_label_e_barra(app):
    _resetar(app, total_workers=2)

    app._tratar_mensagem(("worker_status", 0, "43% concluído - 10 multas encontradas até agora"))
    app._tratar_mensagem(("worker_status", 1, "[OK] concluído - 5 multas no total (histórico completo)"))
    app.update()

    assert "43% conclu" in app._linhas_worker[0]["label"]["text"]
    assert app._linhas_worker[0]["barra"]["value"] == 43
    assert app._linhas_worker[1]["barra"]["value"] == 100


def test_mensagem_concluido_mostra_resumo_final(app):
    _resetar(app, total_workers=1)

    app._tratar_mensagem(("concluido", "C:/fake/Relatorio_Multas.xlsx", "Confirmado: 100% completo.", 4191, 7))
    app.update()

    assert "CONCLU" in app._label_status_geral["text"]
    assert "Relatorio_Multas.xlsx" in app._label_resultado_final["text"]
    assert "Confirmado: 100% completo." in app._label_resultado_final["text"]
    # achado/pedido em 24/09/2026: resumo final precisa dizer quantas multas
    # foram verificadas no total e quantas são novas desta execução.
    assert "4191" in app._label_resultado_final["text"]
    assert "7 nova" in app._label_resultado_final["text"]


# ---------------------------------------------------------------------------
# _resumo_completude_legivel() - achado ao vivo em 23/09/2026 (ver CLAUDE.md):
# a tela antiga mandava a pessoa NÃO-técnica "pedir pra alguém rodar um
# script" - contradiz o motivo da IHM existir. Agora a checagem roda
# sozinha e o resultado sai em português direto na tela.
# ---------------------------------------------------------------------------


def test_resumo_completude_erro_nao_menciona_rodar_script():
    resumo = _resumo_completude_legivel({"erro": "sessão expirada"})
    assert "script" not in resumo.lower()
    assert "rode este programa de novo" in resumo


def test_resumo_completude_100_por_cento():
    resultado = {"cem_por_cento": True}
    resumo = _resumo_completude_legivel(resultado)
    assert "100% completa" in resumo


def test_resumo_completude_faltando_paginacao_e_falhas():
    resultado = {
        "cem_por_cento": False,
        "paginacao_completa": False,
        "faltando_por_cnpj": {"92.660.604/0001-82": ["Cargas", "Excesso de Peso"]},
        "total_falhas": 5,
    }
    resumo = _resumo_completude_legivel(resultado)
    assert "2 combinação" in resumo
    assert "5 documento" in resumo
    assert "script" not in resumo.lower()


def test_resumo_completude_so_falhas_permanentes_nao_promete_rodar_de_novo():
    """Achado na revisão crítica de 25/09/2026: se a única pendência for
    falha(s) já confirmada(s) como problema permanente do servidor, a
    mensagem não pode sugerir que rodar de novo vai chegar a 100% - isso
    pode nunca acontecer pra essas."""
    resultado = {
        "cem_por_cento": False,
        "paginacao_completa": True,
        "faltando_por_cnpj": {},
        "total_falhas": 176,
        "falhas_novas": 0,
        "falhas_permanentes": 176,
    }
    resumo = _resumo_completude_legivel(resultado)
    assert "não precisa rodar de novo" in resumo
    assert "176" in resumo
    assert "É só rodar este programa de novo que ele tenta terminar" not in resumo


def test_resumo_completude_falhas_mistas_ainda_sugere_rodar_de_novo():
    """Se sobrar pelo menos 1 falha nova (não confirmada permanente ainda),
    a sugestão de rodar de novo continua fazendo sentido - só não pra
    100% completo (as permanentes continuam lá)."""
    resultado = {
        "cem_por_cento": False,
        "paginacao_completa": True,
        "faltando_por_cnpj": {},
        "total_falhas": 180,
        "falhas_novas": 4,
        "falhas_permanentes": 176,
    }
    resumo = _resumo_completude_legivel(resultado)
    assert "É só rodar este programa de novo que ele tenta terminar" in resumo
    assert "4 documento" in resumo
    assert "176 documento" in resumo


def test_resumo_completude_so_checkpoint_corrompido_nao_gera_frase_quebrada():
    """Achado na revisão crítica de 24/09/2026: com paginação completa e 0
    falhas, mas 1+ checkpoint corrompido, "cem_por_cento" é False sem que
    nenhuma das 2 checagens antigas dispare - sem o fix, a frase saía
    "Ainda não está 100% completo: . É só rodar..." (detalhe vazio)."""
    resultado = {
        "cem_por_cento": False,
        "paginacao_completa": True,
        "faltando_por_cnpj": {},
        "total_falhas": 0,
        "checkpoints_corrompidos": ["checkpoint_worker_7.json"],
    }
    resumo = _resumo_completude_legivel(resultado)
    assert ": ." not in resumo
    assert "1 arquivo" in resumo


def test_clicar_ja_fiz_login_libera_evento_e_desabilita_botao(app):
    _resetar(app, total_workers=1)

    app._evento_login = threading.Event()
    app._botao_login.config(state="normal")
    app._ao_clicar_ja_fiz_login()

    assert app._evento_login.is_set()
    assert app._botao_login["state"] == "disabled"


def test_mensagem_erro_nao_derruba_a_tela(app):
    """A thread de fundo posta ("erro", msg) em vez de deixar uma exceção
    matar o processo em silêncio - garante que _tratar_mensagem lida com
    isso sem levantar exceção própria."""
    _resetar(app, total_workers=1)

    app._tratar_mensagem(("erro", "falha simulada"))
    app.update()
    assert "falha simulada" in app._label_status_geral["text"]


# ---------------------------------------------------------------------------
# Reconexão por worker (25/09/2026, pedido em reunião com o time) - ver
# docstring do módulo. Não abre navegador/Playwright de verdade nos testes -
# _ao_clicar_relogar monkeypatcha threading.Thread pra capturar o alvo em
# vez de rodá-lo (o próprio _reconectar_worker também não é exercido aqui
# com login real - ele só chama funções já usadas/testadas em outro lugar).
# ---------------------------------------------------------------------------


def test_botao_relogar_comeca_desabilitado(app):
    _resetar(app, total_workers=2)
    assert app._linhas_worker[0]["botao_relogar"]["state"] == "disabled"


def test_mensagem_worker_parou_habilita_so_o_botao_daquele_worker(app):
    _resetar(app, total_workers=2)

    app._tratar_mensagem(("worker_parou", 0))
    app.update()

    assert app._linhas_worker[0]["botao_relogar"]["state"] == "normal"
    assert app._linhas_worker[1]["botao_relogar"]["state"] == "disabled"
    assert 0 in app._workers_parados


def test_mensagem_worker_parou_nao_habilita_se_ja_concluido(app):
    """Depois de "concluído", ninguém mais está fazendo polling - habilitar
    o botão seria enganoso (clicar não teria efeito real)."""
    _resetar(app, total_workers=1)
    app._execucao_concluida = True

    app._tratar_mensagem(("worker_parou", 0))
    app.update()

    assert app._linhas_worker[0]["botao_relogar"]["state"] == "disabled"


def test_ao_clicar_relogar_desabilita_todos_os_botoes_e_dispara_thread(app, monkeypatch):
    """Serializa reconexões (1 login manual por vez, reaproveitando o
    mesmo botão/evento "Já fiz login" já usado no login inicial)."""
    _resetar(app, total_workers=2)
    app._tratar_mensagem(("worker_parou", 0))
    app.update()

    threads_criadas = []

    class ThreadFalsa:
        def __init__(self, target, args, daemon):
            threads_criadas.append((target, args))

        def start(self):
            pass  # não roda de verdade - testado à parte via _reconectar_worker

    monkeypatch.setattr(executar_robo_gui.threading, "Thread", ThreadFalsa)

    app._ao_clicar_relogar(0, total_workers=2)
    app.update()

    assert app._reconectando is True
    assert app._linhas_worker[0]["botao_relogar"]["state"] == "disabled"
    assert app._linhas_worker[1]["botao_relogar"]["state"] == "disabled"
    assert len(threads_criadas) == 1
    assert threads_criadas[0][0] == app._reconectar_worker
    assert threads_criadas[0][1] == (0, 2)


def test_ao_clicar_relogar_nao_faz_nada_se_ja_reconectando(app, monkeypatch):
    _resetar(app, total_workers=2)
    app._tratar_mensagem(("worker_parou", 0))
    app._reconectando = True
    app.update()

    chamou_thread = []
    monkeypatch.setattr(
        executar_robo_gui.threading,
        "Thread",
        lambda *a, **k: chamou_thread.append(True),
    )

    app._ao_clicar_relogar(0, total_workers=2)

    assert not chamou_thread


def test_ao_clicar_relogar_apos_concluido_mostra_aviso_sem_disparar_thread(app, monkeypatch):
    _resetar(app, total_workers=1)
    app._execucao_concluida = True

    avisos = []
    monkeypatch.setattr(executar_robo_gui.messagebox, "showinfo", lambda *a, **k: avisos.append(a))
    chamou_thread = []
    monkeypatch.setattr(
        executar_robo_gui.threading,
        "Thread",
        lambda *a, **k: chamou_thread.append(True),
    )

    app._ao_clicar_relogar(0, total_workers=1)

    assert avisos
    assert not chamou_thread


def test_mensagem_reconexao_finalizada_com_sucesso_libera_flag_e_reabilita_pendentes(app):
    """2 workers pararam; reconecta o worker 0 COM SUCESSO - ao terminar,
    o botão do worker 0 fica sem uso (removido de _workers_parados) e o
    do worker 1 (que continuava parado) volta a ficar disponível."""
    _resetar(app, total_workers=2)
    app._tratar_mensagem(("worker_parou", 0))
    app._tratar_mensagem(("worker_parou", 1))
    app._reconectando = True
    for linha in app._linhas_worker.values():
        linha["botao_relogar"].config(state="disabled")
    app.update()

    app._tratar_mensagem(("reconexao_finalizada", 0, True))
    app.update()

    assert app._reconectando is False
    assert 0 not in app._workers_parados
    assert app._linhas_worker[1]["botao_relogar"]["state"] == "normal"


def test_mensagem_reconexao_finalizada_sem_sucesso_mantem_botao_disponivel(app):
    """Achado ao vivo em 29/09/2026: se a reconexão falhar de novo (login
    falhou outra vez), o worker precisa CONTINUAR em _workers_parados e
    com o botão disponível - senão ficaria preso desabilitado pra sempre,
    sem nenhum jeito de tentar de novo pela tela."""
    _resetar(app, total_workers=1)
    app._tratar_mensagem(("worker_parou", 0))
    app._reconectando = True
    app._linhas_worker[0]["botao_relogar"].config(state="disabled")
    app.update()

    app._tratar_mensagem(("reconexao_finalizada", 0, False))
    app.update()

    assert app._reconectando is False
    assert 0 in app._workers_parados
    assert app._linhas_worker[0]["botao_relogar"]["state"] == "normal"


def test_mensagem_reconexao_erro_mostra_aviso_sem_travar(app):
    _resetar(app, total_workers=1)

    app._tratar_mensagem(("reconexao_erro", 0, "falha simulada de login"))
    app.update()

    assert "Worker 1" in app._label_status_geral["text"]
    assert "falha simulada de login" in app._label_status_geral["text"]


# ---------------------------------------------------------------------------
# _fazer_login_e_lancar() - achado ao vivo em 29/09/2026: um erro do
# Playwright durante o LOGIN de 1 worker (ex.: "BrowserContext.storage_state:
# Connection closed while reading from the driver") derrubava a thread
# inteira de _orquestrar() - mesmo com outros workers já rodando com
# sucesso, a tela travava sem mais nenhum acompanhamento. Testado sem
# navegador real (monkeypatch em _login_worker_gui/_iniciar_worker).
# ---------------------------------------------------------------------------


def test_fazer_login_e_lancar_sucesso(app, monkeypatch):
    _resetar(app, total_workers=1)
    monkeypatch.setattr(app, "_login_worker_gui", lambda wid: None)
    processo_falso = object()
    monkeypatch.setattr(executar_robo_gui, "_iniciar_worker", lambda wid, total: processo_falso)

    resultado = app._fazer_login_e_lancar(0, total_workers=1)
    _drenar_fila(app)

    assert resultado is True
    assert app._processos[0] is processo_falso
    assert "login feito" in app._linhas_worker[0]["label"]["text"]


def test_fazer_login_e_lancar_falha_no_login_nao_propaga_excecao(app, monkeypatch):
    """O caso real do erro ao vivo: _login_worker_gui() levanta uma
    exceção do Playwright - devolve False (não propaga), marca o worker
    como [PAROU] e habilita o botão "Relogar", em vez de derrubar quem
    chamou (o laço de login inicial em _orquestrar, ou a reconexão)."""
    _resetar(app, total_workers=1)

    def _login_que_falha(wid):
        raise Exception("BrowserContext.storage_state: Connection closed while reading from the driver")

    monkeypatch.setattr(app, "_login_worker_gui", _login_que_falha)

    resultado = app._fazer_login_e_lancar(0, total_workers=1)
    _drenar_fila(app)

    assert resultado is False
    assert 0 not in app._processos
    assert "[PAROU]" in app._linhas_worker[0]["label"]["text"]
    assert app._linhas_worker[0]["botao_relogar"]["state"] == "normal"


def _drenar_fila(app):
    while True:
        try:
            app._tratar_mensagem(app._fila.get_nowait())
        except queue.Empty:
            break
    app.update()


def test_orquestrar_nao_trava_tudo_se_1_login_falhar_no_meio_do_laco(app, monkeypatch):
    """Reprodução direta do erro real relatado ao vivo em 29/09/2026: o
    usuário logou os 5 workers, e o login de 1 deles quebrou com
    "BrowserContext.storage_state: Connection closed while reading from
    the driver" (provável fechamento do navegador antes da hora) - a
    tela travou mostrando só esse erro, sem mais acompanhamento dos
    outros workers (que já tinham logado/lançado com sucesso). Este
    teste chama _orquestrar() diretamente (sem thread própria - já é
    síncrono o bastante pra um teste) com o login do worker 2 quebrando
    de propósito, e confirma que os workers 0/1 continuam sendo
    acompanhados até o fim (não travados no "erro" geral)."""
    _resetar(app, total_workers=3)

    class _ProcessoFalso:
        def poll(self):
            return 0  # já "terminou" - some da fila de polling na hora

    def _login_fake(wid):
        if wid == 2:
            raise Exception("BrowserContext.storage_state: Connection closed while reading from the driver")

    monkeypatch.setattr(app, "_login_worker_gui", _login_fake)
    monkeypatch.setattr(executar_robo_gui, "_iniciar_worker", lambda wid, total: _ProcessoFalso())
    monkeypatch.setattr(executar_robo_gui, "_status_legivel", lambda log_path: "[OK] concluído")
    monkeypatch.setattr(executar_robo_gui, "_contar_linhas_planilha", lambda caminho: 10)
    monkeypatch.setattr(executar_robo_gui, "_consolidar_planilha_final", lambda: None)
    monkeypatch.setattr(executar_robo_gui, "calcular_completude", lambda: {"cem_por_cento": True})
    monkeypatch.setattr(executar_robo_gui.time, "sleep", lambda segundos: None)

    app._orquestrar(3)
    _drenar_fila(app)

    assert app._processos.get(0) is not None
    assert app._processos.get(1) is not None
    assert 2 not in app._processos
    assert "[PAROU]" in app._linhas_worker[2]["label"]["text"]
    # Neste cenário os workers 0/1 "terminam" na hora (poll() falso) e a
    # execução chega a "concluído" de verdade - nesse ponto o botão
    # "Relogar" fica desabilitado por design (ninguém mais monitora pra
    # pegar um relançamento, ver mensagem "concluido"/_execucao_concluida)
    # - não é um bug, é o mesmo comportamento já coberto por
    # test_mensagem_concluido_desabilita_botoes_relogar_restantes.
    assert app._linhas_worker[2]["botao_relogar"]["state"] == "disabled"
    # terminou de verdade (consolidou/concluiu) - não ficou preso no "erro"
    assert app._execucao_concluida is True
    assert "CONCLU" in app._label_status_geral["text"]


def test_mensagem_concluido_desabilita_botoes_relogar_restantes(app):
    _resetar(app, total_workers=2)
    app._tratar_mensagem(("worker_parou", 0))
    app.update()
    assert app._linhas_worker[0]["botao_relogar"]["state"] == "normal"

    app._tratar_mensagem(("concluido", "C:/fake/Relatorio_Multas.xlsx", "Confirmado: 100% completo.", 10, 1))
    app.update()

    assert app._execucao_concluida is True
    assert app._linhas_worker[0]["botao_relogar"]["state"] == "disabled"


# ---------------------------------------------------------------------------
# Pasta de destino configurável (25/09/2026, ver CLAUDE.md e config.py) -
# tela nova que aparece só quando config.SHAREPOINT_DIR não existe nesta
# máquina, perguntando onde salvar antes de seguir pra tela normal.
# ---------------------------------------------------------------------------


def _resetar_para_escolher_pasta(app):
    for nome in ("_frame_inicial", "_frame_exec", "_frame_pasta"):
        frame = getattr(app, nome, None)
        if frame is not None and frame.winfo_exists():
            frame.destroy()
    app._montar_tela_escolher_pasta()
    app.update()


def test_pasta_e_gravavel_aceita_pasta_valida(tmp_path):
    assert _pasta_e_gravavel(tmp_path / "subpasta_nova")


def test_pasta_e_gravavel_rejeita_quando_nao_consegue_escrever(tmp_path, monkeypatch):
    """Simula uma falha de gravação (ex.: sem permissão) sem depender de
    ACLs reais do SO, que variam de máquina pra máquina."""

    def _write_text_que_falha(self, *args, **kwargs):
        raise OSError("simulado: sem permissão")

    monkeypatch.setattr(Path, "write_text", _write_text_que_falha)
    assert not _pasta_e_gravavel(tmp_path / "sem_permissao")


def test_tela_escolher_pasta_mostra_o_botao(app):
    _resetar_para_escolher_pasta(app)
    assert app._frame_pasta.winfo_exists()


def test_ao_clicar_escolher_pasta_cancelado_nao_salva_nem_reinicia(app, monkeypatch):
    """filedialog.askdirectory() devolve "" quando a pessoa cancela o
    seletor - nada deve acontecer, a tela continua a mesma."""
    _resetar_para_escolher_pasta(app)

    monkeypatch.setattr(executar_robo_gui.filedialog, "askdirectory", lambda **kwargs: "")
    chamou_reiniciar = []
    monkeypatch.setattr(executar_robo_gui, "_reiniciar_programa", lambda: chamou_reiniciar.append(True))

    app._ao_clicar_escolher_pasta()

    assert not chamou_reiniciar


def test_ao_clicar_escolher_pasta_nao_gravavel_mostra_erro_sem_reiniciar(app, monkeypatch):
    _resetar_para_escolher_pasta(app)

    monkeypatch.setattr(executar_robo_gui.filedialog, "askdirectory", lambda **kwargs: "Z:\\pasta\\impossivel")
    monkeypatch.setattr(executar_robo_gui, "_pasta_e_gravavel", lambda pasta: False)
    chamou_reiniciar = []
    monkeypatch.setattr(executar_robo_gui, "_reiniciar_programa", lambda: chamou_reiniciar.append(True))

    app._ao_clicar_escolher_pasta()
    app.update()

    assert not chamou_reiniciar
    assert "Não foi possível" in app._label_erro_pasta["text"]


def test_ao_clicar_escolher_pasta_valida_salva_e_reinicia(app, monkeypatch, tmp_path):
    """Fluxo feliz de ponta a ponta: escolhe uma pasta válida, confirma
    que a escolha É GRAVADA DE VERDADE no arquivo de configuração local
    (não só que as funções foram chamadas), e que o programa tenta
    reiniciar em seguida."""
    _resetar_para_escolher_pasta(app)

    pasta_escolhida = tmp_path / "Pasta Escolhida Pela Pessoa"
    monkeypatch.setattr(config, "CONFIG_LOCAL_PATH", tmp_path / "config_local.json")
    monkeypatch.setattr(executar_robo_gui.filedialog, "askdirectory", lambda **kwargs: str(pasta_escolhida))
    monkeypatch.setattr(executar_robo_gui.messagebox, "showinfo", lambda *a, **k: None)  # não abre diálogo real
    chamou_reiniciar = []
    monkeypatch.setattr(executar_robo_gui, "_reiniciar_programa", lambda: chamou_reiniciar.append(True))

    app._ao_clicar_escolher_pasta()

    assert chamou_reiniciar == [True]
    assert config._carregar_sharepoint_dir_configurado() == pasta_escolhida
    assert pasta_escolhida.exists()  # a pasta em si também foi criada (_pasta_e_gravavel)


# ---------------------------------------------------------------------------
# Cancelamento (29/09/2026, pedido do usuário: "um botão que permita
# cancelar a varredura, caso seja necessário parar de executar o programa").
# ---------------------------------------------------------------------------


def test_botao_cancelar_existe_e_comeca_habilitado(app):
    _resetar(app, total_workers=2)
    assert app._botao_cancelar["state"] == "normal"


def test_ao_clicar_cancelar_recusado_nao_faz_nada(app, monkeypatch):
    _resetar(app, total_workers=1)
    monkeypatch.setattr(executar_robo_gui.messagebox, "askyesno", lambda *a, **k: False)

    app._ao_clicar_cancelar()

    assert not app._cancelado.is_set()
    assert app._botao_cancelar["state"] == "normal"


def test_ao_clicar_cancelar_confirmado_seta_flag_e_desabilita_botao(app, monkeypatch):
    _resetar(app, total_workers=1)
    monkeypatch.setattr(executar_robo_gui.messagebox, "askyesno", lambda *a, **k: True)

    app._ao_clicar_cancelar()

    assert app._cancelado.is_set()
    assert app._botao_cancelar["state"] == "disabled"
    assert "Cancelando" in app._label_status_geral["text"]


def test_ao_clicar_cancelar_libera_login_pendente(app, monkeypatch):
    """Se tiver um login pendente (navegador aberto esperando "Já fiz
    login"), cancelar precisa liberar esse wait() na hora, não só marcar
    a flag geral - ver _login_worker_gui()."""
    _resetar(app, total_workers=1)
    monkeypatch.setattr(executar_robo_gui.messagebox, "askyesno", lambda *a, **k: True)
    app._evento_login = threading.Event()
    app._botao_login.config(state="normal")

    app._ao_clicar_cancelar()

    assert app._evento_login.is_set()
    assert app._botao_login["state"] == "disabled"


def test_ao_clicar_cancelar_nao_faz_nada_se_ja_concluido(app, monkeypatch):
    _resetar(app, total_workers=1)
    app._execucao_concluida = True
    chamou_confirmacao = []
    monkeypatch.setattr(executar_robo_gui.messagebox, "askyesno", lambda *a, **k: chamou_confirmacao.append(True))

    app._ao_clicar_cancelar()

    assert not chamou_confirmacao
    assert not app._cancelado.is_set()


def test_ao_clicar_cancelar_nao_faz_nada_se_ja_cancelado(app, monkeypatch):
    _resetar(app, total_workers=1)
    app._cancelado.set()
    chamou_confirmacao = []
    monkeypatch.setattr(executar_robo_gui.messagebox, "askyesno", lambda *a, **k: chamou_confirmacao.append(True))

    app._ao_clicar_cancelar()

    assert not chamou_confirmacao


def test_mensagem_cancelado_com_totais(app):
    _resetar(app, total_workers=1)

    app._tratar_mensagem(("cancelado", "C:/fake/Relatorio_Multas.xlsx", 50, 3))
    app.update()

    assert app._execucao_concluida is True
    assert app._botao_cancelar["state"] == "disabled"
    assert "CANCELADO" in app._label_status_geral["text"]
    assert "50 multa" in app._label_resultado_final["text"]
    assert "3 nova" in app._label_resultado_final["text"]


def test_mensagem_cancelado_sem_totais_nao_quebra(app):
    """Se a consolidação de melhor esforço falhar (ex.: sessão também
    caiu no meio do cancelamento), total/novas vêm None - a tela precisa
    mostrar isso com clareza, sem quebrar nem mostrar "None" cru."""
    _resetar(app, total_workers=1)

    app._tratar_mensagem(("cancelado", "C:/fake/Relatorio_Multas.xlsx", None, None))
    app.update()

    assert "None" not in app._label_resultado_final["text"]
    assert "não foi possível confirmar" in app._label_resultado_final["text"]


def test_fazer_login_e_lancar_propaga_cancelamento_sem_marcar_falha(app, monkeypatch):
    """_CancelamentoSolicitado não é uma falha de login de verdade - tem
    que subir pra quem chamou (o laço de _orquestrar ou a reconexão)
    tratar, não pode ser engolida nem virar "[PAROU] falha no login"."""
    _resetar(app, total_workers=1)

    def _login_cancelado(wid):
        raise executar_robo_gui._CancelamentoSolicitado()

    monkeypatch.setattr(app, "_login_worker_gui", _login_cancelado)

    with pytest.raises(executar_robo_gui._CancelamentoSolicitado):
        app._fazer_login_e_lancar(0, total_workers=1)

    _drenar_fila(app)
    assert "[PAROU]" not in app._linhas_worker[0]["label"]["text"]


def test_orquestrar_cancelado_antes_do_1o_login_encerra_direto(app, monkeypatch):
    """Cenário mais simples: a pessoa cancela antes de qualquer worker
    logar - _orquestrar() precisa notar isso e ir direto pro
    encerramento, sem tentar logar ninguém."""
    _resetar(app, total_workers=2)
    app._cancelado.set()

    chamadas_encerrar = []
    monkeypatch.setattr(executar_robo_gui, "_encerrar_worker", lambda p: chamadas_encerrar.append(p))
    monkeypatch.setattr(executar_robo_gui, "_contar_linhas_planilha", lambda caminho: 5)
    monkeypatch.setattr(executar_robo_gui, "_consolidar_planilha_final", lambda: None)
    chamou_login = []
    monkeypatch.setattr(app, "_login_worker_gui", lambda wid: chamou_login.append(wid))

    app._orquestrar(2)
    _drenar_fila(app)

    assert not chamou_login
    assert not chamadas_encerrar  # nenhum processo pra encerrar - nada foi lançado
    assert app._execucao_concluida is True
    assert "CANCELADO" in app._label_status_geral["text"]


def test_orquestrar_cancelado_no_meio_do_laco_encerra_workers_ja_lancados(app, monkeypatch):
    """Cenário real: worker 0 já logou e foi lançado; a pessoa cancela
    antes do login do worker 1 começar - o worker 0 (já rodando de
    verdade) precisa ser encerrado, e o worker 1 nunca chega a logar."""
    _resetar(app, total_workers=2)

    class _ProcessoFalso:
        def poll(self):
            return None  # ainda "rodando"

    processo_worker_0 = _ProcessoFalso()

    def _login_fake(wid):
        if wid == 1:
            # Simula o clique em "Cancelar" bem nesse momento - a
            # _login_worker_gui() real detectaria a flag e levantaria
            # esse mesmo sinal (ver docstring dela), então o dublê
            # replica os 2 efeitos, não só a flag.
            app._cancelado.set()
            raise executar_robo_gui._CancelamentoSolicitado()

    monkeypatch.setattr(app, "_login_worker_gui", _login_fake)
    monkeypatch.setattr(executar_robo_gui, "_iniciar_worker", lambda wid, total: processo_worker_0)
    chamadas_encerrar = []
    monkeypatch.setattr(executar_robo_gui, "_encerrar_worker", lambda p: chamadas_encerrar.append(p))
    monkeypatch.setattr(executar_robo_gui, "_contar_linhas_planilha", lambda caminho: 5)
    monkeypatch.setattr(executar_robo_gui, "_consolidar_planilha_final", lambda: None)

    app._orquestrar(2)
    _drenar_fila(app)

    assert app._processos.get(0) is processo_worker_0
    assert 1 not in app._processos
    assert chamadas_encerrar == [processo_worker_0]
    assert "CANCELADO" in app._label_status_geral["text"]


def test_orquestrar_cancelado_durante_polling_encerra_workers(app, monkeypatch):
    """Todos os workers já lançados e "trabalhando" (poll() ainda None) -
    o cancelamento precisa ser notado dentro do laço de acompanhamento
    também, não só no laço de login."""
    _resetar(app, total_workers=1)

    class _ProcessoFalso:
        def poll(self):
            return None

    processo = _ProcessoFalso()
    monkeypatch.setattr(app, "_login_worker_gui", lambda wid: None)
    monkeypatch.setattr(executar_robo_gui, "_iniciar_worker", lambda wid, total: processo)
    monkeypatch.setattr(executar_robo_gui, "_status_legivel", lambda log_path: "50% concluído (5/10)")

    def _sleep_e_cancela(segundos):
        app._cancelado.set()

    monkeypatch.setattr(executar_robo_gui.time, "sleep", _sleep_e_cancela)
    chamadas_encerrar = []
    monkeypatch.setattr(executar_robo_gui, "_encerrar_worker", lambda p: chamadas_encerrar.append(p))
    monkeypatch.setattr(executar_robo_gui, "_contar_linhas_planilha", lambda caminho: 5)
    monkeypatch.setattr(executar_robo_gui, "_consolidar_planilha_final", lambda: None)

    app._orquestrar(1)
    _drenar_fila(app)

    assert chamadas_encerrar == [processo]
    assert "CANCELADO" in app._label_status_geral["text"]
