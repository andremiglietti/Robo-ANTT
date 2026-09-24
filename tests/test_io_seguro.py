"""
Testes de io_seguro.py - trava de concorrência entre execuções no mesmo
checkpoint (22/09/2026, ver CLAUDE.md - implementada depois de um
quase-incidente real: IHM + varredura manual escrevendo no mesmo arquivo
ao mesmo tempo).
"""
import pytest

# conftest.py (carregado automaticamente pelo pytest antes deste módulo)
# já insere src/ no sys.path - ver tests/conftest.py.
from robo_antt.io_seguro import ChecklistEmUsoError, adquirir_trava, liberar_trava


def test_adquirir_trava_funciona_na_primeira_vez(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    trava = adquirir_trava(checkpoint)
    assert trava.exists()
    liberar_trava(trava)


def test_segunda_aquisicao_com_processo_ainda_vivo_levanta_erro(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    trava = adquirir_trava(checkpoint)
    try:
        # o PID gravado é o deste próprio processo de teste - "ainda vivo"
        # é verdade por definição enquanto o teste roda.
        with pytest.raises(ChecklistEmUsoError):
            adquirir_trava(checkpoint)
    finally:
        liberar_trava(trava)


def test_liberar_e_readquirir_funciona(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    trava1 = adquirir_trava(checkpoint)
    liberar_trava(trava1)
    assert not trava1.exists()

    trava2 = adquirir_trava(checkpoint)
    assert trava2.exists()
    liberar_trava(trava2)


def test_trava_fantasma_de_processo_morto_e_removida_sozinha(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    trava = checkpoint.with_name(checkpoint.name + ".lock")
    trava.parent.mkdir(parents=True, exist_ok=True)
    trava.write_text("999999999", encoding="utf-8")  # PID quase certamente inexistente

    trava_nova = adquirir_trava(checkpoint)
    assert trava_nova.exists()
    assert trava_nova.read_text(encoding="utf-8").strip() != "999999999"
    liberar_trava(trava_nova)


def test_criacao_e_atomica_segunda_chamada_nunca_sobrescreve_a_primeira(tmp_path):
    """Achado na revisão crítica de 24/09/2026: a versão antiga fazia
    `exists()` e só depois `write_text()` como 2 passos separados (TOCTOU) -
    a criação agora usa O_CREAT|O_EXCL, atômica no SO. Confirma que o PID
    gravado no arquivo é sempre o do processo que criou primeiro, mesmo
    chamando adquirir_trava() de novo (sem liberar) - a 2ª chamada tem que
    falhar (ChecklistEmUsoError), nunca sobrescrever silenciosamente."""
    checkpoint = tmp_path / "checkpoint.json"
    trava1 = adquirir_trava(checkpoint)
    pid_gravado = trava1.read_text(encoding="utf-8").strip()

    with pytest.raises(ChecklistEmUsoError):
        adquirir_trava(checkpoint)

    # o conteúdo da trava não pode ter mudado - a 2ª chamada não escreveu nada
    assert trava1.read_text(encoding="utf-8").strip() == pid_gravado
    liberar_trava(trava1)


def test_conteudo_ilegivel_que_nunca_resolve_levanta_erro_claro(tmp_path):
    """Conteúdo ilegível (nem PID nem vazio-recém-criado que vai resolver
    sozinho) não pode ser tratado como "fantasma, apaga direto" - isso foi
    exatamente a causa do TOCTOU original. Depois de esgotar as
    retentativas, tem que levantar um erro claro, não apagar o arquivo de
    qualquer jeito nem entrar em loop infinito."""
    checkpoint = tmp_path / "checkpoint.json"
    trava = checkpoint.with_name(checkpoint.name + ".lock")
    trava.parent.mkdir(parents=True, exist_ok=True)
    trava.write_text("isso não é um PID válido", encoding="utf-8")

    with pytest.raises(ChecklistEmUsoError):
        adquirir_trava(checkpoint, tentativas=2, espera_segundos=0.01)

    # o arquivo ambíguo continua lá - nunca foi apagado automaticamente
    assert trava.exists()
