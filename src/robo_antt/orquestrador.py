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
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from robo_antt import checkpoint
from robo_antt.config import PLANILHA_PATH, SESSION_FILE, TIPOS_FISCALIZACAO
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
    acompanhamento em tempo real.

    ⚠️ Achado em 17/09/2026: rodando num console/arquivo que não é UTF-8
    (ex.: cp1252, comum no Windows), um caractere fora do padrão (mesmo só
    um emoji) derruba o processo com UnicodeEncodeError bem no fim da
    execução - péssimo justo na hora de reportar o resultado. Por isso o
    print tem um fallback: se a codificação do destino não aceitar algum
    caractere, troca só esse caractere (não trava o robô por causa de 1
    símbolo no log)."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(encoding, errors="replace").decode(encoding), flush=True)


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


def _tentar_tipo(page, cnpj: dict, tipo_value: str, tipo_nome: str, estado: dict, wb, prefixo: str) -> dict:
    """Tenta processar 1 tipo de fiscalização pra 1 CNPJ (o CNPJ já deve
    estar selecionado). Devolve {"novos", "falhas", "completo"} -
    `completo=True` SÓ quando a paginação inteira foi percorrida sem
    nenhuma exceção (busca ou "próxima página") - é o sinal usado por
    rodar() pra decidir se essa combinação CNPJ+tipo pode ser marcada como
    confirmada no checkpoint (ver checkpoint.marcar_varredura_completa()) ou
    se precisa ser retentada.

    Extraído de processar_cnpj() em 17/09/2026 pra poder ser chamado de novo
    nas retentativas de "garantia de varredura completa" (ver CLAUDE.md) -
    documentos "aparecendo" numa reexecução do mesmo CNPJ eram, na verdade,
    paginações que tinham parado no meio sem nenhum aviso.
    """
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
        if total_linhas:
            _log(
                f"{prefixo} concluído: {total_linhas} processo(s) na tela "
                f"({novos} novo(s), {falhas} falha(s), resto já conhecido)"
            )
        else:
            _log(f"{prefixo} sem processos")
        return {"novos": novos, "falhas": falhas, "completo": True}
    except (SessaoExpiradaError, PortalIndisponivelError):
        raise  # falha de infraestrutura - para tudo (ver rodar())
    except Exception as e:
        # falha ao navegar (busca ou paginação) pra ESSE tipo específico -
        # não é culpa de nenhum documento em particular pra marcar no
        # checkpoint, mas também não deveria derrubar a varredura inteira -
        # loga e marca como INCOMPLETO (rodar() retenta automaticamente,
        # ver "garantia de varredura completa" no CLAUDE.md) em vez de só
        # engolir o erro e seguir em frente como antes - isso é exatamente o
        # que escondia documentos não descobertos até uma reexecução futura
        # conseguir terminar essa mesma busca sem travar.
        _log(f"{prefixo} [INCOMPLETO] varredura interrompida, será retentada: {e}")
        return {"novos": 0, "falhas": 0, "completo": False}


def processar_cnpj(
    page,
    cnpj: dict,
    estado: dict,
    wb,
    tipos: dict = TIPOS_FISCALIZACAO,
    indice_cnpj: int = 1,
    total_cnpjs: int = 1,
    rotulo_worker: str = "",
) -> dict:
    """Varre um CNPJ por todos os tipos de fiscalização informados,
    processando (baixando/extraindo/registrando) cada linha encontrada.
    Devolve {"novos", "falhas", "incompletos"} - "incompletos" é uma lista
    de (cnpj, tipo_value, tipo_nome) pras combinações que não terminaram a
    paginação (ver _tentar_tipo()) e precisam ser retentadas por rodar().

    "falhas" aqui conta o que ACONTECEU nesta execução, não é o mesmo que
    `len(estado["falhas"])` no final (esse é só o número de falhas ainda
    PENDENTES no checkpoint, que pode até diminuir numa execução se falhas
    antigas forem resolvidas com sucesso - ver checkpoint.marcar_processado()).

    `indice_cnpj`/`total_cnpjs` são só pra exibir "CNPJ X/N" no progresso -
    não mudam o comportamento. `rotulo_worker` (ex.: "[Worker 1] ") é só pra
    identificar de qual worker é cada linha, quando rodando em paralelo -
    ver rodar() e a arquitetura de múltiplos workers (17/09/2026).
    """
    selecionar_cnpj(page, cnpj["indice"])
    processados_antes = len(estado["processados"])
    total_tipos = len(tipos)
    falhas_cnpj = 0
    incompletos = []

    for indice_tipo, (tipo_value, tipo_nome) in enumerate(tipos.items(), start=1):
        prefixo = f"  {rotulo_worker}[CNPJ {indice_cnpj}/{total_cnpjs} | Tipo {indice_tipo}/{total_tipos}: {tipo_nome}]"
        page.wait_for_timeout(2000)  # não martelar o portal - ver PAUSA_ENTRE_ACOES_MS em config.py
        resultado = _tentar_tipo(page, cnpj, tipo_value, tipo_nome, estado, wb, prefixo)
        falhas_cnpj += resultado["falhas"]
        if resultado["completo"]:
            checkpoint.marcar_varredura_completa(estado, cnpj["value"], tipo_value)
        else:
            incompletos.append((cnpj, tipo_value, tipo_nome))

    novos = len(estado["processados"]) - processados_antes
    return {"novos": novos, "falhas": falhas_cnpj, "incompletos": incompletos}


def rodar(
    limite_cnpjs: int | None = None,
    tipos: dict = TIPOS_FISCALIZACAO,
    session_file: Path = SESSION_FILE,
    checkpoint_file: Path = checkpoint.CHECKPOINT_FILE,
    planilha_path: Path = PLANILHA_PATH,
    worker_id: int | None = None,
    total_workers: int | None = None,
) -> None:
    """Ponto de entrada principal. `limite_cnpjs` e `tipos` existem pra
    facilitar testar com um escopo pequeno antes de rodar a empresa toda
    (que pode levar horas - ver "achados" no CLAUDE.md sobre volume real).

    `session_file`/`checkpoint_file`/`planilha_path` têm default = execução
    única de sempre (comportamento inalterado se chamado sem argumentos).
    `worker_id`/`total_workers` são da arquitetura de múltiplos workers
    (17/09/2026, ver CLAUDE.md e o plano da sessão): quando os dois são
    passados, filtra os CNPJs pelo padrão intercalado
    `indice % total_workers == worker_id` (espalha melhor a variância de
    volume entre workers do que dividir em blocos contíguos), e cada worker
    lê/escreve SEMPRE nos seus próprios arquivos (sessão/checkpoint/planilha
    passados aqui) - nunca nos compartilhados, pra não ter concorrência de
    escrita entre processos. A consolidação na planilha real do SharePoint é
    feita à parte, por scripts/consolidar_planilhas.py.
    """
    rotulo_worker = f"[Worker {worker_id}] " if worker_id is not None else ""
    inicio = time.time()
    estado = checkpoint.carregar(checkpoint_file)
    wb = abrir_ou_criar(planilha_path)
    processados_no_inicio = len(estado["processados"])
    falhas_ocorridas = 0  # falhas que ACONTECERAM nesta execução (não confundir com len(estado["falhas"]) - ver processar_cnpj())
    todos_incompletos: list[tuple[dict, str, str]] = []  # (cnpj, tipo_value, tipo_nome) - ver "garantia de varredura completa"
    cnpjs_tentados = 0
    total_cnpjs = 0
    cnpjs_listados = False  # só True depois de listar_cnpjs() ter sucesso - distingue "0 de 0" (nunca chegou a listar, ex. sessão caiu antes) de "terminou tudo" (ver bug corrigido em 17/09/2026: sem isso, sessão expirando ANTES de listar CNPJs relatava "100% completo" por engano, já que 0==0)

    with sync_playwright() as p:
        browser, context, page = abrir_contexto(p, headless=True, session_file=session_file)
        try:
            abrir_tela_processos(page)
            cnpjs = listar_cnpjs(page)
            if worker_id is not None and total_workers:
                cnpjs = [c for i, c in enumerate(cnpjs) if i % total_workers == worker_id]
            if limite_cnpjs:
                cnpjs = cnpjs[:limite_cnpjs]
            total_cnpjs = len(cnpjs)
            cnpjs_listados = True

            for indice_cnpj, cnpj in enumerate(cnpjs, start=1):
                _log(f"\n{rotulo_worker}[CNPJ {indice_cnpj}/{total_cnpjs}] {cnpj['texto']}")
                t_cnpj = time.time()
                resultado_cnpj = processar_cnpj(page, cnpj, estado, wb, tipos, indice_cnpj, total_cnpjs, rotulo_worker)
                falhas_ocorridas += resultado_cnpj["falhas"]
                todos_incompletos.extend(resultado_cnpj["incompletos"])
                cnpjs_tentados += 1
                dt_cnpj = time.time() - t_cnpj
                _log(
                    f"{rotulo_worker}[CNPJ {indice_cnpj}/{total_cnpjs}] concluído: {resultado_cnpj['novos']} novo(s) em {_formatar_duracao(dt_cnpj)} | "
                    f"total geral: {len(estado['processados'])} processados, {len(estado['falhas'])} falhas pendentes | "
                    f"decorrido: {_formatar_duracao(time.time() - inicio)}"
                )
                # salva a cada CNPJ concluído - uma varredura completa pode
                # levar horas, não queremos perder tudo se algo interromper
                salvar_planilha(wb, planilha_path)
                checkpoint.salvar(estado, checkpoint_file)

            # Garantia de varredura completa (17/09/2026, ver CLAUDE.md):
            # retenta automaticamente, dentro desta mesma execução, só as
            # combinações CNPJ+tipo que ficaram incompletas (paginação
            # interrompida por erro) - até 3 rodadas extras. Não refaz o que
            # já foi confirmado completo, nem reprocessa autos já no
            # checkpoint (processar_linha já pula os conhecidos).
            tentativa_extra = 1
            while todos_incompletos and tentativa_extra <= 3:
                pendentes, todos_incompletos = todos_incompletos, []
                _log(
                    f"\n{rotulo_worker}=== Retentativa {tentativa_extra}/3: "
                    f"{len(pendentes)} combinação(ões) CNPJ×tipo incompleta(s) ==="
                )
                try:
                    for indice_pendente, (cnpj, tipo_value, tipo_nome) in enumerate(pendentes):
                        selecionar_cnpj(page, cnpj["indice"])
                        prefixo = f"  {rotulo_worker}[RETRY {tentativa_extra}/3 | {cnpj['texto']} | {tipo_nome}]"
                        page.wait_for_timeout(2000)
                        resultado = _tentar_tipo(page, cnpj, tipo_value, tipo_nome, estado, wb, prefixo)
                        falhas_ocorridas += resultado["falhas"]
                        if resultado["completo"]:
                            checkpoint.marcar_varredura_completa(estado, cnpj["value"], tipo_value)
                        else:
                            todos_incompletos.append((cnpj, tipo_value, tipo_nome))
                except (SessaoExpiradaError, PortalIndisponivelError):
                    # o que ainda não foi tentado nesta rodada (incluindo o
                    # item que estava sendo tentado quando caiu) continua
                    # pendente - sem isso, sumiria do relatório final como
                    # se tivesse sido confirmado, quando na verdade nunca
                    # chegou a ser tentado de novo.
                    todos_incompletos.extend(pendentes[indice_pendente:])
                    raise
                salvar_planilha(wb, planilha_path)
                checkpoint.salvar(estado, checkpoint_file)
                tentativa_extra += 1

        except (SessaoExpiradaError, PortalIndisponivelError) as e:
            _log(f"\n{rotulo_worker}[PAROU] {e}")
        finally:
            salvar_planilha(wb, planilha_path)
            checkpoint.salvar(estado, checkpoint_file)
            browser.close()

    _log(f"\n{rotulo_worker}=== RESUMO DA EXECUÇÃO ===")
    _log(f"{rotulo_worker}Planilha: {planilha_path}")
    _log(f"{rotulo_worker}Novos processados nesta execução: {len(estado['processados']) - processados_no_inicio}")
    _log(f"{rotulo_worker}Total processados (histórico completo): {len(estado['processados'])}")
    _log(f"{rotulo_worker}Falhas ocorridas nesta execução: {falhas_ocorridas}")
    if estado["falhas"]:
        _log(f"{rotulo_worker}Falhas pendentes: {len(estado['falhas'])} (ver {checkpoint_file})")
    _log(f"{rotulo_worker}Tempo total desta execução: {_formatar_duracao(time.time() - inicio)}")

    _log(f"\n{rotulo_worker}=== VERIFICAÇÃO DE COMPLETUDE ===")
    if not cnpjs_listados:
        _log(
            f"{rotulo_worker}[ATENÇÃO] Não foi possível nem começar a varredura desta execução "
            '(ver "[PAROU]" acima) - nada foi verificado. Rode de novo.'
        )
    elif cnpjs_tentados < total_cnpjs:
        _log(
            f"{rotulo_worker}[ATENÇÃO] Execução interrompida antes de terminar - só {cnpjs_tentados} de {total_cnpjs} "
            "CNPJs desta leva chegaram a ser tentados (sessão expirou ou portal caiu no meio). "
            "Rode de novo pra continuar - o que já foi confirmado não será refeito."
        )
    if todos_incompletos:
        _log(
            f"{rotulo_worker}[ATENÇÃO] {len(todos_incompletos)} combinação(ões) CNPJ×tipo AINDA incompleta(s) "
            "depois de 3 retentativas:"
        )
        for cnpj, tipo_value, tipo_nome in todos_incompletos:
            _log(f"{rotulo_worker}   - {cnpj['texto']} | {tipo_nome}")
        _log(f"{rotulo_worker}   Rode de novo mais tarde pra tentar terminar essas - o resto já está confirmado.")
    elif cnpjs_listados and cnpjs_tentados == total_cnpjs:
        _log(f"{rotulo_worker}[OK] Todas as combinações CNPJ×tipo desta execução foram confirmadas 100% completas.")


if __name__ == "__main__":
    rodar()
