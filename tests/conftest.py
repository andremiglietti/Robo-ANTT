"""
Configuração compartilhada dos testes (ver CLAUDE.md, 22/09/2026 - suite
criada depois de encontrar 4 bugs reais de extração só por auditoria
manual ao vivo, sem nenhuma rede de proteção automatizada).

As fixtures em tests/fixtures/ são PDFs REAIS (5 exemplos originais +
documentos-problema descobertos hoje) - gitignorados pela mesma regra
`*.pdf` que já protege `data/downloads/` (contêm CPF/CNPJ/dados de
motoristas reais, nunca versionar - ver CLAUDE.md, "Notas de segurança").
Isso significa: um clone novo do repositório não vai ter esses arquivos
até alguém copiá-los manualmente - os testes que dependem deles usam
`pdf_fixture()` abaixo, que faz `pytest.skip()` (não falha) se o arquivo
não existir, em vez de quebrar o `pytest` inteiro num ambiente sem os
PDFs locais.
"""
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def pdf_fixture(nome: str) -> Path:
    """Caminho de um PDF de fixture - pytest.skip() se o arquivo não
    existir localmente (ver docstring do módulo)."""
    caminho = FIXTURES_DIR / nome
    if not caminho.exists():
        pytest.skip(f"fixture ausente: {nome} (PDFs reais são gitignorados - ver tests/conftest.py)")
    return caminho


# ---------------------------------------------------------------------------
# Fixture de navegador (24/09/2026, ver CLAUDE.md - revisão crítica): até
# hoje, portal.py e download.py (juntos, mais de 700 linhas - boa parte do
# código que já causou bug real em produção) não tinham NENHUM teste
# automatizado, porque toda a lógica interage com um `Page` do Playwright.
# Não precisa do portal real nem de sessão pra testar isso: `page.set_content()`
# carrega HTML sintético local (offline, sem rede) que imita a estrutura real
# do DOM (capturada em codigos_site/ - ver CLAUDE.md), permitindo testar a
# lógica de parsing/seleção de verdade contra um `Page` de verdade, sem
# tocar no portal.
# ---------------------------------------------------------------------------
from playwright.sync_api import sync_playwright  # noqa: E402


@pytest.fixture(scope="session")
def _browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(_browser):
    pagina = _browser.new_page()
    yield pagina
    pagina.close()
