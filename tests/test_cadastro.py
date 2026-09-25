"""
Testes de cadastro.py - mapeamento CNPJ -> Apelido (25/09/2026, pedido em
reunião com o time: "colocar junto ao nome da pasta do CNPJ o Apelido").

Os testes de `_normalizar_cnpj()` e `nome_pasta_cnpj()` NÃO dependem do
conteúdo real de `docs/CNPJ Dados cadastrais das Unidades.xlsb` (usam
`monkeypatch` no cache) - ficam estáveis mesmo se essa planilha for
atualizada pelo time no futuro. Só `test_carregar_apelidos_arquivo_real*`
lê o arquivo de verdade, pra confirmar que o parsing funciona contra o
formato real (achado ao vivo: a coluna CNPJ mistura número e string).
"""
from pathlib import Path

import pytest

from robo_antt import cadastro


@pytest.fixture(autouse=True)
def _limpar_cache():
    """Cada teste começa com o cache do módulo vazio (None) - senão um
    teste que carrega o arquivo real "vazaria" pros testes seguintes que
    esperam um cache controlado via monkeypatch."""
    cadastro._cache = None
    yield
    cadastro._cache = None


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (92660604012784.0, "92660604012784"),
        (92660604000182, "92660604000182"),
        ("92.660.604/0173-10", "92660604017310"),
        ("92660604017310", "92660604017310"),
        (None, None),
        ("sem nenhum digito", None),
    ],
)
def test_normalizar_cnpj(valor, esperado):
    assert cadastro._normalizar_cnpj(valor) == esperado


def test_carregar_apelidos_arquivo_inexistente_devolve_dict_vazio(tmp_path):
    assert cadastro.carregar_apelidos(tmp_path / "nao_existe.xlsb") == {}


def test_nome_pasta_cnpj_com_apelido_conhecido(monkeypatch):
    monkeypatch.setattr(cadastro, "_cache", {"92660604012784": "VIX3"})
    assert cadastro.nome_pasta_cnpj("92660604012784") == "92660604012784 - VIX3"


def test_nome_pasta_cnpj_sem_apelido_cai_no_cnpj_puro(monkeypatch):
    """Achado ao vivo em 25/09/2026: 3 dos 37 CNPJs já vistos pelo robô
    não têm entrada na planilha de cadastro - fallback é um caso real."""
    monkeypatch.setattr(cadastro, "_cache", {"92660604012784": "VIX3"})
    assert cadastro.nome_pasta_cnpj("92660604011540") == "92660604011540"


def test_carregar_apelidos_e_cacheado_so_le_o_arquivo_1_vez(monkeypatch):
    chamadas = []
    original_open_workbook = cadastro.open_workbook

    def _open_workbook_espiao(caminho):
        chamadas.append(caminho)
        return original_open_workbook(caminho)

    monkeypatch.setattr(cadastro, "open_workbook", _open_workbook_espiao)
    cadastro.carregar_apelidos()
    cadastro.carregar_apelidos()
    cadastro.carregar_apelidos()
    assert len(chamadas) == 1


# ---------------------------------------------------------------------------
# Contra o arquivo real - confirma que o parsing bate com o formato de
# verdade (coluna CNPJ mistura número e string, 2 abas). Roda pytest.skip()
# se o arquivo não existir localmente (não deveria acontecer - está no
# repositório - mas evita quebrar um clone incompleto).
# ---------------------------------------------------------------------------


def test_carregar_apelidos_arquivo_real_encontra_cnpjs_conhecidos():
    if not cadastro.CADASTRO_PATH.exists():
        pytest.skip(f"arquivo de cadastro ausente: {cadastro.CADASTRO_PATH}")
    apelidos = cadastro.carregar_apelidos()
    assert len(apelidos) >= 50  # confirmado ao vivo: 58 CNPJs únicos nas 2 abas
    assert all(len(cnpj) == 14 and cnpj.isdigit() for cnpj in apelidos)
    assert all(isinstance(apelido, str) and apelido for apelido in apelidos.values())
