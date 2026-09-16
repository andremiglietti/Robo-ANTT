"""
Funções de navegação no portal SIFAMA - Área do Autuado (ANTT).

Cobre a varredura: listar CNPJs (matriz/filiais), buscar processos por CNPJ
e percorrer a tabela de resultados paginada. O download do PDF (clique na
lupa/"Vistas") fica para uma etapa separada (dia 8 do cronograma) - aqui só
lemos a listagem.
"""
from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from robo_antt.config import PAUSA_ENTRE_ACOES_MS, SEL, SESSION_FILE, TIPOS_FISCALIZACAO, VISTAS_URL


class SessaoExpiradaError(Exception):
    """A sessão salva não está mais autenticada - precisa de novo login manual."""


class PortalIndisponivelError(Exception):
    """O portal está fora do ar (ex.: manutenção) - não é problema de sessão,
    só precisa tentar de novo mais tarde. Não sinalizar como se fosse preciso
    logar de novo."""


TEXTO_MANUTENCAO = "Estamos atualizando o sistema"


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


def abrir_tela_processos(page: Page, tentativas: int = 3) -> None:
    """Abre a tela de processos, distinguindo os 3 motivos possíveis de falha:
    sessão expirada, portal fora do ar (manutenção), ou lentidão passageira.

    Achado em 16/09/2026: essa página às vezes demora bem mais que o normal
    pra montar o DOM, e nunca dispara "load"/"networkidle" - por isso usa
    "commit" pra navegar e espera o seletor com um timeout generoso. Também
    achado no mesmo dia: às vezes o portal inteiro está em manutenção
    ("Estamos atualizando o sistema..."), o que não tem nada a ver com a
    sessão - por isso checamos esse texto antes de concluir sessão expirada.
    """
    for tentativa in range(1, tentativas + 1):
        page.goto(VISTAS_URL, wait_until="commit", timeout=60000)
        try:
            page.wait_for_selector(SEL["representado"], state="attached", timeout=30000)
            return  # sucesso
        except PlaywrightTimeoutError:
            if "Login.aspx" in page.url:
                break  # não adianta tentar de novo, sessão realmente expirou
            if TEXTO_MANUTENCAO in page.locator("body").inner_text():
                raise PortalIndisponivelError(
                    "O portal da ANTT está em manutenção agora "
                    f'("{TEXTO_MANUTENCAO}..."). Não é problema de sessão - '
                    "tentar de novo mais tarde."
                )
            # senão, provavelmente só demorou - tenta de novo

    if "Login.aspx" in page.url or page.locator(SEL["representado"]).count() == 0:
        raise SessaoExpiradaError(
            f"Não foi possível acessar a tela de processos depois de {tentativas} tentativas "
            f"(URL atual: {page.url}) - a sessão provavelmente expirou. É preciso refazer o "
            "login manual (scripts/teste_sessao_1_capturar.py)."
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
    preparar_para_clicar(page)
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


def _esperar_modal_processando_sumir(page: Page, timeout: int = 30000) -> None:
    """Espera o modal "Processando..." (#Progress_DivProgress) sumir antes de
    clicar em outra coisa. Achado em 16/09/2026: ele às vezes ainda está na
    tela (bloqueando cliques) quando a próxima ação começa, mesmo depois da
    tabela já ter atualizado - o clique seguinte falha com "elemento
    intercepta o clique" se não esperar isso primeiro.
    """
    try:
        page.wait_for_selector(SEL["modal_processando"], state="hidden", timeout=timeout)
    except PlaywrightTimeoutError:
        pass  # talvez o modal nem exista nessa página nesse momento - segue o jogo


def fechar_modal_confirmacao_download(page: Page, timeout: int = 45000, exigir: bool = False) -> None:
    """Fecha o modal "Vistas ao Processo Solicitada com Sucesso!" que
    aparece DEPOIS de cada download (clique na lupa). Ele fica aberto até
    ser fechado e bloqueia o próximo clique (erro "elemento intercepta o
    clique") - achado ao vivo em 16/09/2026, chamar logo depois de
    baixar_pdf() capturar o download.

    ⚠️ Achado em teste de escala maior (16/09/2026): esse modal pode demorar
    a aparecer tanto quanto qualquer outra resposta desse portal (visto
    levando mais de 15s em alguns casos) - um timeout curto aqui faz a
    função devolver achando que "não apareceu", quando na verdade ele só
    ainda ia aparecer. Se isso acontece, o modal fica aberto e trava TODOS
    os cliques seguintes pelo resto da execução (não só o próximo). Por
    isso: timeout mais generoso, e `baixar_pdf()` também chama essa função
    ANTES de clicar (não só depois) - se um modal ficou pendurado de uma
    chamada anterior por qualquer motivo, a próxima chamada se autocorrige
    em vez de ficar travada pro resto da execução.

    Escolhe "Não Responder" na pesquisa de satisfação antes de clicar Ok -
    o robô não deve interagir com a pesquisa da ANTT, e a opção marcada por
    padrão é "Sim, Responder Agora", que abriria um formulário extra.

    `exigir=True` propaga o timeout em vez de engolir (usado antes do
    clique, onde "não apareceu" é o caminho normal e não deve custar
    `timeout` inteiro de espera toda vez - ver baixar_pdf()).
    """
    try:
        page.wait_for_selector(SEL["modal_confirmacao_download"], state="visible", timeout=timeout if exigir else 2000)
    except PlaywrightTimeoutError:
        return  # não apareceu dessa vez - segue o jogo, não é bloqueante
    if page.locator(SEL["modal_confirmacao_nao_responder"]).count():
        page.check(SEL["modal_confirmacao_nao_responder"])
    page.click(SEL["modal_confirmacao_ok"])
    page.wait_for_selector(SEL["modal_confirmacao_download"], state="hidden", timeout=timeout)


def fechar_modal_mensagem_generica(page: Page, timeout: int = 2000) -> None:
    """Fecha o modal de mensagem genérico do portal (`#divMensagem`) se
    estiver na tela - usado pra erros/avisos do servidor (ex.: visto ao vivo
    em 16/09/2026 associado a alguns downloads que vieram com problema, tipo
    de auto ainda não identificado com certeza). Não sabemos ainda o texto
    exato que aparece dentro - só que ele bloqueia cliques até ser fechado,
    igual aos outros modais.
    """
    try:
        page.wait_for_selector(SEL["modal_mensagem_generica"], state="visible", timeout=timeout)
    except PlaywrightTimeoutError:
        return
    if page.locator(SEL["modal_mensagem_generica_ok"]).count():
        page.click(SEL["modal_mensagem_generica_ok"])
        page.wait_for_selector(SEL["modal_mensagem_generica"], state="hidden", timeout=15000)


def preparar_para_clicar(page: Page) -> None:
    """Espera os modais conhecidos ("Processando...", confirmação de
    download, mensagem genérica) sumirem antes de tentar clicar em algo.
    Chamar antes de qualquer clique que pode ter ficado bloqueado por um
    modal pendurado de uma ação anterior - achado ao vivo em 16/09/2026
    (teste em escala maior): o clique na lupa de `baixar_pdf()` falhava
    travado atrás de um desses modais, às vezes o de uma chamada BEM
    anterior que nunca tinha sido fechada direito. As checagens aqui são
    rápidas quando não há modal nenhum na tela (não atrasa o caso comum).
    """
    _esperar_modal_processando_sumir(page)
    fechar_modal_confirmacao_download(page, exigir=False)
    fechar_modal_mensagem_generica(page)


def _esperar_tabela_mudar(page: Page, valor_anterior: str | None, timeout: int = 30000) -> None:
    """Espera até a 1ª linha da tabela ser diferente de `valor_anterior`, ou
    até aparecer "Nenhum registro encontrado" - detecta o fim do AJAX sem
    depender de wait_for_load_state, que trava nessa página (ver goto acima).

    ⚠️ Achado em 16/09/2026 (confirmado manualmente pelo usuário): o
    paginador do portal (o "X de N") **não reflete a quantidade real de
    resultados** - ele aparece com N fixo mesmo quando não há resultado
    nenhum, ou quando os resultados reais cabem em menos páginas do que N
    sugere. Ou seja, não dá pra confiar em `info_paginacao()` pra saber
    quando parar de paginar - o sinal real é a tabela vir vazia
    ("Nenhum registro encontrado"), e é isso que essa função espera também
    (não só "a linha mudou").
    """
    page.wait_for_function(
        """(args) => {
            const tabela = document.querySelector(args.sel);
            if (!tabela) return false;
            const linhas = tabela.querySelectorAll('tr');
            if (linhas.length === 0) return false;
            // "Nenhum registro encontrado" vem como UMA linha só, sem cabeçalho,
            // com <td colspan="6"> - diferente do caso normal (cabeçalho + linhas de dado)
            if (linhas.length === 1) {
                return !!linhas[0].querySelector('td[colspan]');
            }
            const primeiraCelula = linhas[1].querySelector('td');
            if (!primeiraCelula) return false;
            if (primeiraCelula.hasAttribute('colspan')) return true;
            return primeiraCelula.innerText.trim() !== args.anterior;
        }""",
        arg={"sel": SEL["tabela_resultado"], "anterior": valor_anterior},
        timeout=timeout,
    )
    page.wait_for_timeout(300)


def buscar(page: Page, tentativas: int = 3) -> None:
    """Clica em Pesquisar e espera a tabela terminar de carregar.

    ⚠️ O campo "Tipo de Fiscalização" tem que estar preenchido antes de
    chamar essa função - buscar com ele em branco trava o "Processando..."
    indefinidamente no servidor (testado ao vivo em 16/09/2026, sem resposta
    em 20s+). Por isso varrer_cnpj() itera pelos valores de TIPOS_FISCALIZACAO
    em vez de fazer uma busca só sem filtro.

    ⚠️ O tempo de resposta do portal varia muito (visto entre ~8s e mais de
    30s pra mesma busca, em momentos diferentes - achado em 16/09/2026). Por
    isso, se o primeiro `wait` estourar o timeout, a função **espera de novo**
    (o clique em Pesquisar já foi feito, só continua aguardando a mesma
    resposta) antes de desistir e assumir que a busca não teve resultado -
    assumir "sem resultado" cedo demais faz o robô pular processos de
    verdade.
    """
    preparar_para_clicar(page)
    linha_anterior = _primeira_linha(page)
    page.click(SEL["btn_pesquisar"])
    for tentativa in range(tentativas):
        try:
            _esperar_tabela_mudar(page, linha_anterior)
            return  # sucesso
        except PlaywrightTimeoutError:
            continue  # ainda "Processando..." - espera mais um pouco
    # depois de todas as tentativas, se realmente não veio nada, deixa
    # ler_pagina_atual() confirmar (pode ser busca sem resultado de verdade)
    # em vez de derrubar a varredura inteira por causa de 1 tipo.


def info_paginacao(page: Page) -> tuple[int, int]:
    """Lê o texto tipo '1 de 20' e retorna (pagina_atual, total_paginas)."""
    texto = page.locator(SEL["paginador_info"]).inner_text().strip()
    atual, total = texto.split(" de ")
    return int(atual), int(total)


def ir_proxima_pagina(page: Page) -> None:
    page.wait_for_timeout(PAUSA_ENTRE_ACOES_MS)  # não martelar o portal - ver config.py
    preparar_para_clicar(page)
    linha_anterior = _primeira_linha(page)
    page.click(SEL["paginador_proxima"])
    _esperar_tabela_mudar(page, linha_anterior)


def iterar_paginas_resultado(page: Page):
    """Gerador: percorre a busca atual (já feita, não seleciona nada),
    devolvendo a lista de linhas de CADA página, uma de cada vez. Diferente
    de varrer_busca_atual() (que devolve tudo junto no final), este gerador
    deixa cada linha ainda visível/clicável na tela no momento em que é
    devolvida - necessário pra quem precisa interagir com a linha (ex.:
    baixar_pdf() clicando na lupa) antes de avançar pra próxima página.

    ⚠️ Não confia no "X de N" do paginador pra saber quantas páginas
    percorrer - confirmado com o usuário em 16/09/2026 que esse número **não
    reflete a quantidade real de resultados** (aparece fixo mesmo com 0
    resultados). O sinal real de "acabou" é a próxima página vir vazia.
    """
    pagina = ler_pagina_atual(page)
    if not pagina or page.locator(SEL["paginador_info"]).count() == 0:
        yield pagina  # sem resultado, ou resultado cabe numa página sem paginador
        return

    yield pagina
    pagina_atual, total_paginas = info_paginacao(page)
    while pagina_atual < total_paginas:
        ir_proxima_pagina(page)
        pagina = ler_pagina_atual(page)
        if not pagina:
            break  # "Nenhum registro encontrado" - não tem mais dados de verdade, apesar do paginador
        yield pagina
        pagina_atual, total_paginas = info_paginacao(page)


def varrer_busca_atual(page: Page) -> list[dict]:
    """Lê todas as páginas da busca que já está na tela e devolve tudo numa
    lista só. Ver iterar_paginas_resultado() se for processar cada linha
    ainda com ela na tela (ex.: baixar o PDF)."""
    todos: list[dict] = []
    for pagina in iterar_paginas_resultado(page):
        todos.extend(pagina)
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
        page.wait_for_timeout(PAUSA_ENTRE_ACOES_MS)  # não martelar o portal - ver config.py
        selecionar_tipo_fiscalizacao(page, tipo_value)
        buscar(page)
        resultados = varrer_busca_atual(page)
        for row in resultados:
            row["cnpj"] = cnpj_value
            row["tipo_fiscalizacao_busca"] = tipo_nome
        todos.extend(resultados)
    return todos
