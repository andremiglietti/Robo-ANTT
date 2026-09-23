"""
Testes de scripts/executar_robo.py - _status_legivel() (a tradução do log
técnico de 1 worker pra 1 linha em português comum, usada pela IHM
terminal E pela GUI).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from executar_robo import _status_legivel  # noqa: E402


def _escrever_log(tmp_path: Path, conteudo: str) -> Path:
    caminho = tmp_path / "worker_0.log"
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def test_log_inexistente_diz_iniciando(tmp_path):
    caminho = tmp_path / "nao_existe.log"
    assert _status_legivel(caminho) == "iniciando..."


def test_progresso_no_meio_da_execucao_nao_confunde_total_historico_com_desta_execucao(tmp_path):
    """Achado ao vivo em 23/09/2026 (teste de login real da GUI): o
    usuário viu "11% concluído - 4189 multas encontradas até agora" logo
    no início de uma execução nova e estranhou - "4189" é o total
    HISTÓRICO do checkpoint (execuções anteriores incluídas), não algo
    achado nos primeiros segundos desta execução. A frase precisa deixar
    isso claro, não sugerir que é tudo novo."""
    log = _escrever_log(
        tmp_path,
        "[Progresso] 47/427 combinação(ões) CNPJ×tipo tentada(s) | "
        "total geral: 4189 processados, 0 falhas pendentes | decorrido: 5m00s",
    )
    status = _status_legivel(log)
    assert status.startswith("11% concluído")
    assert "histórico" in status  # não pode parecer que é tudo novo desta execução
    assert "encontradas até agora" not in status  # frase antiga, ambígua - não pode voltar


def test_parou_reporta_sessao_expirada():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        log = _escrever_log(Path(tmp), "algum log\n[PAROU] sessão expirou\nmais coisa")
        status = _status_legivel(log)
        assert status.startswith("[PAROU]")


def test_concluido_mostra_total_historico(tmp_path):
    log = _escrever_log(
        tmp_path,
        "=== VERIFICAÇÃO DE COMPLETUDE ===\nTotal processados (histórico completo): 500\n",
    )
    status = _status_legivel(log)
    assert status == "[OK] concluído - 500 multas no total (histórico completo)"


def test_sem_numero_de_progresso_ainda_diz_trabalhando(tmp_path):
    log = _escrever_log(tmp_path, "Abrindo o portal...\n")
    assert _status_legivel(log) == "trabalhando... (ainda sem número de progresso disponível)"


def test_antes_do_1o_checkpoint_de_10_usa_a_linha_de_item_como_sinal_de_vida(tmp_path):
    """Achado ao vivo em 23/09/2026 (login real com 5 workers): "[Progresso]"
    só aparece a cada 10 itens - com ~85 itens por worker, a pessoa ficava
    minutos vendo "sem número de progresso disponível" mesmo com o robô já
    tendo processado itens reais (um deles achou 327 registros no item 5).
    "[Item X/Y | ...]" imprime a cada item - usada como sinal de vida
    imediato antes do 1º checkpoint de 10."""
    log = _escrever_log(
        tmp_path,
        "[Item 1/86 | 92.660.604/0001-82 - YARA BRASIL FERTILIZANTES S/A | Excesso de Peso] concluído: 3 processo(s)\n"
        "[Item 2/86 | 92.660.604/0001-82 - YARA BRASIL FERTILIZANTES S/A | Cargas] sem processos\n",
    )
    status = _status_legivel(log)
    assert status == "2% concluído - trabalhando (combinação 2 de 86)"


def test_item_sem_cnpj_no_meio_nao_quebra_o_parsing(tmp_path):
    """Visto ao vivo: às vezes o CNPJ vem vazio entre os "|" - o parsing do
    número de item/total não pode depender do que tem depois."""
    log = _escrever_log(tmp_path, "[Item 13/86 | - YARA BRASIL FERTILIZANTES S.A | Passageiros Internacional] sem processos\n")
    assert _status_legivel(log) == "15% concluído - trabalhando (combinação 13 de 86)"
