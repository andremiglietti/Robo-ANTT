"""
Testes de planilha.py - cache de ja_registrado() (22/09/2026) e backfill
de células vazias (atualizar_campos_vazios(), 22/09/2026).
"""
from pathlib import Path

# conftest.py (carregado automaticamente pelo pytest antes deste módulo)
# já insere src/ no sys.path - ver tests/conftest.py.
from robo_antt.planilha import abrir_ou_criar, adicionar_registro, atualizar_campos_vazios, ja_registrado, salvar


def test_ja_registrado_acha_autos_existentes_e_nao_existentes():
    wb = abrir_ou_criar(Path("__inexistente__.xlsx"))
    for i in range(50):
        adicionar_registro(wb, {"auto_infracao": f"AUTO{i:04d}", "cnpj": "123"})

    assert ja_registrado(wb, "AUTO0000")
    assert ja_registrado(wb, "AUTO0049")
    assert not ja_registrado(wb, "NAO_EXISTE")


def test_ja_registrado_cache_frio_ao_reabrir_do_disco(tmp_path):
    caminho = tmp_path / "planilha.xlsx"
    wb = abrir_ou_criar(caminho)
    adicionar_registro(wb, {"auto_infracao": "AUTO0001", "cnpj": "123"})
    salvar(wb, caminho)

    wb2 = abrir_ou_criar(caminho)  # cache ainda não existe nesta instância nova
    assert ja_registrado(wb2, "AUTO0001")
    assert not ja_registrado(wb2, "NAO_EXISTE")


def test_adicionar_registro_mantem_cache_incremental():
    wb = abrir_ou_criar(Path("__inexistente__.xlsx"))
    ja_registrado(wb, "QUALQUER")  # força a criação do cache
    adicionar_registro(wb, {"auto_infracao": "NOVO", "cnpj": "123"})
    assert ja_registrado(wb, "NOVO")  # tem que estar no cache na hora, sem reconstruir


def test_atualizar_campos_vazios_so_preenche_celula_vazia():
    wb = abrir_ou_criar(Path("__inexistente__.xlsx"))
    adicionar_registro(wb, {"auto_infracao": "AUTO1", "cnpj": "123", "placa": "ABC1234", "valor": None})

    preenchidos = atualizar_campos_vazios(wb, "AUTO1", {"placa": "XYZ9999", "valor": "100,00"})

    assert preenchidos == 1  # só "valor" estava vazio - "placa" não deve ser sobrescrita
    ws = wb.active
    linha = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
    registro = dict(zip([c.value for c in next(ws.iter_rows(min_row=1, max_row=1))], linha))
    assert registro["Placa"] == "ABC1234"  # preservada, não sobrescrita
    assert registro["Valor"] == "100,00"  # preenchida


def test_atualizar_campos_vazios_auto_inexistente_devolve_zero():
    wb = abrir_ou_criar(Path("__inexistente__.xlsx"))
    assert atualizar_campos_vazios(wb, "NAO_EXISTE", {"placa": "ABC1234"}) == 0
