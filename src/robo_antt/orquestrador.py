"""
Orquestrador principal do robô: liga varredura, download, extração de
campos e planilha, com checkpoint entre execuções (ver CLAUDE.md, item 6
da arquitetura).

Fluxo por CNPJ, por tipo de fiscalização, por página de resultado:
  seleciona CNPJ -> seleciona tipo -> busca -> pra cada linha da página
  (ainda visível na tela): já processado? pula. Senão: baixa o PDF, extrai
  os campos, adiciona na planilha (se ainda não tiver essa linha),
  marca como processado no checkpoint -> próxima página -> próximo tipo ->
  próximo CNPJ. Salva a planilha e o checkpoint a cada CNPJ concluído (não
  só no final), pra não perder o progresso se algo interromper no meio de
  uma varredura longa (pode levar horas pra empresa toda - ver CLAUDE.md).
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

from robo_antt import checkpoint
from robo_antt.config import OUTPUT_DIR, TIPOS_FISCALIZACAO
from robo_antt.download import baixar_pdf
from robo_antt.extracao import (
    extrair_campos_pagina1,
    extrair_campos_boleto,
    extrair_data_emissao_notificacao,
    extrair_texto_pagina1,
    identificar_tipo_multa,
    localizar_pagina_boleto,
    localizar_pagina_notificacao,
)
from robo_antt.planilha import abrir_ou_criar, adicionar_registro, ja_registrado, salvar as salvar_planilha
from robo_antt.portal import (
    PortalIndisponivelError,
    SessaoExpiradaError,
    abrir_contexto,
    abrir_tela_processos,
    iterar_paginas_resultado,
    listar_cnpjs,
    selecionar_cnpj,
    selecionar_tipo_fiscalizacao,
    buscar,
)

PLANILHA_PATH = OUTPUT_DIR / "relatorio_multas.xlsx"


def extrair_todos_campos(caminho_pdf: Path) -> dict:
    """Roda a extração completa (página 1 + boleto + notificação, se
    existirem) e devolve um dict só, pronto pra virar uma linha da planilha
    (ver src/robo_antt/planilha.py)."""
    texto1 = extrair_texto_pagina1(caminho_pdf)
    campos = {"tipo_multa": identificar_tipo_multa(texto1)}
    campos.update(extrair_campos_pagina1(caminho_pdf))

    pagina_boleto = localizar_pagina_boleto(caminho_pdf)
    if pagina_boleto:
        campos.update(extrair_campos_boleto(caminho_pdf, pagina_boleto))

    pagina_notif = localizar_pagina_notificacao(caminho_pdf)
    if pagina_notif:
        campos["data_emissao_notificacao"] = extrair_data_emissao_notificacao(caminho_pdf, pagina_notif)

    return campos


def processar_linha(page, row: dict, estado: dict, wb) -> None:
    """Baixa (se precisar) e extrai os campos de 1 auto, e adiciona na
    planilha se ainda não estiver lá. Marca sucesso/falha no checkpoint -
    falha aqui é sempre de UM documento específico (PDF ilegível, campo que
    não bateu com nenhum padrão conhecido etc.), não de sessão/portal (essas
    sobem como exceção e param a execução inteira, ver rodar())."""
    auto = row["auto_infracao"]
    if checkpoint.ja_processado(estado, auto):
        return

    try:
        caminho_pdf = baixar_pdf(page, auto, row["cnpj"])
        campos = extrair_todos_campos(caminho_pdf)
        registro = {
            "link_arquivo": str(caminho_pdf),
            "numero_processo": row["numero_processo"],
            "auto_infracao": auto,
            "cnpj": row["cnpj"],
            **campos,
        }
        if not ja_registrado(wb, auto):
            adicionar_registro(wb, registro)
        checkpoint.marcar_processado(estado, auto)
    except (SessaoExpiradaError, PortalIndisponivelError):
        raise  # falha de infraestrutura - não é do documento, para tudo (ver rodar())
    except Exception as e:  # falha real deste documento - registra e segue pros próximos
        checkpoint.marcar_falha(estado, auto, str(e))
        print(f"    [FALHA] {auto}: {e}")


def processar_cnpj(page, cnpj: dict, estado: dict, wb, tipos: dict = TIPOS_FISCALIZACAO) -> int:
    """Varre um CNPJ por todos os tipos de fiscalização informados,
    processando (baixando/extraindo/registrando) cada linha encontrada.
    Devolve quantos autos novos foram processados com sucesso."""
    selecionar_cnpj(page, cnpj["indice"])
    processados_antes = len(estado["processados"])

    for tipo_value, tipo_nome in tipos.items():
        page.wait_for_timeout(2000)  # não martelar o portal - ver PAUSA_ENTRE_ACOES_MS em config.py
        try:
            selecionar_tipo_fiscalizacao(page, tipo_value)
            buscar(page)
            for pagina in iterar_paginas_resultado(page):
                for row in pagina:
                    row["cnpj"] = cnpj["value"]
                    processar_linha(page, row, estado, wb)
        except (SessaoExpiradaError, PortalIndisponivelError):
            raise  # falha de infraestrutura - para tudo (ver rodar())
        except Exception as e:
            # falha ao navegar (busca ou paginação) pra ESSE tipo específico -
            # não é culpa de nenhum documento em particular pra marcar no
            # checkpoint, mas também não deveria derrubar a varredura inteira -
            # loga e segue pro próximo tipo/CNPJ (achado ao vivo em 16/09/2026:
            # um clique de paginação falhou por causa do modal de confirmação
            # do download anterior ainda aberto - já corrigido, mas mantém essa
            # rede de segurança pra outras falhas de navegação imprevistas).
            print(f"    [FALHA NAVEGAÇÃO] {cnpj['texto']} / {tipo_nome}: {e}")

    return len(estado["processados"]) - processados_antes


def rodar(limite_cnpjs: int | None = None, tipos: dict = TIPOS_FISCALIZACAO) -> None:
    """Ponto de entrada principal. `limite_cnpjs` e `tipos` existem pra
    facilitar testar com um escopo pequeno antes de rodar a empresa toda
    (que pode levar ~2,5-3h - ver CLAUDE.md)."""
    estado = checkpoint.carregar()
    wb = abrir_ou_criar(PLANILHA_PATH)

    with sync_playwright() as p:
        browser, context, page = abrir_contexto(p, headless=True)
        try:
            abrir_tela_processos(page)
            cnpjs = listar_cnpjs(page)
            if limite_cnpjs:
                cnpjs = cnpjs[:limite_cnpjs]

            for cnpj in cnpjs:
                print(f"Varrendo {cnpj['texto']}...")
                novos = processar_cnpj(page, cnpj, estado, wb, tipos)
                print(f"  {novos} auto(s) novo(s) processado(s).")
                # salva a cada CNPJ concluído - uma varredura completa pode
                # levar horas, não queremos perder tudo se algo interromper
                salvar_planilha(wb, PLANILHA_PATH)
                checkpoint.salvar(estado)

        except (SessaoExpiradaError, PortalIndisponivelError) as e:
            print(f"\n[PAROU] {e}")
        finally:
            salvar_planilha(wb, PLANILHA_PATH)
            checkpoint.salvar(estado)
            browser.close()

    print(f"\nPlanilha: {PLANILHA_PATH}")
    print(f"Processados no total (histórico completo): {len(estado['processados'])}")
    if estado["falhas"]:
        print(f"Falhas pendentes: {len(estado['falhas'])} (ver {checkpoint.CHECKPOINT_FILE})")


if __name__ == "__main__":
    rodar()
