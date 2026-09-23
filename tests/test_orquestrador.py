"""
Testes de orquestrador.py - só as partes que não precisam de navegador
real (Playwright). `_atualizar_situacao_se_necessario()` é pura o
suficiente pra testar isolada (só mexe na planilha em memória).
"""
from pathlib import Path

# conftest.py (carregado automaticamente pelo pytest antes deste módulo)
# já insere src/ no sys.path - ver tests/conftest.py.
from robo_antt.orquestrador import _atualizar_situacao_se_necessario
from robo_antt.planilha import abrir_ou_criar, adicionar_registro


def test_preenche_situacao_vazia_de_auto_ja_conhecido():
    """Achado em 23/09/2026 (ver CLAUDE.md): "Situação" só era gravada na
    1ª vez que um auto era processado - autos já conhecidos, revisitados
    numa reexecução, nunca ganhavam esse campo mesmo a busca trazendo o
    valor de novo. Corrigido chamando isso nos 2 caminhos de "já
    conhecido" de processar_linha()."""
    wb = abrir_ou_criar(Path("__inexistente__.xlsx"))
    adicionar_registro(wb, {"auto_infracao": "AUTO1", "cnpj": "123", "situacao": None})

    _atualizar_situacao_se_necessario(wb, "AUTO1", {"situacao": "Arquivado - Pago"})

    ws = wb.active
    from robo_antt.planilha import COLUNAS

    col_situacao = COLUNAS.index("Situação")
    linha = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
    assert linha[col_situacao] == "Arquivado - Pago"


def test_nao_sobrescreve_situacao_ja_preenchida():
    wb = abrir_ou_criar(Path("__inexistente__.xlsx"))
    adicionar_registro(wb, {"auto_infracao": "AUTO1", "cnpj": "123", "situacao": "Recurso em julgamento"})

    _atualizar_situacao_se_necessario(wb, "AUTO1", {"situacao": "Arquivado - Pago"})

    ws = wb.active
    from robo_antt.planilha import COLUNAS

    col_situacao = COLUNAS.index("Situação")
    linha = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
    assert linha[col_situacao] == "Recurso em julgamento"  # preservado, não sobrescrito


def test_sem_situacao_na_row_nao_faz_nada():
    wb = abrir_ou_criar(Path("__inexistente__.xlsx"))
    adicionar_registro(wb, {"auto_infracao": "AUTO1", "cnpj": "123"})
    _atualizar_situacao_se_necessario(wb, "AUTO1", {})  # não levanta exceção
