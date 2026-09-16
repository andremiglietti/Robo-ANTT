"""
Funções de navegação no portal SIFAMA - Área do Autuado (ANTT).

Cobre a varredura: listar CNPJs (matriz/filiais), buscar processos por CNPJ
e percorrer a tabela de resultados paginada. O download do PDF (clique na
lupa/"Vistas") fica para uma etapa separada (dia 8 do cronograma) - aqui só
lemos a listagem.
"""
from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from robo_antt.config import SEL, SESSION_FILE, TIPOS_FISCALIZACAO, VISTAS_URL


class SessaoExpiradaError(Exception):
    """A sessão salva não está mais autenticada - precisa de novo login manual."""


def abrir_contexto(playwright, headless: bool = True) -> tuple:
    if not SESSION_FILE.exists():
        raise FileNotFoundError(
            f"Sessão não encontrada em {SESSION_FILE}. "
            "Rode scripts/teste_sessao_1_capturar.py para gerar uma sessão válida."
        )
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(storage_state=str(SESSION_FILE))
    page = context.new_page()
    return browser, context, page


def abrir_tela_processos(page: Page) -> None:
    # "commit" (não "load"/"networkidle") porque a página tem alguma requisição
    # de fundo que não termina nunca - com "load" o goto trava até estourar o
    # timeout, mesmo a página já estando pronta pra uso (descoberto em 16/09/2026).
    page.goto(VISTAS_URL, wait_until="commit", timeout=60000)
    try:
        page.wait_for_selector(SEL["representado"], state="attached", timeout=30000)
    except PlaywrightTimeoutError:
        pass
    # O sinal confiável de sessão expirada é o REDIRECT pra Login.aspx - checar
    # só a ausência do seletor dá falso positivo (a página às vezes demora um
    # pouco mais que o timeout pra montar o DOM, mesmo com sessão válida;
    # descoberto ao vivo em 16/09/2026).
    if "Login.aspx" in page.url or page.locator(SEL["representado"]).count() == 0:
        raise SessaoExpiradaError(
            f"Não foi possível acessar a tela de processos (URL atual: {page.url}) - "
            "a sessão provavelmente expirou. É preciso refazer o login manual "
            "(scripts/teste_sessao_1_capturar.py)."
        )


def listar_cnpjs(page: Page) -> list[dict]:
    """Retorna [{"value": "92660604000182", "texto": "92.660.604/0001-82 - YARA ...", "indice": 1}].

    "indice" é a posição da <option> dentro do <select> (0 = "Selecione"), que
    corresponde ao atributo data-option-array-index dos <li> do chosen.js -
    é o que selecionar_cnpj() usa pra clicar na opção certa.
    """
    opcoes = page.locator(f'{SEL["representado"]} option').all()
    cnpjs = []
    for indice, opcao in enumerate(opcoes):
        valor = opcao.get_attribute("value")
        texto = opcao.inner_text().strip()
        if valor:  # ignora a opção em branco "Selecione" (índice 0)
            cnpjs.append({"value": valor, "texto": texto, "indice": indice})
    return cnpjs


def selecionar_cnpj(page: Page, indice: int) -> None:
    """Seleciona um CNPJ pelo índice (ver listar_cnpjs).

    O <select> real fica oculto (display:none) porque o portal usa o plugin
    chosen.js pra desenhar o dropdown visível (o com campo de busca, visto
    nos prints). Setar o <select> direto via JS/force=True NÃO funciona: o
    widget do chosen.js fica com o texto antigo ("Selecione") e a busca
    subsequente trava (testado ao vivo em 16/09/2026). Por isso aqui a gente
    interage com o widget visível, igual um humano faria: clica pra abrir e
    clica na opção certa pelo data-option-array-index.
    """
    page.click(SEL["representado_chosen"])
    page.click(f'{SEL["representado_chosen"]} li[data-option-array-index="{indice}"]')
    page.wait_for_timeout(300)


def selecionar_tipo_fiscalizacao(page: Page, tipo_value: str) -> None:
    # Ao contrário do Representado, esse <select> NÃO é escondido pelo
    # chosen.js (confirmado no outerHTML capturado) - select_option normal
    # funciona direto, sem nenhum truque.
    page.select_option(SEL["tipo_fiscalizacao"], value=tipo_value)


def ler_pagina_atual(page: Page) -> list[dict]:
    """Lê as linhas da tabela de resultados já carregada na página atual."""
    if page.locator(SEL["tabela_resultado"]).count() == 0:
        return []
    linhas = page.locator(f'{SEL["tabela_resultado"]} tr').all()
    resultados = []
    for linha in linhas:
        celulas = linha.locator("td").all()
        if len(celulas) < 5:
            continue  # pula a linha de cabeçalho (usa <th>, não <td>)
        resultados.append(
            {
                "auto_infracao": celulas[0].inner_text().strip(),
                "numero_processo": celulas[1].inner_text().strip(),
                "autuado": celulas[2].inner_text().strip(),
                "situacao": celulas[3].inner_text().strip(),
                "data_auto": celulas[4].inner_text().strip(),
            }
        )
    return resultados


def _primeira_linha(page: Page) -> str | None:
    atual = ler_pagina_atual(page)
    return atual[0]["auto_infracao"] if atual else None


def _esperar_tabela_mudar(page: Page, valor_anterior: str | None, timeout: int = 30000) -> None:
    """Espera até a 1ª linha da tabela ser diferente de `valor_anterior` (ou a
    tabela aparecer, se ela ainda não existia) - detecta o fim do AJAX sem
    depender de wait_for_load_state, que trava nessa página (ver goto acima).
    """
    page.wait_for_function(
        """(args) => {
            const tabela = document.querySelector(args.sel);
            if (!tabela) return false;
            const linhas = tabela.querySelectorAll('tr');
            if (linhas.length < 2) return false;
            const primeiraCelula = linhas[1].querySelector('td');
            return primeiraCelula && primeiraCelula.innerText.trim() !== args.anterior;
        }""",
        arg={"sel": SEL["tabela_resultado"], "anterior": valor_anterior},
        timeout=timeout,
    )
    page.wait_for_timeout(300)


def buscar(page: Page) -> None:
    """Clica em Pesquisar e espera a tabela terminar de carregar.

    ⚠️ O campo "Tipo de Fiscalização" tem que estar preenchido antes de
    chamar essa função - buscar com ele em branco trava o "Processando..."
    indefinidamente no servidor (testado ao vivo em 16/09/2026, sem resposta
    em 20s+). Por isso varrer_cnpj() itera pelos valores de TIPOS_FISCALIZACAO
    em vez de fazer uma busca só sem filtro.
    """
    linha_anterior = _primeira_linha(page)
    page.click(SEL["btn_pesquisar"])
    try:
        _esperar_tabela_mudar(page, linha_anterior)
    except PlaywrightTimeoutError:
        # provavelmente essa busca não teve nenhum resultado (a tabela nem
        # chega a aparecer nesse caso) - deixa ler_pagina_atual() confirmar,
        # em vez de derrubar a varredura inteira por causa de 1 tipo vazio.
        pass


def info_paginacao(page: Page) -> tuple[int, int]:
    """Lê o texto tipo '1 de 20' e retorna (pagina_atual, total_paginas)."""
    texto = page.locator(SEL["paginador_info"]).inner_text().strip()
    atual, total = texto.split(" de ")
    return int(atual), int(total)


def ir_proxima_pagina(page: Page) -> None:
    linha_anterior = _primeira_linha(page)
    page.click(SEL["paginador_proxima"])
    _esperar_tabela_mudar(page, linha_anterior)


def varrer_busca_atual(page: Page) -> list[dict]:
    """Lê todas as páginas da busca que já está na tela (não seleciona nada)."""
    todos = ler_pagina_atual(page)
    if not todos or page.locator(SEL["paginador_info"]).count() == 0:
        return todos  # sem resultado, ou resultado cabe numa página sem paginador

    pagina_atual, total_paginas = info_paginacao(page)
    while pagina_atual < total_paginas:
        ir_proxima_pagina(page)
        todos.extend(ler_pagina_atual(page))
        pagina_atual, total_paginas = info_paginacao(page)
    return todos


def varrer_cnpj(page: Page, cnpj_indice: int, cnpj_value: str) -> list[dict]:
    """Busca todos os processos de um CNPJ, iterando por TODOS os tipos de
    fiscalização (ver TIPOS_FISCALIZACAO) e todas as páginas de cada um.

    Não dá pra buscar com "Tipo de Fiscalização" em branco - trava no
    servidor (ver docstring de buscar()). Por isso iteramos um tipo de cada
    vez; o "Tipo de Multa" de cada linha aqui é o filtro usado na busca, mas
    o valor definitivo pra planilha final vem do cabeçalho da página 1 do
    PDF (mais granular - ver CLAUDE.md, item 5 da arquitetura).
    """
    selecionar_cnpj(page, cnpj_indice)

    todos = []
    for tipo_value, tipo_nome in TIPOS_FISCALIZACAO.items():
        selecionar_tipo_fiscalizacao(page, tipo_value)
        buscar(page)
        resultados = varrer_busca_atual(page)
        for row in resultados:
            row["cnpj"] = cnpj_value
            row["tipo_fiscalizacao_busca"] = tipo_nome
        todos.extend(resultados)
    return todos
