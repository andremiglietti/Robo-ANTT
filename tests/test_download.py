"""
Testes de download.py - achado na revisão crítica de 24/09/2026: zero
testes dedicados, apesar de ser o módulo que já causou vários bugs reais
documentados (linha não encontrada, tabela invalidada, download que vem
como HTML em vez de PDF - ver CLAUDE.md).

`_eh_pdf_valido()`/`already_downloaded()` são 100% locais (sem Page) -
testados direto. `_mensagem_tabela_vazia()`/`_localizar_linha()` precisam
de um `Page` - usa `page.set_content()` com HTML sintético (fixture `page`,
ver conftest.py e test_portal.py), sem sessão nem portal real.
"""
import robo_antt.download as download_mod
from robo_antt.download import (
    TabelaInvalidadaError,
    _eh_pdf_valido,
    _localizar_linha,
    _mensagem_tabela_vazia,
    already_downloaded,
)

# ---------------------------------------------------------------------------
# _eh_pdf_valido() - 100% local, sem Page.
# ---------------------------------------------------------------------------


def test_eh_pdf_valido_aceita_arquivo_com_assinatura_pdf(tmp_path):
    caminho = tmp_path / "auto.pdf"
    caminho.write_bytes(b"%PDF-1.4\n%resto do conteudo nao importa aqui")
    assert _eh_pdf_valido(caminho)


def test_eh_pdf_valido_rejeita_html_disfarcado_de_pdf(tmp_path):
    """Achado ao vivo em 16/09/2026 (ver CLAUDE.md): alguns downloads vêm
    como a página HTML de erro do portal, não o PDF de verdade - sem essa
    checagem, isso corromperia silenciosamente o resultado."""
    caminho = tmp_path / "auto.pdf"
    caminho.write_bytes(b"<!DOCTYPE html><html><body>erro do servidor</body></html>")
    assert not _eh_pdf_valido(caminho)


# ---------------------------------------------------------------------------
# already_downloaded() - 100% local, sem Page, sem tocar em DOWNLOAD_DIR
# real (monkeypatch aponta pra um tmp_path descartável).
# ---------------------------------------------------------------------------


def test_already_downloaded_encontra_arquivo_existente(tmp_path, monkeypatch):
    monkeypatch.setattr(download_mod, "DOWNLOAD_DIR", tmp_path)
    pasta = tmp_path / "92660604000182" / "Excesso de Peso"
    pasta.mkdir(parents=True)
    (pasta / "EPSMA00087472019.pdf").write_bytes(b"%PDF-1.4")

    encontrado = already_downloaded("EPSMA00087472019", "92660604000182")
    assert encontrado == pasta / "EPSMA00087472019.pdf"


def test_already_downloaded_nao_encontra_cnpj_inexistente(tmp_path, monkeypatch):
    monkeypatch.setattr(download_mod, "DOWNLOAD_DIR", tmp_path)
    assert already_downloaded("QUALQUER00000012019", "00000000000000") is None


def test_already_downloaded_nao_encontra_auto_diferente_no_mesmo_cnpj(tmp_path, monkeypatch):
    monkeypatch.setattr(download_mod, "DOWNLOAD_DIR", tmp_path)
    pasta = tmp_path / "92660604000182" / "Cargas"
    pasta.mkdir(parents=True)
    (pasta / "CRGTF00018212019.pdf").write_bytes(b"%PDF-1.4")

    assert already_downloaded("CRGTF00099999999", "92660604000182") is None


# ---------------------------------------------------------------------------
# _mensagem_tabela_vazia() - precisa de Page (lê o DOM), sem sessão/portal.
# ---------------------------------------------------------------------------


def test_mensagem_tabela_vazia_zero_linhas(page):
    """Achado ao vivo em 21/09/2026: a tabela pode ficar com ZERO <tr>
    (nem o placeholder "Nenhum registro encontrado" chega a aparecer)."""
    page.set_content('<table id="Corpo_gdvResultado"></table>')
    assert _mensagem_tabela_vazia(page) == "tabela sem nenhuma linha"


def test_mensagem_tabela_vazia_placeholder_nenhum_registro(page):
    page.set_content(
        '<table id="Corpo_gdvResultado"><tr><td colspan="6">Nenhum registro encontrado.</td></tr></table>'
    )
    assert _mensagem_tabela_vazia(page) == "Nenhum registro encontrado."


def test_mensagem_tabela_vazia_com_dados_reais_devolve_none(page):
    page.set_content(
        """
        <table id="Corpo_gdvResultado">
          <tr><th>Auto</th><th>Processo</th></tr>
          <tr><td>EPSMA00087472019</td><td>12345.678901/2019-00</td></tr>
        </table>
        """
    )
    assert _mensagem_tabela_vazia(page) is None


# ---------------------------------------------------------------------------
# _localizar_linha() - caminho feliz (linha já visível) e o caminho de
# TabelaInvalidadaError (tabela virou "Nenhum registro encontrado" no meio).
# Não testa o caso "linha realmente sumiu mas tabela continua com dado" (o
# ValueError genérico) porque isso exige esperar o timeout inteiro
# (TIMEOUT_LOCALIZAR_LINHA_MS × tentativas) de propósito - lento demais pra
# suite automatizada, sem ganho real (a lógica em si já é coberta pelos 2
# outros casos).
# ---------------------------------------------------------------------------


def test_localizar_linha_encontra_linha_visivel_de_cara(page):
    page.set_content(
        """
        <table id="Corpo_gdvResultado">
          <tr><th>Auto</th></tr>
          <tr><td>EPSMA00087472019</td><td><input type="image"/></td></tr>
        </table>
        """
    )
    linha = _localizar_linha(page, "EPSMA00087472019")
    assert linha.count() == 1


def test_localizar_linha_tabela_invalidada_levanta_erro_especifico(page):
    page.set_content(
        '<table id="Corpo_gdvResultado"><tr><td colspan="6">Nenhum registro encontrado.</td></tr></table>'
    )
    try:
        _localizar_linha(page, "EPSMA00087472019", tentativas=1)
        assert False, "deveria ter levantado TabelaInvalidadaError"
    except TabelaInvalidadaError as e:
        assert "Nenhum registro encontrado" in str(e)
