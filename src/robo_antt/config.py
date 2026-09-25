import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SESSION_FILE = BASE_DIR / "data" / "sessao" / "sessao_antt.json"
# Estado interno do robô (checkpoint) - fica LOCAL, não sincronizado com o
# SharePoint: é só memória de execução do robô, não é entregável pra ninguém
# ler, e escrever nele com frequência (a cada CNPJ) numa pasta do OneDrive
# geraria sincronização o tempo todo à toa.
OUTPUT_DIR = BASE_DIR / "data" / "output"

# Configuração local por máquina/pessoa (25/09/2026, pedido do usuário -
# "essa possibilidade deve ser algo fácil, a pessoa deverá conseguir
# selecionar a pasta"): guarda a pasta de destino escolhida manualmente
# via a GUI (ver executar_robo_gui.py), pra não perguntar de novo nas
# próximas execuções desta máquina. Nunca versionado - é específico de
# cada instalação, não do projeto (ver .gitignore).
CONFIG_LOCAL_PATH = BASE_DIR / "data" / "config_local.json"


def _carregar_sharepoint_dir_configurado() -> Path | None:
    """Lê a pasta de destino escolhida manualmente nesta máquina, se
    alguma vez foi escolhida - None se ainda não (1ª execução, ou o
    palpite padrão abaixo já bateu certo e ninguém precisou escolher)."""
    if not CONFIG_LOCAL_PATH.exists():
        return None
    try:
        dado = json.loads(CONFIG_LOCAL_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    caminho = dado.get("sharepoint_dir")
    return Path(caminho) if caminho else None


def salvar_sharepoint_dir(caminho: Path) -> None:
    """Grava a escolha manual da pasta de destino - chamado pela GUI
    depois da pessoa escolher pelo seletor de pastas (ver
    executar_robo_gui.py). Pra "esquecer" a escolha e voltar a perguntar,
    basta apagar `CONFIG_LOCAL_PATH` manualmente.

    ⚠️ Só toma efeito numa execução FUTURA - vários módulos do projeto
    importam `DOWNLOAD_DIR`/`PLANILHA_PATH` como valor fixo no momento da
    importação (`from robo_antt.config import PLANILHA_PATH`), não como
    referência viva ao módulo `config` - mudar só o valor em memória aqui
    não atualizaria o que esses módulos já capturaram. Por isso a GUI
    reinicia o programa inteiro depois de chamar esta função, garantindo
    que todo módulo (inclusive os workers, cada um seu próprio processo)
    reimporte `config.py` do zero, já com a pasta nova."""
    CONFIG_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_LOCAL_PATH.write_text(json.dumps({"sharepoint_dir": str(caminho)}, ensure_ascii=False), encoding="utf-8")


# Pasta sincronizada com o OneDrive/SharePoint - aqui vai o que É entregável:
# os PDFs baixados (organizados por CNPJ/tipo de multa) e a planilha final.
# Nome da biblioteca confirmado pelo usuário em 16/09/2026.
#
# ⚠️ Achado em 21-22/09/2026: até hoje esse caminho era ABSOLUTO e craft com
# o usuário Windows de UM computador específico (`C:\Users\a847468\...`) -
# rodando em outro computador/usuário (o robô pode ser usado por mais de 1
# pessoa), o caminho simplesmente não existe. Corrigido pra usar
# `Path.home()`, que resolve o prefixo do usuário sozinho - o NOME da
# pasta sob o OneDrive é o mesmo pra qualquer pessoa com acesso à mesma
# biblioteca do SharePoint, só o `C:\Users\<usuário>\` muda de máquina pra
# máquina.
#
# ✅ Resolvido em 25/09/2026 (pedido do usuário, pensando numa 2ª pessoa
# usando o robô no computador dela): esse caminho calculado é só um
# PALPITE inicial agora - se ele não existir, a GUI pergunta a pasta
# certa por um seletor (ver executar_robo_gui.py) e salva a escolha via
# `salvar_sharepoint_dir()` acima, que é verificada aqui ANTES do palpite.
# Pra quem já tem a estrutura padrão (o palpite bate), nada muda - nunca
# precisa escolher nada.
SHAREPOINT_DIR = _carregar_sharepoint_dir_configurado() or (Path.home() / "OneDrive - Yara International ASA" / "Dados ANTT")
DOWNLOAD_DIR = SHAREPOINT_DIR / "Autos"
PLANILHA_PATH = SHAREPOINT_DIR / "Relatorio_Multas.xlsx"

VISTAS_URL = "https://appweb1.antt.gov.br/spmi/Site/Acessos/VistasAoProcesso.aspx"

# Caminhos por worker (arquitetura de múltiplos workers, 17/09/2026 - ver
# CLAUDE.md e o plano da sessão). Cada worker tem sua própria sessão,
# checkpoint e planilha "fatia" LOCAL (nunca no SharePoint) - evita qualquer
# concorrência de escrita entre processos. A consolidação numa planilha só
# (a de verdade, no SharePoint) é feita à parte por
# scripts/consolidar_planilhas.py, que é o único escritor desse arquivo
# compartilhado.
SESSAO_DIR = BASE_DIR / "data" / "sessao"


def sessao_worker(worker_id: int) -> Path:
    return SESSAO_DIR / f"sessao_worker_{worker_id}.json"


def checkpoint_worker(worker_id: int) -> Path:
    return OUTPUT_DIR / f"checkpoint_worker_{worker_id}.json"


def planilha_worker(worker_id: int) -> Path:
    return OUTPUT_DIR / f"planilha_worker_{worker_id}.xlsx"

# Pausa deliberada (ms) entre ações que batem no servidor (troca de tipo de
# fiscalização, próxima página, próximo CNPJ). Achado em 16/09/2026: baterias
# de requisições em sequência rápida deixaram o portal visivelmente mais lento
# e instável (page.goto chegando a travar 60s+). Não é otimização - é pra não
# sobrecarregar um sistema de governo real. Ver "Achados operacionais" no
# CLAUDE.md antes de reduzir esse valor.
PAUSA_ENTRE_ACOES_MS = 2000

# --- Timeouts e contagens de retentativa do portal/download ---------------
# Centralizados aqui em 24/09/2026 (revisão crítica pedida pelo usuário):
# antes, cada valor era um default de parâmetro espalhado inline em
# portal.py/download.py - ajustar qualquer um deles (ex.: se o portal ficar
# mais lento no futuro) exigia caçar em vários arquivos/funções diferentes.
# Cada valor abaixo mantém o número original (nenhum comportamento muda),
# só a localização - o histórico/motivo de cada um continua documentado no
# docstring da função que o usa em portal.py/download.py.
TIMEOUT_GOTO_TELA_PROCESSOS_MS = 60000
TIMEOUT_SELETOR_TELA_PROCESSOS_MS = 30000
TENTATIVAS_ABRIR_TELA_PROCESSOS = 3

TENTATIVAS_CONFIRMAR_CNPJ = 10
INTERVALO_CONFIRMAR_CNPJ_MS = 500

TIMEOUT_MODAL_PROCESSANDO_MS = 30000
TIMEOUT_MODAL_CONFIRMACAO_DOWNLOAD_MS = 45000
TIMEOUT_MODAL_CONFIRMACAO_DOWNLOAD_OPCIONAL_MS = 2000
TIMEOUT_MODAL_MENSAGEM_GENERICA_MS = 2000
TIMEOUT_MODAL_MENSAGEM_GENERICA_FECHAR_MS = 15000

TIMEOUT_PROCESSAMENTO_GRANDE_VISIVEL_MS = 5000
TIMEOUT_PROCESSAMENTO_GRANDE_OCULTO_MS = 600000  # 10min - ver _esperar_processamento_grande() em portal.py

TIMEOUT_TABELA_MUDAR_MS = 30000
TENTATIVAS_BUSCAR = 3
TENTATIVAS_PROXIMA_PAGINA = 3

TENTATIVAS_LOCALIZAR_LINHA = 3
TIMEOUT_LOCALIZAR_LINHA_MS = 5000
# 60s -> 180s -> 75s (ver histórico completo em download.py, baixar_pdf()) -
# valor final decidido em 23/09/2026 com base em evidência real de produção.
TIMEOUT_DOWNLOAD_MS = 75000

# Seletores confirmados em 15/09/2026 a partir do outerHTML real do portal
# (ver codigos_site/vistas_ao_processo.docx e codigos_site/tabela_pesquisar.txt).
# O portal é ASP.NET WebForms — os ids reais têm o prefixo "Corpo_".
SEL = {
    "representado": "#Corpo_ddlRepresentado",
    "tipo_fiscalizacao": "#Corpo_ddlTipoFiscalizacao",
    "auto_infracao": "#Corpo_txbAutoInfracao",
    "numero_processo": "#Corpo_txtGedProcesso",
    "btn_pesquisar": "#Corpo_btnPesquisar",
    "btn_limpar": "#Corpo_btnLimpar",
    "tabela_resultado": "#Corpo_gdvResultado",
    "paginador_info": "#Corpo_ucPaginadorResultado li.info",
    "paginador_proxima": "#Corpo_ucPaginadorResultado_ucPaginadorResultado_lbNextPage",
    "representado_chosen": "#Corpo_ddlRepresentado_chosen",
    "modal_processando": "#Progress_DivProgress",
    # modal de confirmação que aparece DEPOIS de cada download (clique na
    # lupa) - "Vistas ao Processo Solicitada com Sucesso!" + pesquisa de
    # satisfação. Fica aberto até ser fechado e bloqueia o próximo clique
    # (achado ao vivo em 16/09/2026 - ver baixar_pdf() em download.py).
    "modal_confirmacao_download": "#divMensagemPesquisa",
    "modal_confirmacao_nao_responder": "#MessageBoxPesquisa_rdbNao",
    "modal_confirmacao_ok": "#MessageBoxPesquisa_ButtonOkPesquisa",
    # modal de mensagem GENÉRICO do portal (erro/aviso do servidor) - visto
    # ao vivo em 16/09/2026 (teste em escala maior) bloqueando cliques depois
    # de alguns downloads que vieram com problema (ver "Achados" no
    # CLAUDE.md). Id do botão Ok inferido pelo mesmo padrão de nomenclatura
    # do modal_confirmacao_ok (MessageBox_ButtonOk / MessageBoxPesquisa_ButtonOkPesquisa)
    # - ainda não confirmado com outerHTML capturado ao vivo dessa modal específica.
    "modal_mensagem_generica": "#divMensagem",
    "modal_mensagem_generica_ok": "#MessageBox_ButtonOk",
}

# Valores reais do <select id="Corpo_ddlTipoFiscalizacao"> (capturados em 15/09/2026).
# Buscar com esse campo em branco TRAVA no servidor (testado ao vivo em 16/09/2026,
# "Processando..." nunca termina) - por isso a varredura precisa iterar por esses
# valores. Cobre também os tipos de multa vistos nos PDFs de exemplo que não têm
# opção própria no dropdown (ex.: Piso Mínimo de Frete, Produtos Perigosos e
# Vale-Pedágio parecem cair todos dentro de "Cargas", a julgar pelo prefixo comum
# CRG*/FEL* dos números de auto) - ainda não 100% confirmado, ver CLAUDE.md.
TIPOS_FISCALIZACAO = {
    "2": "Excesso de Peso",
    "3": "Cargas",
    "4": "Passageiros",
    "5": "Cargas Internacional",
    "7": "Passageiros Internacional",
    "8": "Infraestrutura Rodoviária",
    "9": "Evasão de Pedágio",
}
