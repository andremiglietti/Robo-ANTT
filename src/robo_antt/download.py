"""
Download do PDF do auto de infração (clique na lupa/"Vistas" da tabela de
resultados) e organização em pastas por CNPJ + tipo de multa.

Pré-requisito: a linha do auto precisa estar visível na tabela de resultados
da página atual (chamar logo depois de ler a página com portal.py, antes de
paginar pra frente).
"""
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from robo_antt.config import DOWNLOAD_DIR, SEL
from robo_antt.extracao import extrair_texto_pagina1, identificar_tipo_multa
from robo_antt.portal import fechar_modal_confirmacao_download, preparar_para_clicar


class TabelaInvalidadaError(Exception):
    """A tabela de resultados foi resetada/invalidada no meio do
    processamento de uma página (mostra só "Nenhum registro encontrado"
    onde antes tinha linhas de verdade) - ver _localizar_linha().

    Diferente de uma falha de UM documento específico: se a tabela está
    vazia, TODAS as linhas restantes da página vão falhar exatamente do
    mesmo jeito - não é útil (nem rápido) tentar cada uma individualmente.
    Por isso essa exceção NÃO é tratada como falha de documento em
    processar_linha() - propaga até _tentar_tipo(), que marca o tipo
    inteiro como incompleto (pra retentar do zero) e para de processar o
    resto da página imediatamente.
    """


def _mensagem_tabela_vazia(page: Page) -> str | None:
    """Devolve o texto se a tabela agora mostra só 'Nenhum registro
    encontrado' (1 linha só, com colspan - ver _esperar_tabela_mudar() em
    portal.py), ou None se tem conteúdo de verdade."""
    todas = page.locator(f'{SEL["tabela_resultado"]} tr')
    if todas.count() != 1:
        return None
    texto = todas.first.inner_text().strip()
    if todas.first.locator("td[colspan]").count():
        return texto
    return None


def _localizar_linha(page: Page, auto_infracao: str, tentativas: int = 3):
    """Espera a linha desse auto aparecer na tabela antes de tentar clicar.

    ⚠️ Achado ao vivo em 17/09/2026 (teste de 3 workers em paralelo): ~50
    tentativas SEGUIDAS falharam com "Locator.click: Timeout 30000ms
    exceeded" sem NENHUM log de tentativa de clique (diferente do bug do
    `no_wait_after` corrigido antes, que mostrava "click action done" antes
    de travar) - ou seja, a linha simplesmente não estava na tabela no
    momento do clique. Em vez de deixar o `.click()` estourar 30s inteiros
    sem nenhum diagnóstico, espera a linha explicitamente (com retentativa
    curta).

    ⚠️ Achado ao vivo em 18/09/2026: se depois de esperar a linha ainda não
    aparecer, e a tabela agora mostra só "Nenhum registro encontrado", isso
    NÃO é uma falha desse documento específico - é sinal de que a busca
    inteira foi invalidada no meio (o próprio usuário notou isso revendo o
    log: "você está considerando 'Nenhum registro encontrado' como erro?").
    Levanta TabelaInvalidadaError nesse caso (tratada à parte, ver acima),
    em vez do ValueError genérico usado quando a tabela ainda tem conteúdo
    mas só essa linha específica sumiu (aí sim pode ser um problema real
    só desse documento).
    """
    linha = page.locator(f'{SEL["tabela_resultado"]} tr', has_text=auto_infracao)
    for _ in range(tentativas):
        try:
            linha.first.wait_for(state="visible", timeout=5000)
            return linha
        except PlaywrightTimeoutError:
            continue

    vazia = _mensagem_tabela_vazia(page)
    if vazia:
        raise TabelaInvalidadaError(
            f"A tabela foi invalidada no meio do processamento (mostra '{vazia}' agora, "
            f"onde antes tinha linhas de verdade) - parando de tentar o resto desta página."
        )

    todas = page.locator(f'{SEL["tabela_resultado"]} tr')
    total = todas.count()
    amostra = [todas.nth(i).inner_text().replace("\n", " | ") for i in range(min(total, 3))]
    raise ValueError(
        f"A linha do auto {auto_infracao} não apareceu na tabela depois de {tentativas} tentativas "
        f"(a tela tem {total} linha(s) agora; primeiras: {amostra})"
    )


def _eh_pdf_valido(caminho: Path) -> bool:
    with open(caminho, "rb") as f:
        return f.read(5) == b"%PDF-"


def already_downloaded(auto_infracao: str, cnpj: str) -> Path | None:
    """Procura se esse auto já foi baixado antes (em qualquer pasta de tipo -
    o tipo só é conhecido depois de abrir o PDF, ver identificar_tipo_multa).
    Controle de duplicidade simples baseado no nome do arquivo (ver CLAUDE.md,
    item 4 da arquitetura: o PDF já baixa com o nome do número do auto).
    """
    pasta_cnpj = DOWNLOAD_DIR / cnpj
    if not pasta_cnpj.exists():
        return None
    encontrados = list(pasta_cnpj.glob(f"*/{auto_infracao}.pdf"))
    return encontrados[0] if encontrados else None


def baixar_pdf(page: Page, auto_infracao: str, cnpj: str) -> Path:
    """Baixa o PDF de um auto (clicando na lupa da linha correspondente, que
    precisa estar na página atual) e salva em
    data/downloads/{cnpj}/{tipo_multa}/{auto_infracao}.pdf.

    O "tipo_multa" da pasta vem do cabeçalho da própria página 1 do PDF (mais
    granular que o filtro de busca "Tipo de Fiscalização" - ver CLAUDE.md,
    item 5 da arquitetura), então só dá pra saber o caminho final depois de
    baixar - por isso primeiro salva num arquivo temporário.
    """
    existente = already_downloaded(auto_infracao, cnpj)
    if existente:
        return existente

    # se um modal ficou pendurado de uma chamada anterior (achado ao vivo em
    # 16/09/2026, teste em escala maior - ver preparar_para_clicar()), fecha
    # antes de tentar clicar/esperar a linha, senão os dois ficam travados
    # atrás dele.
    preparar_para_clicar(page)
    linha = _localizar_linha(page, auto_infracao)
    botao_visualizar = linha.locator('input[type="image"]')

    # no_wait_after=True: esse clique dispara um DOWNLOAD, não uma navegação
    # de página - sem isso, o .click() fica esperando por uma "navegação"
    # que nunca conclui do jeito que ele espera, e trava até estourar os 30s
    # de timeout (achado ao vivo em 17/09/2026, teste de amplitude: 55 de
    # ~110 tentativas falharam exatamente com esse padrão - "click action
    # done" seguido de "waiting for scheduled navigations to finish" até
    # expirar). O download em si já é capturado por expect_download() logo
    # abaixo, então não precisamos que o click espere por mais nada.
    with page.expect_download(timeout=60000) as download_info:
        botao_visualizar.click(no_wait_after=True)
    download = download_info.value

    # o portal abre um modal de confirmação depois do download que fica
    # bloqueando a tela até ser fechado - achado ao vivo em 16/09/2026
    fechar_modal_confirmacao_download(page, exigir=True)

    # escreve em arquivo temporário primeiro, só depois move pro destino final
    # com o tipo já identificado - mesmo cuidado da gravação na pasta do
    # SharePoint (ver CLAUDE.md, "Cuidado técnico na gravação"), pra nunca
    # deixar um arquivo parcial/incompleto num nome final.
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destino_tmp = DOWNLOAD_DIR / f"_tmp_{auto_infracao}.pdf"
    download.save_as(str(destino_tmp))

    # Achado ao vivo em 16/09/2026 (teste em escala maior): pra alguns
    # autos (motivo ainda não identificado - visto em processos mais antigos
    # com prefixos de auto nunca vistos antes, ex. EPSB2/EPSC1/EPSC2) o
    # "download" capturado pelo Playwright não é um PDF de verdade, é a
    # própria página HTML do portal. Sem essa checagem, esse HTML seria
    # salvo com nome de PDF e corromperia silenciosamente o resultado -
    # melhor falhar esse documento específico (fica registrado no
    # checkpoint pra revisão manual) do que entregar um arquivo errado.
    if not _eh_pdf_valido(destino_tmp):
        destino_tmp.unlink(missing_ok=True)
        raise ValueError(
            f"O download de {auto_infracao} não é um PDF de verdade (o portal "
            "devolveu outro conteúdo, provavelmente uma página HTML de erro)."
        )

    texto_pagina1 = extrair_texto_pagina1(destino_tmp)
    tipo_multa = identificar_tipo_multa(texto_pagina1)

    destino_final = DOWNLOAD_DIR / cnpj / tipo_multa / f"{auto_infracao}.pdf"
    destino_final.parent.mkdir(parents=True, exist_ok=True)
    destino_tmp.replace(destino_final)

    return destino_final
