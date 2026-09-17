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

Acompanhamento visual (17/09/2026): todo print aqui usa flush=True e mostra
"CNPJ X/N" e "Tipo Y/7" - dá pra acompanhar ao vivo rodando no terminal, ou
ler os logs depois (nenhuma informação de progresso fica só numa tela que
se apaga).
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from robo_antt import checkpoint
from robo_antt.config import PLANILHA_PATH, TIPOS_FISCALIZACAO
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


def _log(msg: str) -> None:
    """print com flush - sem isso, rodando em segundo plano/redirecionado
    pra arquivo, as linhas só apareciam depois que o processo inteiro
    terminava (achado ao vivo em 16/09/2026), o que inutiliza qualquer
    acompanhamento em tempo real."""
    print(msg, flush=True)


def _formatar_duracao(segundos: float) -> str:
    minutos, seg = divmod(int(segundos), 60)
    horas, minutos = divmod(minutos, 60)
    if horas:
        return f"{horas}h{minutos:02d}m{seg:02d}s"
    if minutos:
        return f"{minutos}m{seg:02d}s"
    return f"{seg}s"


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


def processar_linha(page, row: dict, estado: dict, wb, prefixo: str = "") -> str:
    """Baixa (se precisar) e extrai os campos de 1 auto, e adiciona na
    planilha se ainda não estiver lá. Marca sucesso/falha no checkpoint -
    falha aqui é sempre de UM documento específico (PDF ilegível, campo que
    não bateu com nenhum padrão conhecido etc.), não de sessão/portal (essas
    sobem como exceção e param a execução inteira, ver rodar()).

    Devolve "novo", "conhecido" ou "falha" - usado por processar_cnpj() pra
    montar o resumo de progresso.
    """
    auto = row["auto_infracao"]
    if checkpoint.ja_processado(estado, auto):
        return "conhecido"  # não printa - CNPJs com muito histórico já conhecido ficariam poluídos de linha

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
        _log(f"{prefixo} {auto} -> novo ({campos.get('tipo_multa', '?')})")
        return "novo"
    except (SessaoExpiradaError, PortalIndisponivelError):
        raise  # falha de infraestrutura - não é do documento, para tudo (ver rodar())
    except Exception as e:  # falha real deste documento - registra e segue pros próximos
        checkpoint.marcar_falha(estado, auto, str(e))
        _log(f"{prefixo} {auto} -> FALHA: {e}")
        return "falha"


def processar_cnpj(
    page,
    cnpj: dict,
    estado: dict,
    wb,
    tipos: dict = TIPOS_FISCALIZACAO,
    indice_cnpj: int = 1,
    total_cnpjs: int = 1,
) -> tuple[int, int]:
    """Varre um CNPJ por todos os tipos de fiscalização informados,
    processando (baixando/extraindo/registrando) cada linha encontrada.
    Devolve (autos novos processados com sucesso, falhas ocorridas nesta
    chamada) - falhas aqui conta o que ACONTECEU nesta execução, não é o
    mesmo que `len(estado["falhas"])` no final (esse é só o número de falhas
    ainda PENDENTES no checkpoint, que pode até diminuir numa execução se
    falhas antigas forem resolvidas com sucesso - ver checkpoint.marcar_processado()).

    `indice_cnpj`/`total_cnpjs` são só pra exibir "CNPJ X/N" no progresso -
    não mudam o comportamento.
    """
    selecionar_cnpj(page, cnpj["indice"])
    processados_antes = len(estado["processados"])
    total_tipos = len(tipos)
    falhas_cnpj = 0

    for indice_tipo, (tipo_value, tipo_nome) in enumerate(tipos.items(), start=1):
        prefixo = f"  [CNPJ {indice_cnpj}/{total_cnpjs} | Tipo {indice_tipo}/{total_tipos}: {tipo_nome}]"
        page.wait_for_timeout(2000)  # não martelar o portal - ver PAUSA_ENTRE_ACOES_MS em config.py
        try:
            selecionar_tipo_fiscalizacao(page, tipo_value)
            buscar(page)
            total_linhas = 0
            novos = 0
            falhas = 0
            for pagina in iterar_paginas_resultado(page):
                for row in pagina:
                    total_linhas += 1
                    row["cnpj"] = cnpj["value"]
                    resultado = processar_linha(page, row, estado, wb, prefixo)
                    if resultado == "novo":
                        novos += 1
                    elif resultado == "falha":
                        falhas += 1
            falhas_cnpj += falhas
            if total_linhas:
                _log(
                    f"{prefixo} concluído: {total_linhas} processo(s) na tela "
                    f"({novos} novo(s), {falhas} falha(s), resto já conhecido)"
                )
            else:
                _log(f"{prefixo} sem processos")
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
            _log(f"{prefixo} [FALHA NAVEGAÇÃO] {e}")

    return len(estado["processados"]) - processados_antes, falhas_cnpj


def rodar(limite_cnpjs: int | None = None, tipos: dict = TIPOS_FISCALIZACAO) -> None:
    """Ponto de entrada principal. `limite_cnpjs` e `tipos` existem pra
    facilitar testar com um escopo pequeno antes de rodar a empresa toda
    (que pode levar horas - ver "achados" no CLAUDE.md sobre volume real)."""
    inicio = time.time()
    estado = checkpoint.carregar()
    wb = abrir_ou_criar(PLANILHA_PATH)
    processados_no_inicio = len(estado["processados"])
    falhas_ocorridas = 0  # falhas que ACONTECERAM nesta execução (não confundir com len(estado["falhas"]) - ver processar_cnpj())

    with sync_playwright() as p:
        browser, context, page = abrir_contexto(p, headless=True)
        try:
            abrir_tela_processos(page)
            cnpjs = listar_cnpjs(page)
            if limite_cnpjs:
                cnpjs = cnpjs[:limite_cnpjs]
            total_cnpjs = len(cnpjs)

            for indice_cnpj, cnpj in enumerate(cnpjs, start=1):
                _log(f"\n[CNPJ {indice_cnpj}/{total_cnpjs}] {cnpj['texto']}")
                t_cnpj = time.time()
                novos, falhas_cnpj = processar_cnpj(page, cnpj, estado, wb, tipos, indice_cnpj, total_cnpjs)
                falhas_ocorridas += falhas_cnpj
                dt_cnpj = time.time() - t_cnpj
                _log(
                    f"[CNPJ {indice_cnpj}/{total_cnpjs}] concluído: {novos} novo(s) em {_formatar_duracao(dt_cnpj)} | "
                    f"total geral: {len(estado['processados'])} processados, {len(estado['falhas'])} falhas pendentes | "
                    f"decorrido: {_formatar_duracao(time.time() - inicio)}"
                )
                # salva a cada CNPJ concluído - uma varredura completa pode
                # levar horas, não queremos perder tudo se algo interromper
                salvar_planilha(wb, PLANILHA_PATH)
                checkpoint.salvar(estado)

        except (SessaoExpiradaError, PortalIndisponivelError) as e:
            _log(f"\n[PAROU] {e}")
        finally:
            salvar_planilha(wb, PLANILHA_PATH)
            checkpoint.salvar(estado)
            browser.close()

    _log("\n=== RESUMO DA EXECUÇÃO ===")
    _log(f"Planilha: {PLANILHA_PATH}")
    _log(f"Novos processados nesta execução: {len(estado['processados']) - processados_no_inicio}")
    _log(f"Total processados (histórico completo): {len(estado['processados'])}")
    _log(f"Falhas ocorridas nesta execução: {falhas_ocorridas}")
    if estado["falhas"]:
        _log(f"Falhas pendentes: {len(estado['falhas'])} (ver {checkpoint.CHECKPOINT_FILE})")
    _log(f"Tempo total desta execução: {_formatar_duracao(time.time() - inicio)}")


if __name__ == "__main__":
    rodar()
