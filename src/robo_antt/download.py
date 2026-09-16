"""
Download do PDF do auto de infração (clique na lupa/"Vistas" da tabela de
resultados) e organização em pastas por CNPJ + tipo de multa.

Pré-requisito: a linha do auto precisa estar visível na tabela de resultados
da página atual (chamar logo depois de ler a página com portal.py, antes de
paginar pra frente).
"""
from pathlib import Path

from playwright.sync_api import Page

from robo_antt.config import DOWNLOAD_DIR, SEL
from robo_antt.extracao import extrair_texto_pagina1, identificar_tipo_multa
from robo_antt.portal import fechar_modal_confirmacao_download


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

    linha = page.locator(f'{SEL["tabela_resultado"]} tr', has_text=auto_infracao)
    botao_visualizar = linha.locator('input[type="image"]')

    with page.expect_download(timeout=60000) as download_info:
        botao_visualizar.click()
    download = download_info.value

    # o portal abre um modal de confirmação depois do download que fica
    # bloqueando a tela até ser fechado - achado ao vivo em 16/09/2026
    fechar_modal_confirmacao_download(page)

    # escreve em arquivo temporário primeiro, só depois move pro destino final
    # com o tipo já identificado - mesmo cuidado da gravação na pasta do
    # SharePoint (ver CLAUDE.md, "Cuidado técnico na gravação"), pra nunca
    # deixar um arquivo parcial/incompleto num nome final.
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destino_tmp = DOWNLOAD_DIR / f"_tmp_{auto_infracao}.pdf"
    download.save_as(str(destino_tmp))

    texto_pagina1 = extrair_texto_pagina1(destino_tmp)
    tipo_multa = identificar_tipo_multa(texto_pagina1)

    destino_final = DOWNLOAD_DIR / cnpj / tipo_multa / f"{auto_infracao}.pdf"
    destino_final.parent.mkdir(parents=True, exist_ok=True)
    destino_tmp.replace(destino_final)

    return destino_final
