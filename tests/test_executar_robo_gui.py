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
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from executar_robo_gui import AppRobo, _percentual_de, _resumo_completude_legivel  # noqa: E402


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

    app._tratar_mensagem(("concluido", "C:/fake/Relatorio_Multas.xlsx", "Confirmado: 100% completo."))
    app.update()

    assert "CONCLU" in app._label_status_geral["text"]
    assert "Relatorio_Multas.xlsx" in app._label_resultado_final["text"]
    assert "Confirmado: 100% completo." in app._label_resultado_final["text"]


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
