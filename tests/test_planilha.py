"""
Testes de planilha.py - cache de ja_registrado() (22/09/2026), backfill
de células vazias (atualizar_campos_vazios(), 22/09/2026) e conversão pra
tipo nativo do Excel em colunas de data/valor (23/09/2026).
"""
import datetime
from pathlib import Path

# conftest.py (carregado automaticamente pelo pytest antes deste módulo)
# já insere src/ no sys.path - ver tests/conftest.py.
from robo_antt.planilha import (
    _converter_para_tipo_nativo,
    abrir_ou_criar,
    adicionar_registro,
    atualizar_campos_vazios,
    ja_registrado,
    salvar,
)


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
    assert registro["Valor"] == 100.0  # preenchida, convertida pro tipo nativo (ver 23/09/2026)


def test_atualizar_campos_vazios_auto_inexistente_devolve_zero():
    wb = abrir_ou_criar(Path("__inexistente__.xlsx"))
    assert atualizar_campos_vazios(wb, "NAO_EXISTE", {"placa": "ABC1234"}) == 0


# ---------------------------------------------------------------------------
# Conversão pra tipo nativo do Excel (23/09/2026) - ver CLAUDE.md: datas e
# valores eram gravados como texto puro, impedindo ordenar/filtrar/somar
# no Excel sem conversão manual.
# ---------------------------------------------------------------------------


def test_converter_data_valida():
    resultado = _converter_para_tipo_nativo("Data Autuação", "23/07/2016")
    assert resultado == datetime.date(2016, 7, 23)


def test_converter_valor_com_milhar():
    assert _converter_para_tipo_nativo("Valor", "1.992,16") == 1992.16


def test_converter_valor_sem_milhar():
    assert _converter_para_tipo_nativo("Valor Desconto", "398,43") == 398.43


def test_converter_e_idempotente_com_tipo_ja_nativo():
    """Reconsolidar uma planilha já migrada não pode quebrar - o valor já
    vem como datetime.date/float, não como string."""
    data_nativa = datetime.date(2020, 1, 1)
    assert _converter_para_tipo_nativo("Data Vencimento", data_nativa) is data_nativa
    assert _converter_para_tipo_nativo("Valor", 100.5) == 100.5


def test_converter_formato_atipico_mantem_texto_original():
    """Nunca perde o dado por causa de 1 formato inesperado - devolve a
    string original em vez de levantar exceção ou inventar um número."""
    assert _converter_para_tipo_nativo("Valor", "92.660.604") == "92.660.604"
    assert _converter_para_tipo_nativo("Data Autuação", "data inválida") == "data inválida"


def test_converter_coluna_nao_monetaria_nao_muda():
    assert _converter_para_tipo_nativo("Placa", "ABC1234") == "ABC1234"
    assert _converter_para_tipo_nativo("Código de Barras", "001-9 00190") == "001-9 00190"


def test_converter_none_e_vazio_passam_direto():
    assert _converter_para_tipo_nativo("Valor", None) is None
    assert _converter_para_tipo_nativo("Data Autuação", "") == ""


def test_adicionar_registro_grava_tipo_nativo_com_formato():
    wb = abrir_ou_criar(Path("__inexistente__.xlsx"))
    adicionar_registro(
        wb,
        {
            "auto_infracao": "AUTO_TIPO",
            "cnpj": "123",
            "data_autuacao": "23/07/2016",
            "valor": "1.992,16",
        },
    )
    ws = wb.active
    from robo_antt.planilha import COLUNAS

    col_data = COLUNAS.index("Data Autuação") + 1
    col_valor = COLUNAS.index("Valor") + 1
    celula_data = ws.cell(row=2, column=col_data)
    celula_valor = ws.cell(row=2, column=col_valor)

    assert celula_data.value == datetime.date(2016, 7, 23)
    assert celula_data.number_format == "DD/MM/YYYY"
    assert celula_valor.value == 1992.16
    assert celula_valor.number_format == "R$ #,##0.00"
