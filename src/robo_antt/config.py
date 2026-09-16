from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SESSION_FILE = BASE_DIR / "data" / "sessao" / "sessao_antt.json"
DOWNLOAD_DIR = BASE_DIR / "data" / "downloads"
OUTPUT_DIR = BASE_DIR / "data" / "output"

VISTAS_URL = "https://appweb1.antt.gov.br/spmi/Site/Acessos/VistasAoProcesso.aspx"

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
