"""
Testes de orquestrador.py - só as partes que não precisam de navegador
real (Playwright). `_atualizar_situacao_se_necessario()` é pura o
suficiente pra testar isolada (só mexe na planilha em memória).
"""
from pathlib import Path

# conftest.py (carregado automaticamente pelo pytest antes deste módulo)
# já insere src/ no sys.path - ver tests/conftest.py.
from robo_antt import checkpoint
from robo_antt.orquestrador import _atualizar_situacao_se_necessario, _combinacao_so_tem_falhas_permanentes
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


# ---------------------------------------------------------------------------
# _combinacao_so_tem_falhas_permanentes() - pedido do usuário em 24/09/2026:
# não gastar as rodadas 2/3 de retentativa numa combinação cujas falhas
# restantes já são conhecidas como permanentes (ver checkpoint.py).
# ---------------------------------------------------------------------------


def _estado_com_falha_repetida(auto: str, cnpj: str, tipo_value: str, vezes: int) -> dict:
    estado = checkpoint.carregar(Path("__checkpoint_inexistente__.json"))
    for _ in range(vezes):
        checkpoint.marcar_falha(estado, auto, "erro", cnpj=cnpj, tipo_value=tipo_value)
    return estado


def test_combinacao_com_falha_nova_nao_e_permanente():
    estado = _estado_com_falha_repetida("AUTO1", "123", "2", vezes=1)
    assert not _combinacao_so_tem_falhas_permanentes(estado, "123", "2")


def test_combinacao_com_falha_ja_confirmada_permanente():
    estado = _estado_com_falha_repetida("AUTO1", "123", "2", vezes=checkpoint.LIMITE_TENTATIVAS_PROVAVEL_PERMANENTE)
    assert _combinacao_so_tem_falhas_permanentes(estado, "123", "2")


def test_combinacao_com_1_falha_nova_e_1_permanente_nao_e_so_permanente():
    """Se sobra pelo menos 1 falha ainda "nova" na combinação, ela continua
    valendo as rodadas extras normais - só pula quando NENHUMA falha
    restante merece mais insistência."""
    estado = _estado_com_falha_repetida("AUTO_VELHO", "123", "2", vezes=checkpoint.LIMITE_TENTATIVAS_PROVAVEL_PERMANENTE)
    checkpoint.marcar_falha(estado, "AUTO_NOVO", "erro", cnpj="123", tipo_value="2")
    assert not _combinacao_so_tem_falhas_permanentes(estado, "123", "2")


def test_combinacao_sem_nenhuma_falha_pendente_nao_e_permanente():
    """Combinação sem falha nenhuma (já resolvida, ou nunca teve) não deve
    ser tratada como "só permanentes" - não há nada aqui pra pular."""
    estado = checkpoint.carregar(Path("__checkpoint_inexistente__.json"))
    assert not _combinacao_so_tem_falhas_permanentes(estado, "123", "2")
