"""
Testes de portal.py - achado na revisão crítica de 24/09/2026: 511 linhas,
zero testes dedicados, apesar de já ter causado vários bugs reais em
produção (paginador não confiável, modais travando cliques, seleção de
CNPJ silenciosamente errada - ver CLAUDE.md).

Usa `page.set_content()` (fixture `page`, ver conftest.py) pra carregar
HTML sintético que imita a estrutura real do portal (baseada no outerHTML
capturado em codigos_site/) - testa a lógica de parsing/seleção de verdade
contra um `Page` real do Playwright, sem precisar de sessão nem tocar no
portal. Cobre só as funções que dependem apenas do DOM (não de postback
AJAX real do servidor, que não dá pra simular localmente).
"""
from robo_antt.portal import info_paginacao, ler_pagina_atual, listar_cnpjs

_TABELA_COM_DADOS = """
<table id="Corpo_gdvResultado">
  <tr><th>Auto</th><th>Processo</th><th>Autuado</th><th>Situação</th><th>Data</th><th>Ação</th></tr>
  <tr>
    <td>EPSMA00087472019</td>
    <td>12345.678901/2019-00</td>
    <td>YARA BRASIL FERTILIZANTES S/A</td>
    <td>Arquivado - Pago</td>
    <td>01/01/2019</td>
    <td><input type="image" id="Corpo_gdvResultado_btnVisualizar_0"/></td>
  </tr>
  <tr>
    <td>CRGTF00018212019</td>
    <td>12345.678902/2019-00</td>
    <td>YARA BRASIL FERTILIZANTES S/A</td>
    <td>Notificado</td>
    <td>02/02/2019</td>
    <td><input type="image" id="Corpo_gdvResultado_btnVisualizar_1"/></td>
  </tr>
</table>
"""

_TABELA_VAZIA = """
<table id="Corpo_gdvResultado">
  <tr><td colspan="6">Nenhum registro encontrado.</td></tr>
</table>
"""


def test_ler_pagina_atual_extrai_campos_e_pula_cabecalho(page):
    page.set_content(_TABELA_COM_DADOS)
    linhas = ler_pagina_atual(page)
    assert len(linhas) == 2
    assert linhas[0] == {
        "auto_infracao": "EPSMA00087472019",
        "numero_processo": "12345.678901/2019-00",
        "autuado": "YARA BRASIL FERTILIZANTES S/A",
        "situacao": "Arquivado - Pago",
        "data_auto": "01/01/2019",
    }
    assert linhas[1]["auto_infracao"] == "CRGTF00018212019"


def test_ler_pagina_atual_tabela_nenhum_registro_devolve_lista_vazia(page):
    page.set_content(_TABELA_VAZIA)
    assert ler_pagina_atual(page) == []


def test_ler_pagina_atual_sem_tabela_no_dom_devolve_lista_vazia(page):
    page.set_content("<html><body><p>sem tabela nenhuma aqui</p></body></html>")
    assert ler_pagina_atual(page) == []


def test_info_paginacao_parseia_pagina_atual_e_total(page):
    page.set_content(
        """
        <ul id="Corpo_ucPaginadorResultado">
          <li class="info">3 de 20</li>
        </ul>
        """
    )
    assert info_paginacao(page) == (3, 20)


def test_listar_cnpjs_ignora_opcao_selecione_e_devolve_indice_real(page):
    page.set_content(
        """
        <select id="Corpo_ddlRepresentado">
          <option value="">Selecione</option>
          <option value="92660604000182">92.660.604/0001-82 - YARA BRASIL FERTILIZANTES S/A</option>
          <option value="92660604000263">92.660.604/0002-63 - YARA BRASIL FERTILIZANTES S/A FILIAL</option>
        </select>
        """
    )
    cnpjs = listar_cnpjs(page)
    assert cnpjs == [
        {"value": "92660604000182", "texto": "92.660.604/0001-82 - YARA BRASIL FERTILIZANTES S/A", "indice": 1},
        {"value": "92660604000263", "texto": "92.660.604/0002-63 - YARA BRASIL FERTILIZANTES S/A FILIAL", "indice": 2},
    ]


def test_listar_cnpjs_devolve_lista_vazia_se_so_tiver_a_opcao_selecione(page):
    page.set_content('<select id="Corpo_ddlRepresentado"><option value="">Selecione</option></select>')
    assert listar_cnpjs(page) == []
