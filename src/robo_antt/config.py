from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SESSION_FILE = BASE_DIR / "data" / "sessao" / "sessao_antt.json"
# Estado interno do robô (checkpoint) - fica LOCAL, não sincronizado com o
# SharePoint: é só memória de execução do robô, não é entregável pra ninguém
# ler, e escrever nele com frequência (a cada CNPJ) numa pasta do OneDrive
# geraria sincronização o tempo todo à toa.
OUTPUT_DIR = BASE_DIR / "data" / "output"

# Pasta sincronizada com o OneDrive/SharePoint - aqui vai o que É entregável:
# os PDFs baixados (organizados por CNPJ/tipo de multa) e a planilha final.
# Caminho confirmado pelo usuário em 16/09/2026.
SHAREPOINT_DIR = Path(r"C:\Users\a847468\OneDrive - Yara International ASA\Dados ANTT")
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
