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


def test_progresso_no_meio_da_execucao_mostra_so_percentual_e_fracao(tmp_path):
    """Achado ao vivo em 23/09/2026 (teste de login real da GUI): o
    usuário viu "11% concluído - 4189 multas encontradas até agora" logo
    no início de uma execução nova e estranhou - "4189" é o total
    HISTÓRICO do checkpoint (execuções anteriores incluídas), não algo
    achado nos primeiros segundos desta execução.

    Corrigido uma 1ª vez em 23/09/2026 deixando a frase mais honesta
    ("histórico, inclui execuções anteriores"); corrigido de novo (mais a
    fundo) em 24/09/2026 a pedido direto do usuário revendo a GUI: o
    número histórico simplesmente não ajuda na linha de andamento - só
    percentual e fração importam enquanto ainda está rodando. O total de
    verdade (quantas verificadas, quantas novas) passou a aparecer só no
    resumo final, depois de consolidar (ver executar_robo_gui.py)."""
    log = _escrever_log(
        tmp_path,
        "[Progresso] 47/427 combinação(ões) CNPJ×tipo tentada(s) | "
        "total geral: 4189 processados, 0 falhas pendentes | decorrido: 5m00s",
    )
    status = _status_legivel(log)
    assert status == "11% concluído (47/427)"
    assert "4189" not in status  # número histórico não pertence mais à linha de andamento


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
    # achado ao vivo em 24/09/2026: "- trabalhando..." aqui só, e não no ramo
    # "[Progresso]" (mesmo formato "X% concluído (Y/Z)"), fazia alguns
    # workers mostrarem sufixo e outros não, sem nenhuma explicação visível.
    assert status == "2% concluído (2/86)"


def test_item_sem_cnpj_no_meio_nao_quebra_o_parsing(tmp_path):
    """Visto ao vivo: às vezes o CNPJ vem vazio entre os "|" - o parsing do
    número de item/total não pode depender do que tem depois."""
    log = _escrever_log(tmp_path, "[Item 13/86 | - YARA BRASIL FERTILIZANTES S.A | Passageiros Internacional] sem processos\n")
    assert _status_legivel(log) == "15% concluído (13/86)"


def test_progresso_100_por_cento_nao_diz_concluido(tmp_path):
    """Achado ao vivo em 24/09/2026: workers encerrados à força no meio das
    retentativas mostravam "100% concluído" mesmo com dezenas de falhas
    pendentes nunca reportadas - "100%" no [Progresso] só significa que o
    loop principal passou por todas as combinações, não que terminou sem
    pendência (só o ramo "[OK] concluído", que exige a seção VERIFICAÇÃO DE
    COMPLETUDE no log, representa isso). O texto não pode mais dizer
    "concluído" nesse ponto."""
    log = _escrever_log(
        tmp_path,
        "[Progresso] 427/427 combinação(ões) CNPJ×tipo tentada(s) | "
        "total geral: 4189 processados, 80 falhas pendentes | decorrido: 5h00s",
    )
    status = _status_legivel(log)
    assert "concluído" not in status
    assert "(427/427)" in status
    assert "100%" in status  # ainda menciona 100%, mas não como "concluído"


def test_item_mais_recente_prevalece_sobre_progresso_desatualizado(tmp_path):
    """Achado ao vivo em 24/09/2026 (usuário testando com 10 workers reais):
    depois do 1º checkpoint de 10, o número ficava "preso" nesse valor e só
    pulava de 10 em 10 nos checkpoints seguintes - mesmo "[Item X/Y]" (a
    cada item, sempre mais atual) já tendo o número certo no log o tempo
    todo. Aqui: "[Progresso]" parou no item 10, mas já tem 3 "[Item]"
    depois disso (13, 14, 15) - o status tem que refletir 15, não 10."""
    log = _escrever_log(
        tmp_path,
        "[Progresso] 10/86 combinação(ões) CNPJ×tipo tentada(s) | "
        "total geral: 100 processados, 0 falhas pendentes | decorrido: 1m00s\n"
        "[Item 13/86 | 92.660.604/0001-82 - YARA BRASIL FERTILIZANTES S/A | Cargas] sem processos\n"
        "[Item 14/86 | 92.660.604/0001-82 - YARA BRASIL FERTILIZANTES S/A | Passageiros] sem processos\n"
        "[Item 15/86 | 92.660.604/0001-82 - YARA BRASIL FERTILIZANTES S/A | Cargas Internacional] sem processos\n",
    )
    status = _status_legivel(log)
    assert status == "17% concluído (15/86)"


def test_item_100_por_cento_nao_diz_concluido(tmp_path):
    """Mesmo achado do teste acima, mas pelo ramo de fallback ([Item X/Y]),
    usado antes do 1º checkpoint de 10 - também não pode dizer "concluído"
    quando X == Y."""
    log = _escrever_log(tmp_path, "[Item 86/86 | 92.660.604/9999-99 - YARA BRASIL FERTILIZANTES S/A | Cargas] sem processos\n")
    status = _status_legivel(log)
    assert "concluído" not in status
    assert "(86/86)" in status
