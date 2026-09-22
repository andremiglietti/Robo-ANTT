"""
Orquestrador principal do robô: liga varredura, download, extração de
campos e planilha, com checkpoint entre execuções (ver CLAUDE.md, item 6
da arquitetura).

Fluxo por combinação CNPJ×tipo de fiscalização, por página de resultado:
  seleciona CNPJ -> seleciona tipo -> busca -> pra cada linha da página
  (ainda visível na tela): já processado? pula. Senão: baixa o PDF, extrai
  os campos, adiciona na planilha (se ainda não tiver essa linha),
  marca como processado no checkpoint -> próxima página -> próxima
  combinação CNPJ×tipo. Salva a planilha e o checkpoint a cada combinação
  concluída (não só no final), pra não perder o progresso se algo
  interromper no meio de uma varredura longa (pode levar horas pra empresa
  toda - ver CLAUDE.md).

⚠️ Particionamento por CNPJ×TIPO, não por CNPJ inteiro (18/09/2026, ver
CLAUDE.md e _processar_item()): rodando com múltiplos workers, o trabalho é
dividido direto nas 61×7=427 combinações possíveis, não nos 61 CNPJs - um
CNPJ com volume desproporcional num único tipo (já visto: milhares de
documentos só em "Excesso de Peso" de 1 CNPJ) tem seus 7 tipos naturalmente
espalhados entre vários workers desde o início, em vez de sobrecarregar um
worker sozinho enquanto os outros ficam ociosos.

Acompanhamento visual (17/09/2026): todo print aqui usa flush=True e mostra
"Item X/N" (a combinação CNPJ×tipo atual) - dá pra acompanhar ao vivo
rodando no terminal, ou ler os logs depois (nenhuma informação de progresso
fica só numa tela que se apaga).

Garantias de completude, em duas frentes independentes (ver
"=== VERIFICAÇÃO DE COMPLETUDE ===" no final do log): (1) PAGINAÇÃO - toda
combinação CNPJ×tipo incompleta (busca/paginação interrompida por erro) é
retentada automaticamente até 3 vezes dentro da mesma execução; (2)
DOCUMENTO - toda falha de download/extração com CNPJ+tipo conhecido (ver
checkpoint.marcar_falha()/falhas_retentaveis(), 19/09/2026) também é
retentada diretamente até 3 vezes, sem depender de a combinação ser
revisitada por acaso numa execução futura (achado ao vivo: mudar o número
de workers entre execuções podia deixar falhas de documento pendentes pra
sempre, sem nenhum erro).
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from robo_antt import checkpoint, io_seguro
from robo_antt.config import PAUSA_ENTRE_ACOES_MS, PLANILHA_PATH, SESSION_FILE, TIPOS_FISCALIZACAO
from robo_antt.download import TabelaInvalidadaError, already_downloaded, baixar_pdf
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
    LimiteResultadosError,
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


def _registrar(wb, auto: str, caminho_pdf: Path, row: dict) -> dict:
    """Extrai os campos do PDF e adiciona a linha na planilha. Assume que
    quem chamou já conferiu que a linha ainda não existe (ver
    processar_linha()) - não checa `ja_registrado()` de novo aqui, porque
    extrair os campos (ler o PDF inteiro, achar a página do boleto etc.) já
    é o trabalho caro que a checagem em processar_linha() existe pra evitar
    repetir à toa."""
    campos = extrair_todos_campos(caminho_pdf)
    registro = {
        "link_arquivo": str(caminho_pdf),
        "numero_processo": row["numero_processo"],
        "auto_infracao": auto,
        "cnpj": row["cnpj"],
        "situacao": row["situacao"],  # 22/09/2026 - vem da tabela de busca, não do PDF (ver planilha.py)
        **campos,
    }
    adicionar_registro(wb, registro)
    return campos


def processar_linha(page, row: dict, estado: dict, wb, prefixo: str = "", tipo_value: str | None = None) -> str:
    """Baixa (se precisar) e extrai os campos de 1 auto, e adiciona na
    planilha se ainda não estiver lá. Marca sucesso/falha no checkpoint -
    falha aqui é sempre de UM documento específico (PDF ilegível, campo que
    não bateu com nenhum padrão conhecido etc.), não de sessão/portal (essas
    sobem como exceção e param a execução inteira, ver rodar()) nem de
    tabela invalidada (essa sobe pra marcar o TIPO inteiro como incompleto,
    ver TabelaInvalidadaError em download.py e _tentar_tipo() abaixo).

    Devolve "novo", "conhecido" ou "falha" - usado por _tentar_tipo() pra
    montar o resumo de progresso.

    `tipo_value` (19/09/2026): repassado só pra marcar_falha() saber ONDE
    essa falha aconteceu (junto com row["cnpj"]) - permite retentar essa
    falha diretamente depois, sem depender de a mesma combinação ser
    revisitada por acaso (ver checkpoint.falhas_retentaveis()).
    """
    auto = row["auto_infracao"]
    if checkpoint.ja_processado(estado, auto):
        return "conhecido"  # não printa - CNPJs com muito histórico já conhecido ficariam poluídos de linha

    # ⚠️ Achado ao vivo em 18/09/2026: o checkpoint é isolado POR WORKER (e
    # a partição de `total_workers` pode ser diferente de uma execução pra
    # outra) - um auto pode já ter sido baixado antes (por outro worker, ou
    # numa execução anterior à própria arquitetura de workers) sem que o
    # checkpoint DESTE worker saiba disso. `already_downloaded()` checa o
    # arquivo no disco direto - é a fonte de verdade de "já existe",
    # independente de qual checkpoint processou.
    #
    # ⚠️ Segundo achado no mesmo dia (pergunta direta do usuário: "isso não
    # acaba levando mais tempo?"): baixar de novo já era evitado desde cedo
    # hoje (mesma checagem já existia dentro de baixar_pdf()) - mas
    # REEXTRAIR os campos do PDF (ler o texto inteiro, achar a página do
    # boleto etc.) continuava acontecendo à toa pra todo documento já
    # conhecido, em TODA reexecução de manutenção - numa segunda varredura,
    # a maioria dos documentos cai nesse caminho, então esse desperdício
    # soma bastante. Corrigido: só extrai/registra de verdade se a linha
    # ainda não estiver NESTA planilha (`ja_registrado()`) - se já estiver,
    # nem abre o PDF de novo.
    existente = already_downloaded(auto, row["cnpj"])
    if existente:
        if not ja_registrado(wb, auto):
            _registrar(wb, auto, existente, row)
        checkpoint.marcar_processado(estado, auto)
        return "conhecido"  # não printa - documento já conhecido, mesmo que de outro worker/execução

    try:
        caminho_pdf = baixar_pdf(page, auto, row["cnpj"])
        campos = _registrar(wb, auto, caminho_pdf, row)
        checkpoint.marcar_processado(estado, auto)
        _log(f"{prefixo} {auto} -> novo ({campos.get('tipo_multa', '?')})")
        return "novo"
    except (SessaoExpiradaError, PortalIndisponivelError, TabelaInvalidadaError):
        raise  # falha de infraestrutura - não é do documento, para tudo (ver rodar())
    except Exception as e:  # falha real deste documento - registra e segue pros próximos
        checkpoint.marcar_falha(estado, auto, str(e), cnpj=row["cnpj"], tipo_value=tipo_value)
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

    Criada em 17/09/2026 pra poder ser chamado de novo nas retentativas de
    "garantia de varredura completa" (ver CLAUDE.md) - documentos
    "aparecendo" numa reexecução do mesmo CNPJ eram, na verdade, paginações
    que tinham parado no meio sem nenhum aviso.
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
                resultado = processar_linha(page, row, estado, wb, prefixo, tipo_value)
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
    except LimiteResultadosError as e:
        # ⚠️ Achado ao vivo em 22/09/2026 (ver CLAUDE.md): limite estrutural
        # de 1000 resultados do portal, não uma falha passageira - retentar
        # não resolve, mas ainda assim NÃO marca como "completo" (seria uma
        # garantia falsa) - mensagem própria pra deixar claro que essa
        # combinação específica precisa de decisão humana (ex.: escalar pra
        # ANTT), não só "rodar de novo".
        _log(f"{prefixo} [LIMITE DO PORTAL] {e}")
        return {"novos": 0, "falhas": 0, "completo": False}
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


def _selecionar_cnpj_com_recuperacao(page, cnpj: dict, prefixo: str = "") -> None:
    """Seleciona o CNPJ - se a página estiver travada, recupera e tenta de
    novo UMA vez antes de desistir de verdade.

    ⚠️ Achado ao vivo em 18/09/2026: o modal "Processando..." (#Progress_
    DivProgress) pode travar DE VEZ (nunca conclui o postback de verdade) -
    quando isso acontece, até ações simples como trocar de CNPJ ou de tipo
    de fiscalização estouram 30s, porque o JS/estado de postback do lado do
    cliente ficou quebrado. Retentar sem recarregar NÃO resolve (o estado
    quebrado continua o mesmo) - o que resolve é recarregar a tela do zero
    (mesma lógica de abrir_tela_processos() usada no início de rodar() - não
    precisa de login novo, só refaz a navegação e reseta o JS travado do
    lado do cliente) e tentar de novo.

    Passa `valor_esperado=cnpj["value"]` pra selecionar_cnpj() confirmar de
    verdade a troca (não só esperar um tempo fixo) - ver achado ao vivo na
    docstring de selecionar_cnpj() em portal.py (busca "vazia" por engano,
    sem erro nenhum, quando o postback da troca de CNPJ ainda não tinha
    assentado).
    """
    try:
        selecionar_cnpj(page, cnpj["indice"], valor_esperado=cnpj["value"])
    except (SessaoExpiradaError, PortalIndisponivelError):
        raise
    except Exception as e:
        _log(f"{prefixo}[RECUPERANDO] página travada ({e}) - recarregando do zero...")
        abrir_tela_processos(page)
        selecionar_cnpj(page, cnpj["indice"], valor_esperado=cnpj["value"])


def _processar_item(
    page, cnpj: dict, tipo_value: str, tipo_nome: str, estado: dict, wb, prefixo: str, forcar_reload: bool = False
) -> dict:
    """Processa 1 combinação CNPJ+tipo: seleciona o CNPJ (recuperando a
    página do zero se ela estiver travada - ver
    _selecionar_cnpj_com_recuperacao()) e tenta a busca/paginação/download
    desse tipo. Devolve o mesmo formato de _tentar_tipo():
    {"novos", "falhas", "completo"}.

    ⚠️ Particionamento por CNPJ×TIPO (18/09/2026, ver CLAUDE.md e o plano da
    sessão): antes, um worker recebia CNPJs inteiros (com os 7 tipos juntos)
    - um CNPJ com volume desproporcional num único tipo (visto ao vivo:
    milhares de documentos só em "Excesso de Peso" de 1 CNPJ) sobrecarregava
    um worker sozinho por horas enquanto os outros ficavam ociosos depois de
    terminar os deles. Agora `rodar()` particiona direto por CNPJ×tipo
    (61×7=427 combinações), então os 7 tipos de um CNPJ pesado já saem
    espalhados entre os workers desde o início - sem precisar de nenhuma
    coordenação em tempo real entre eles (que exigiria uma fila
    compartilhada com trava entre processos - mais arriscado de dar bug).
    Por isso `selecionar_cnpj()` agora acontece aqui, antes de CADA item, em
    vez de uma vez só por CNPJ.

    ⚠️ Achado ao vivo em 18/09/2026 (mesmo dia): o item 1 do primeiro teste
    dessa mudança reportou "sem processos" pro CNPJ matriz + Excesso de Peso
    - uma combinação que TODOS os testes anteriores do dia confirmaram ter 3
    documentos reais. Suspeita: trocar de CNPJ dispara um postback pesado no
    servidor (o mesmo que mostra o modal "Processando..." - confirmado
    porque essa troca é exatamente onde o travamento mais aparece agora,
    muito mais frequente que antes). O `wait_for_timeout` de
    `PAUSA_ENTRE_ACOES_MS` que já existia ficava ANTES de selecionar o CNPJ
    (no loop de rodar()), não depois - então a busca do tipo podia começar
    só 300ms (a espera interna de selecionar_cnpj()) depois da troca de
    CNPJ, tempo insuficiente pro postback assentar direito, arriscando ler
    a tabela num estado intermediário e achar "vazio" por engano - uma
    falha SILENCIOSA que a garantia de completude não detecta (não lança
    exceção nenhuma). Corrigido: a pausa agora acontece AQUI, depois de
    selecionar o CNPJ e antes de tentar o tipo - dá tempo de verdade pro
    postback da troca de CNPJ assentar antes de qualquer busca.
    ⚠️ Achado ao vivo em 21/09/2026 (validação do fix de busca com volume
    grande, mesmo CNPJ 92.660.604/0013-16): mesmo com a busca em si
    corrigida (ver _esperar_processamento_grande() em portal.py), o
    `ir_proxima_pagina()` seguinte travava do MESMO jeito documentado em
    18/09/2026 - o modal "Processando..." preso de vez, bloqueando o clique
    de "próxima página" por dezenas de tentativas até estourar 30s. A
    retentativa automática (`rodar()`) chamava `_processar_item()` de novo,
    mas `_selecionar_cnpj_com_recuperacao()` SÓ recarrega a página se
    `selecionar_cnpj()` EM SI falhar - e ela não falha aqui, porque o
    travamento é da tela de RESULTADOS (paginação), não da seleção de CNPJ.
    Resultado: a retentativa repetia a MESMA sequência na MESMA página já
    quebrada, e falhava exatamente do mesmo jeito de novo (confirmado ao
    vivo: RETRY 1/3 travou idêntico ao 1º erro). `forcar_reload=True`
    (usado pelas retentativas em rodar(), nunca na 1ª tentativa) recarrega a
    tela do zero incondicionalmente antes de selecionar o CNPJ, garantindo
    um estado de JS limpo pra cada nova tentativa - não só quando a
    seleção do CNPJ em si dá sinal de problema.
    """
    if forcar_reload:
        abrir_tela_processos(page)
    _selecionar_cnpj_com_recuperacao(page, cnpj, prefixo)
    page.wait_for_timeout(PAUSA_ENTRE_ACOES_MS)  # ver docstring acima - deixa o postback da troca de CNPJ assentar
    return _tentar_tipo(page, cnpj, tipo_value, tipo_nome, estado, wb, prefixo)


def rodar(
    limite_cnpjs: int | None = None,
    tipos: dict = TIPOS_FISCALIZACAO,
    session_file: Path = SESSION_FILE,
    checkpoint_file: Path = checkpoint.CHECKPOINT_FILE,
    planilha_path: Path = PLANILHA_PATH,
    worker_id: int | None = None,
    total_workers: int | None = None,
    cnpjs_especificos: set[str] | None = None,
) -> None:
    """Ponto de entrada principal - fino de propósito, só cuida da trava de
    concorrência (ver io_seguro.adquirir_trava()) antes de chamar
    _rodar_impl() (mesma lógica de sempre, só renomeada pra não precisar
    reindentar 300+ linhas nessa mudança).

    ⚠️ Achado ao vivo em 22/09/2026 (ver CLAUDE.md): rodando a IHM
    (scripts/executar_robo.py) e uma varredura manual ao mesmo tempo, os
    dois acabaram usando o MESMO checkpoint_file/planilha_path (a IHM
    sempre começa pelo worker 0) - 2 processos escrevendo no mesmo
    arquivo, quase causou perda de progresso real (identificado e
    encerrado a tempo naquela vez, mas por pouco). Agora levanta
    `ChecklistEmUsoError` de cara se outro processo já estiver usando esse
    MESMO `checkpoint_file`, em vez de deixar rolar e torcer.
    """
    trava = io_seguro.adquirir_trava(checkpoint_file)
    try:
        _rodar_impl(
            limite_cnpjs=limite_cnpjs,
            tipos=tipos,
            session_file=session_file,
            checkpoint_file=checkpoint_file,
            planilha_path=planilha_path,
            worker_id=worker_id,
            total_workers=total_workers,
            cnpjs_especificos=cnpjs_especificos,
        )
    finally:
        io_seguro.liberar_trava(trava)


def _rodar_impl(
    limite_cnpjs: int | None = None,
    tipos: dict = TIPOS_FISCALIZACAO,
    session_file: Path = SESSION_FILE,
    checkpoint_file: Path = checkpoint.CHECKPOINT_FILE,
    planilha_path: Path = PLANILHA_PATH,
    worker_id: int | None = None,
    total_workers: int | None = None,
    cnpjs_especificos: set[str] | None = None,
) -> None:
    """Ponto de entrada principal. `limite_cnpjs` e `tipos` existem pra
    facilitar testar com um escopo pequeno antes de rodar a empresa toda
    (que pode levar horas - ver "achados" no CLAUDE.md sobre volume real).

    `session_file`/`checkpoint_file`/`planilha_path` têm default = execução
    única de sempre (comportamento inalterado se chamado sem argumentos).
    `worker_id`/`total_workers` são da arquitetura de múltiplos workers
    (17/09/2026, ver CLAUDE.md e o plano da sessão): quando os dois são
    passados, filtra as combinações CNPJ×tipo (não os CNPJs inteiros - ver
    "Particionamento por CNPJ×TIPO" no topo do arquivo) pelo padrão
    intercalado `indice % total_workers == worker_id`, e cada worker
    lê/escreve SEMPRE nos seus próprios arquivos (sessão/checkpoint/planilha
    passados aqui) - nunca nos compartilhados, pra não ter concorrência de
    escrita entre processos. A consolidação na planilha real do SharePoint é
    feita à parte, por scripts/consolidar_planilhas.py.

    `cnpjs_especificos` (18/09/2026, ver CLAUDE.md - "rebalanceamento por
    rodadas"): se passado, um conjunto de CNPJ (`cnpj["value"]`) - filtra a
    lista de CNPJs pra só esses ANTES de aplicar o particionamento por
    worker, usado por scripts/proxima_rodada.py pra redistribuir só os
    CNPJs que ainda faltam (segundo scripts/relatorio_completude.py) entre
    quantos workers estiverem disponíveis na rodada seguinte, em vez de
    ficar preso à partição original dos 61 CNPJs completos - evita workers
    ociosos enquanto outros ainda têm CNPJs pesados pela frente.
    """
    rotulo_worker = f"[Worker {worker_id}] " if worker_id is not None else ""
    inicio = time.time()
    estado = checkpoint.carregar(checkpoint_file)
    wb = abrir_ou_criar(planilha_path)
    processados_no_inicio = len(estado["processados"])
    falhas_ocorridas = 0  # falhas que ACONTECERAM nesta execução (não confundir com len(estado["falhas"]) - ver _processar_item())
    todos_incompletos: list[tuple[dict, str, str]] = []  # (cnpj, tipo_value, tipo_nome) - ver "garantia de varredura completa"
    itens_tentados = 0
    total_itens = 0
    itens_listados = False  # só True depois de listar_cnpjs() ter sucesso - distingue "0 de 0" (nunca chegou a listar, ex. sessão caiu antes) de "terminou tudo" (ver bug corrigido em 17/09/2026: sem isso, sessão expirando ANTES de listar CNPJs relatava "100% completo" por engano, já que 0==0)

    with sync_playwright() as p:
        browser, context, page = abrir_contexto(p, headless=True, session_file=session_file)
        try:
            abrir_tela_processos(page)
            cnpjs = listar_cnpjs(page)
            if cnpjs_especificos is not None:
                cnpjs = [c for c in cnpjs if c["value"] in cnpjs_especificos]
            if limite_cnpjs:
                cnpjs = cnpjs[:limite_cnpjs]
            # usado pela retentativa de falhas de documento (ver abaixo) pra
            # achar o dict completo (indice/texto) de um CNPJ a partir só do
            # valor gravado numa falha antiga - ainda não filtrado por
            # worker (só por limite_cnpjs/cnpjs_especificos, que definem o
            # escopo pretendido desta execução), então uma falha registrada
            # por ESTE checkpoint sempre é encontrada aqui, mesmo que a
            # combinação CNPJ×tipo dela caia num "worker" diferente sob a
            # partição de hoje.
            cnpjs_por_valor = {c["value"]: c for c in cnpjs}

            # Particiona por CNPJ×TIPO, não por CNPJ inteiro (18/09/2026, ver
            # CLAUDE.md e _processar_item()) - espalha o peso de CNPJs com
            # volume desproporcional num único tipo entre os workers desde o
            # início, em vez de um worker só carregar um CNPJ pesado sozinho.
            todos_itens = [(cnpj, tipo_value, tipo_nome) for cnpj in cnpjs for tipo_value, tipo_nome in tipos.items()]
            if worker_id is not None and total_workers:
                todos_itens = [item for i, item in enumerate(todos_itens) if i % total_workers == worker_id]
            total_itens = len(todos_itens)
            itens_listados = True

            for indice_item, (cnpj, tipo_value, tipo_nome) in enumerate(todos_itens, start=1):
                prefixo = f"  {rotulo_worker}[Item {indice_item}/{total_itens} | {cnpj['texto']} | {tipo_nome}]"
                # a pausa acontece DENTRO de _processar_item, depois de
                # selecionar o CNPJ (ver docstring lá) - não antes, senão não
                # protege a troca de CNPJ de verdade
                resultado = _processar_item(page, cnpj, tipo_value, tipo_nome, estado, wb, prefixo)
                falhas_ocorridas += resultado["falhas"]
                if resultado["completo"]:
                    checkpoint.marcar_varredura_completa(estado, cnpj["value"], tipo_value)
                else:
                    todos_incompletos.append((cnpj, tipo_value, tipo_nome))
                itens_tentados += 1

                # salva a cada item concluído (não só no final) - uma
                # varredura completa pode levar horas, não queremos perder
                # progresso se algo interromper no meio
                salvar_planilha(wb, planilha_path)
                checkpoint.salvar(estado, checkpoint_file)

                if indice_item % 10 == 0 or indice_item == total_itens:
                    _log(
                        f"{rotulo_worker}[Progresso] {indice_item}/{total_itens} combinação(ões) CNPJ×tipo tentada(s) | "
                        f"total geral: {len(estado['processados'])} processados, {len(estado['falhas'])} falhas pendentes | "
                        f"decorrido: {_formatar_duracao(time.time() - inicio)}"
                    )

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
                        prefixo = f"  {rotulo_worker}[RETRY {tentativa_extra}/3 | {cnpj['texto']} | {tipo_nome}]"
                        # forcar_reload=True: ver achado de 21/09/2026 na docstring
                        # de _processar_item() - uma combinação só fica "incompleta"
                        # depois de já ter travado uma vez, então a página pode estar
                        # num estado quebrado que só um reload de verdade resolve
                        # (reselecionar o mesmo CNPJ sozinho não detecta/conserta isso).
                        resultado = _processar_item(page, cnpj, tipo_value, tipo_nome, estado, wb, prefixo, forcar_reload=True)
                        falhas_ocorridas += resultado["falhas"]
                        if resultado["completo"]:
                            checkpoint.marcar_varredura_completa(estado, cnpj["value"], tipo_value)
                        else:
                            todos_incompletos.append((cnpj, tipo_value, tipo_nome))
                except Exception:
                    # ⚠️ Achado ao vivo em 18/09/2026: captura Exception
                    # genérica (cobre também SessaoExpiradaError/
                    # PortalIndisponivelError, que são subclasses) - não só
                    # as 2 conhecidas. selecionar_cnpj() (e outras chamadas de
                    # setup fora do try/except por-tipo de _tentar_tipo())
                    # podem estourar timeout depois que a página entra num
                    # estado travado (ex.: modal "Processando..." nunca some
                    # de verdade) - sem isso, crashava o processo INTEIRO com
                    # traceback cru, sem salvar nem reportar nada -
                    # exatamente o oposto do que a garantia de completude
                    # deveria entregar. O que ainda não foi tentado nesta
                    # rodada (incluindo o item que estava sendo tentado
                    # quando caiu) continua pendente - sem isso, sumiria do
                    # relatório final como se tivesse sido confirmado, quando
                    # na verdade nunca chegou a ser tentado de novo.
                    todos_incompletos.extend(pendentes[indice_pendente:])
                    raise
                salvar_planilha(wb, planilha_path)
                checkpoint.salvar(estado, checkpoint_file)
                tentativa_extra += 1

            # Retentativa DIRECIONADA de falhas de documento pendentes
            # (19/09/2026 - pedido explícito do usuário: "o programa precisa
            # resolver todas as pendências", ver CLAUDE.md). Achado ao vivo
            # no mesmo dia: sem isso, uma falha só era retentada se a MESMA
            # combinação CNPJ×tipo fosse revisitada por acaso numa execução
            # futura (ex.: mesmo worker/partição de quando ela aconteceu) -
            # confirmado que mudar `total_workers` entre execuções podia
            # deixar falhas presas indefinidamente, sem erro nenhum (71
            # falhas continuaram em 71 depois de rodar com um particionamento
            # diferente). Agora usa o CNPJ+tipo gravado em marcar_falha() (ver
            # checkpoint.falhas_retentaveis()) pra ir direto nas combinações
            # certas, reaproveitando _processar_item() (mesmo caminho testado
            # de sempre) - não é uma "retentativa só desse auto": reabre a
            # busca inteira daquele CNPJ×tipo, que processa de novo TODAS as
            # linhas da página (a maioria já conhecida, pula rápido), e só
            # tenta baixar de verdade os autos que ainda não têm sucesso
            # registrado - inclusive pode achar documento novo genuíno de
            # brinde, sem custo extra.
            falhas_iniciais = checkpoint.falhas_retentaveis(estado)
            if falhas_iniciais:
                combinacoes = {(cnpj_v, tipo_v) for _, cnpj_v, tipo_v in falhas_iniciais}
                _log(
                    f"\n{rotulo_worker}=== Retentando {len(falhas_iniciais)} falha(s) de documento pendente(s) "
                    f"({len(combinacoes)} combinação(ões) CNPJ×tipo) ==="
                )
                tentativa_falha = 1
                while combinacoes and tentativa_falha <= 3:
                    pendentes_combo = combinacoes
                    _log(f"{rotulo_worker}--- Retentativa de falhas {tentativa_falha}/3 ---")
                    for cnpj_value, tipo_value in pendentes_combo:
                        cnpj_obj = cnpjs_por_valor.get(cnpj_value)
                        if cnpj_obj is None:
                            # CNPJ fora do escopo desta execução (ex.: limite_cnpjs
                            # menor, ou CNPJ não existe mais no portal) - não dá
                            # pra retentar aqui, fica pra uma execução com escopo
                            # maior/mais atual.
                            continue
                        tipo_nome = tipos.get(tipo_value, tipo_value)
                        prefixo = f"  {rotulo_worker}[RETRY FALHA {tentativa_falha}/3 | {cnpj_obj['texto']} | {tipo_nome}]"
                        # forcar_reload=True - mesmo motivo da retentativa de
                        # paginação incompleta (ver docstring de _processar_item()):
                        # essa combinação já teve um documento falhar antes, então
                        # não custa garantir uma página limpa pra esta nova tentativa.
                        resultado = _processar_item(page, cnpj_obj, tipo_value, tipo_nome, estado, wb, prefixo, forcar_reload=True)
                        falhas_ocorridas += resultado["falhas"]
                        if resultado["completo"]:
                            checkpoint.marcar_varredura_completa(estado, cnpj_value, tipo_value)
                    salvar_planilha(wb, planilha_path)
                    checkpoint.salvar(estado, checkpoint_file)
                    # recalcula com base no que REALMENTE continua falhando
                    # depois desta rodada (não assume que tudo resolveu)
                    combinacoes = {(cnpj_v, tipo_v) for _, cnpj_v, tipo_v in checkpoint.falhas_retentaveis(estado)}
                    tentativa_falha += 1

        except (SessaoExpiradaError, PortalIndisponivelError) as e:
            _log(f"\n{rotulo_worker}[PAROU] {e}")
        except Exception as e:
            # ⚠️ Achado ao vivo em 18/09/2026: sem esse catch-all, qualquer
            # exceção inesperada (ex.: selecionar_cnpj() estourando timeout
            # depois que a página trava de vez atrás de um modal
            # "Processando..." que nunca some de verdade - ver "garantia de
            # varredura completa" no CLAUDE.md) derrubava o processo INTEIRO
            # com traceback cru, sem salvar nem reportar nada - o oposto do
            # que essa garantia deveria entregar. Trata como falha de
            # infraestrutura desconhecida: mesmo efeito prático de
            # SessaoExpiradaError/PortalIndisponivelError (para tudo, salva
            # o que já tem via finally, reporta claramente no final), só com
            # mensagem diferente pra não confundir com sessão expirada de
            # verdade.
            _log(f"\n{rotulo_worker}[PAROU] Erro inesperado, parando a execução com segurança: {e}")
        finally:
            # ⚠️ Achado em 19/09/2026 (revisão de robustez pedida pelo
            # usuário): estas duas chamadas já retentam sozinhas por conta
            # própria (substituir_com_retentativa, até 5x/5s - ver
            # io_seguro.py), mas se AINDA ASSIM falharem (lock persistente
            # do OneDrive, disco cheio etc.), a exceção subia sem proteção
            # própria - derrubava o processo ANTES de chegar em
            # browser.close() (leak de processo do Chromium) e ANTES do
            # relatório final (=== VERIFICAÇÃO DE COMPLETUDE ===) sequer ser
            # impresso, escondendo justamente a informação que essa garantia
            # existe pra nunca esconder. Cada chamada agora é isolada: se uma
            # falhar, avisa alto e continua pras próximas, em vez de morrer
            # em silêncio no meio da limpeza.
            try:
                salvar_planilha(wb, planilha_path)
            except Exception as e:
                _log(f"{rotulo_worker}[ATENÇÃO] Falha ao salvar a planilha no encerramento: {e}")
            try:
                checkpoint.salvar(estado, checkpoint_file)
            except Exception as e:
                _log(f"{rotulo_worker}[ATENÇÃO] Falha ao salvar o checkpoint no encerramento: {e}")
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
    if not itens_listados:
        _log(
            f"{rotulo_worker}[ATENÇÃO] Não foi possível nem começar a varredura desta execução "
            '(ver "[PAROU]" acima) - nada foi verificado. Rode de novo.'
        )
    elif itens_tentados < total_itens:
        _log(
            f"{rotulo_worker}[ATENÇÃO] Execução interrompida antes de terminar - só {itens_tentados} de {total_itens} "
            "combinação(ões) CNPJ×tipo desta leva chegaram a ser tentadas (ver \"[PAROU]\" acima pro motivo exato - "
            "sessão expirada, portal indisponível, ou página travada mesmo depois da recuperação automática). "
            "Rode de novo pra continuar - o que já foi confirmado não será refeito."
        )
    paginacao_completa = itens_listados and itens_tentados == total_itens and not todos_incompletos
    if todos_incompletos:
        _log(
            f"{rotulo_worker}[ATENÇÃO] {len(todos_incompletos)} combinação(ões) CNPJ×tipo AINDA incompleta(s) "
            "depois de 3 retentativas:"
        )
        for cnpj, tipo_value, tipo_nome in todos_incompletos:
            _log(f"{rotulo_worker}   - {cnpj['texto']} | {tipo_nome}")
        _log(f"{rotulo_worker}   Rode de novo mais tarde pra tentar terminar essas - o resto já está confirmado.")
    elif itens_listados and itens_tentados == total_itens:
        _log(f"{rotulo_worker}[OK] Paginação 100% completa: todas as combinações CNPJ×tipo desta execução foram percorridas até o fim.")

    # ⚠️ Achado em 19/09/2026 (revisão de robustez pedida pelo usuário):
    # "paginação completa" (acima) só garante que VIMOS todas as linhas da
    # tabela - não garante que baixamos/extraímos cada uma com sucesso. Um
    # auto que a paginação viu mas cujo download falhou (ex.: PDF inválido,
    # timeout de clique) fica em estado["falhas"], e o relatório de
    # completude ficava mudo sobre isso - dava pra terminar com "[OK] 100%
    # completas" na paginação e MESMO ASSIM faltar autos reais na planilha
    # final. Agora isso é reportado explicitamente, separado da paginação.
    if estado["falhas"]:
        # ⚠️ Achado em 19/09/2026: a partir de hoje, falhas COM cnpj/tipo
        # registrado (ver checkpoint.falhas_retentaveis()) já foram
        # retentadas DIRETAMENTE dentro desta mesma execução (ver acima) -
        # se ainda aparecem aqui, é porque a retentativa direcionada (até 3
        # rodadas) não resolveu de verdade (ex.: PDF realmente corrompido no
        # servidor), não porque ninguém tentou. Falhas SEM cnpj/tipo (só
        # possíveis em checkpoints salvos antes de hoje, formato antigo) não
        # têm como ser retentadas diretamente - só descobertas de novo por
        # acaso numa varredura que passe pela combinação certa.
        legadas = len(estado["falhas"]) - len(checkpoint.falhas_retentaveis(estado))
        detalhe_legadas = (
            f" ({legadas} delas sem CNPJ/tipo registrado - de checkpoints salvos antes de 19/09/2026, "
            "não retentáveis diretamente; as demais JÁ foram retentadas nesta execução e continuam falhando.)"
            if legadas
            else " (já retentadas diretamente nesta execução, até 3 vezes cada, e continuam falhando - "
            "provavelmente um problema real do documento no servidor, não passageiro.)"
        )
        _log(
            f"{rotulo_worker}[ATENÇÃO] {len(estado['falhas'])} auto(s) VISTO(S) na tabela mas NÃO baixado(s)/"
            "extraído(s) com sucesso (falha de documento específico - independe da paginação estar completa)."
            f"{detalhe_legadas} A planilha desta execução pode NÃO ter 100% dos autos reais até essas falhas "
            f"serem resolvidas (ver {checkpoint_file})."
        )
    elif paginacao_completa:
        _log(
            f"{rotulo_worker}[OK] Cobertura 100% completa confirmada: paginação percorrida por inteiro E "
            "nenhuma falha de documento pendente."
        )


if __name__ == "__main__":
    rodar()
