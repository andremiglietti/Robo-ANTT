"""
Testes de regressão pra extracao.py - cada teste aqui existe pra travar
um bug real encontrado ao vivo em 16-22/09/2026 (ver CLAUDE.md), pra que
uma mudança futura não reintroduza o mesmo problema sem ninguém notar.
"""
from conftest import pdf_fixture

from robo_antt.extracao import (
    extrair_campos_boleto,
    extrair_campos_pagina1,
    extrair_texto_pagina1,
    identificar_tipo_multa,
    localizar_pagina_boleto,
)

# ---------------------------------------------------------------------------
# Os 5 exemplos originais (15-16/09/2026) - devem continuar 100% corretos
# em TODOS os campos, sempre. Qualquer regressão aqui é grave.
# ---------------------------------------------------------------------------

_EXEMPLOS_PAGINA1 = {
    "excesso_peso.pdf": "Excesso de Peso",
    "piso_minimo.pdf": "Piso Mínimo de Frete",
    "piso_minimo_2.pdf": "Piso Mínimo de Frete",
    "produtos_perigosos.pdf": "Produtos Perigosos",
    "vale_pedagio.pdf": "Vale-Pedágio",
}


def test_identificar_tipo_multa_nos_5_exemplos():
    for nome_arquivo, tipo_esperado in _EXEMPLOS_PAGINA1.items():
        caminho = pdf_fixture(nome_arquivo)
        texto = extrair_texto_pagina1(caminho)
        assert identificar_tipo_multa(texto) == tipo_esperado, nome_arquivo


def test_campos_pagina1_completos_nos_5_exemplos():
    campos_obrigatorios = [
        "placa",
        "cnpj_infrator",
        "data_autuacao",
        "descricao_infracao",
        "tipo_documento_fiscal",
        "numero_documento_fiscal",
        "data_emissao_doc_fiscal",
    ]
    for nome_arquivo in _EXEMPLOS_PAGINA1:
        caminho = pdf_fixture(nome_arquivo)
        campos = extrair_campos_pagina1(caminho)
        for campo in campos_obrigatorios:
            assert campos.get(campo), f"{nome_arquivo}: campo '{campo}' veio vazio"


_EXEMPLOS_BOLETO = {
    "excesso_peso.pdf": {"valor": "1.992,16", "valor_desconto": "398,43"},
    "piso_minimo.pdf": {"valor": "2.575,00", "valor_desconto": "772,50"},
    "produtos_perigosos.pdf": {"valor": "1.400,00", "valor_desconto": "420,00"},
}


def test_boleto_valor_e_desconto_nos_3_exemplos_com_boleto():
    for nome_arquivo, esperado in _EXEMPLOS_BOLETO.items():
        caminho = pdf_fixture(nome_arquivo)
        pagina = localizar_pagina_boleto(caminho)
        assert pagina, f"{nome_arquivo}: boleto deveria existir"
        campos = extrair_campos_boleto(caminho, pagina)
        assert campos["valor"] == esperado["valor"], nome_arquivo
        assert campos["valor_desconto"] == esperado["valor_desconto"], nome_arquivo


def test_piso_minimo_2_e_vale_pedagio_nao_tem_boleto():
    # confirmado em 15-16/09/2026: 2 dos 5 exemplos legitimamente não têm
    # boleto ainda (processo sem notificação gerada) - localizar_pagina_boleto()
    # deve devolver None, não erro.
    for nome_arquivo in ("piso_minimo_2.pdf", "vale_pedagio.pdf"):
        caminho = pdf_fixture(nome_arquivo)
        assert localizar_pagina_boleto(caminho) is None, nome_arquivo


# ---------------------------------------------------------------------------
# Regressões específicas - cada uma trava um bug real de 22/09/2026.
# ---------------------------------------------------------------------------


def test_hifen_suave_nao_zera_campos_da_pagina1():
    """EPSMA00092252019.pdf: rótulos usam hífen suave (U+00AD) em vez de
    "-" normal (ex.: "01\xadPLACA") - antes da correção, placa/data/
    descrição vinham todos None mesmo com o dado presente no PDF."""
    caminho = pdf_fixture("EPSMA00092252019.pdf")
    campos = extrair_campos_pagina1(caminho)
    assert campos["placa"] == "GLK3691"
    assert campos["data_autuacao"] == "06/03/2019"
    assert campos["descricao_infracao"]  # tem bug de acentuação (�), mas não pode ser None


def test_placa_sem_prefixo_numerico():
    """EPSF100022542020.pdf: célula é só "PLACA\\n<valor>", sem o "01 - "
    que a regex original exigia."""
    caminho = pdf_fixture("EPSF100022542020.pdf")
    campos = extrair_campos_pagina1(caminho)
    assert campos["placa"] == "IAZ3D92"


def test_documento_2016_descricao_genuinamente_vazia_mas_resto_ok():
    """0022356257.pdf: formato antigo (auto só numérico) - o campo
    'DESCRIÇÃO' não tem valor nenhum no PDF de origem (célula só com o
    rótulo) - isso é uma limitação do documento, não um bug nosso. Os
    outros campos (placa, data, doc fiscal) continuam funcionando."""
    caminho = pdf_fixture("0022356257.pdf")
    campos = extrair_campos_pagina1(caminho)
    assert campos["placa"] == "IPX0992"
    assert campos["data_autuacao"] == "23/07/2016"
    assert campos["descricao_infracao"] is None


def test_valor_nao_captura_cnpj_de_coluna_vizinha():
    """EPSMA00440082022.pdf: sub-layout GRU de 3 colunas - o texto corrido
    intercala colunas, e a regex antiga capturava um CNPJ ('92.660.604')
    em vez do valor real ('146,12'). Bug de CORRETUDE, não só completude."""
    caminho = pdf_fixture("EPSMA00440082022.pdf")
    pagina = localizar_pagina_boleto(caminho)
    campos = extrair_campos_boleto(caminho, pagina)
    assert campos["valor"] == "146,12"
    assert campos["valor_desconto"] == "29,22"


def test_valor_desconto_calculado_por_subtracao_quando_celula_vazia():
    """0001443878.pdf: célula "Desconto/Abatimento" existe mas está
    genuinamente vazia no PDF - só "VALOR COM DESCONTO(R$)" tem número.
    valor_desconto = valor - valor_com_desconto = 101,09 - 80,87 = 20,22."""
    caminho = pdf_fixture("0001443878.pdf")
    pagina = localizar_pagina_boleto(caminho)
    campos = extrair_campos_boleto(caminho, pagina)
    assert campos["valor"] == "101,09"
    assert campos["valor_desconto"] == "20,22"


def test_valor_desconto_celula_gru_com_quebra_de_linha():
    """CRGPP00000072026.pdf: célula "2 - (-) DESCONTO / ABATIMENTO\\n420,00"
    tem valor limpo, mas o texto corrido intercalava algo entre rótulo e
    valor (resultado antigo: '4', um fragmento truncado)."""
    caminho = pdf_fixture("CRGPP00000072026.pdf")
    pagina = localizar_pagina_boleto(caminho)
    campos = extrair_campos_boleto(caminho, pagina)
    assert campos["valor_desconto"] == "420,00"


def test_divida_ativa_sem_pagina_de_auto_cai_em_outros():
    """CRGPF00004092019.pdf: página 1 é um "Comprovante de erro retornado
    ao cadastrar crédito na Dívida Ativa", não um auto de infração de
    verdade - identificar_tipo_multa() deve cair em "Outros" (revisão
    manual) em vez de crashar ou classificar errado."""
    caminho = pdf_fixture("CRGPF00004092019.pdf")
    texto = extrair_texto_pagina1(caminho)
    assert identificar_tipo_multa(texto) == "Outros"


# ---------------------------------------------------------------------------
# Auditoria da pasta "Outros" (23/09/2026, ver CLAUDE.md) - achou 2 tipos
# genuinamente novos e um bug de regex que jogava vários "Excesso de Peso"
# em "Outros" por engano.
# ---------------------------------------------------------------------------


def test_regex_com_dotall_acha_peso_em_cabecalho_multilinha():
    """EPSB200007882022.pdf (e outros com o mesmo prefixo EPS*): o
    cabeçalho quebra em várias linhas ("NOTIFICAÇÃO DA AUTUAÇÃO
    EXCESSO\nDE PESO") - sem re.DOTALL, a busca de 80 caracteres parava
    no fim da 1ª linha e nunca achava "PESO", caindo em "Outros" por
    engano mesmo sendo um Excesso de Peso de verdade."""
    caminho = pdf_fixture("EPSB200007882022.pdf")
    texto = extrair_texto_pagina1(caminho)
    assert identificar_tipo_multa(texto) == "Excesso de Peso"


def test_novo_tipo_evasao_de_pesagem():
    """FRMEV00102002021.pdf: "AUTO DE INFRAÇÃO - EVASÃO DA ÁREA DESTINADA
    A PESAGEM" - tipo genuinamente novo, diferente de "Evasão de Pedágio"
    (que ainda não tem exemplo real)."""
    caminho = pdf_fixture("FRMEV00102002021.pdf")
    texto = extrair_texto_pagina1(caminho)
    assert identificar_tipo_multa(texto) == "Evasão de Pesagem"


def test_novo_tipo_cargas_rntrc():
    """CRGRN00057462022.pdf: "CARGAS - RNTRC" - tipo genuinamente novo
    (irregularidade de Registro Nacional de Transportadores Rodoviários
    de Cargas)."""
    caminho = pdf_fixture("CRGRN00057462022.pdf")
    texto = extrair_texto_pagina1(caminho)
    assert identificar_tipo_multa(texto) == "Cargas - RNTRC"
