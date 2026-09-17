"""
Geração/atualização da planilha Excel final com os dados de todas as multas.

Uso típico (ver CLAUDE.md, item 7 da arquitetura):
    wb = abrir_ou_criar(caminho)
    for cada multa nova encontrada:
        if not ja_registrado(wb, registro["auto_infracao"]):
            adicionar_registro(wb, registro)
    salvar(wb, caminho)  # só grava no final, com o cuidado de arquivo temporário
"""
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

NOME_ABA = "Multas"

# Ordem e nomes das colunas definidos com o usuário em 15/09/2026 (ver
# CLAUDE.md, item 7 da arquitetura) - não reordenar sem necessidade, já que
# a pessoa que usa a planilha pode ter filtros/fórmulas montados em cima
# dessa ordem depois da entrega.
COLUNAS = [
    "Link do Arquivo",
    "Número do Processo",
    "Auto de Infração",
    "Tipo de Multa",
    "CNPJ",
    "Data Autuação",
    "Data Emissão Doc. Fiscal",
    "Data Emissão Notificação",
    "Data Emissão Boleto",
    "Data Vencimento",
    "Valor",
    "Valor Desconto",
    "Placa",
    "Descrição da Infração",
    "Código de Barras",
]

# Mapeia o nome da coluna pro nome do campo usado no resto do código
# (portal.py, download.py, extracao.py já usam esses nomes de campo).
_CAMPO_POR_COLUNA = {
    "Link do Arquivo": "link_arquivo",
    "Número do Processo": "numero_processo",
    "Auto de Infração": "auto_infracao",
    "Tipo de Multa": "tipo_multa",
    "CNPJ": "cnpj",
    "Data Autuação": "data_autuacao",
    "Data Emissão Doc. Fiscal": "data_emissao_doc_fiscal",
    "Data Emissão Notificação": "data_emissao_notificacao",
    "Data Emissão Boleto": "data_emissao_boleto",
    "Data Vencimento": "data_vencimento",
    "Valor": "valor",
    "Valor Desconto": "valor_desconto",
    "Placa": "placa",
    "Descrição da Infração": "descricao_infracao",
    "Código de Barras": "codigo_barras",
}

_COLUNA_AUTO_INFRACAO = COLUNAS.index("Auto de Infração") + 1  # openpyxl é 1-based


def abrir_ou_criar(caminho: Path) -> Workbook:
    """Abre a planilha existente (preservando o que já tem), ou cria uma nova
    com o cabeçalho, se ainda não existir."""
    if caminho.exists():
        return load_workbook(str(caminho))

    wb = Workbook()
    ws = wb.active
    ws.title = NOME_ABA
    ws.append(COLUNAS)
    return wb


def _aba(wb: Workbook) -> Worksheet:
    if NOME_ABA in wb.sheetnames:
        return wb[NOME_ABA]
    return wb.active


def ja_registrado(wb: Workbook, auto_infracao: str) -> bool:
    """Confere se esse auto já está na planilha, pra não duplicar linha numa
    execução futura do robô (a checagem de arquivo em download.py evita
    baixar o PDF de novo; esta aqui evita duplicar a linha na planilha,
    inclusive se o PDF já existia de uma execução anterior)."""
    ws = _aba(wb)
    for linha in ws.iter_rows(min_row=2, min_col=_COLUNA_AUTO_INFRACAO, max_col=_COLUNA_AUTO_INFRACAO):
        if linha[0].value == auto_infracao:
            return True
    return False


def registro_da_linha(linha: tuple) -> dict:
    """Inverso de adicionar_registro(): dado os valores de uma linha da
    planilha (na ordem de COLUNAS), devolve o dict com as chaves de campo
    (auto_infracao, cnpj, valor, etc.). Usado por
    scripts/consolidar_planilhas.py pra reler as planilhas-fatia de cada
    worker (arquitetura de múltiplos workers, 17/09/2026) e mesclar na
    planilha final com adicionar_registro()."""
    return {_CAMPO_POR_COLUNA[coluna]: valor for coluna, valor in zip(COLUNAS, linha)}


def adicionar_registro(wb: Workbook, registro: dict) -> None:
    """Adiciona uma linha nova com os dados de uma multa. `registro` é um
    dict com as chaves em _CAMPO_POR_COLUNA.values() (auto_infracao, cnpj,
    valor, etc.) - chaves ausentes viram célula em branco, não erro."""
    ws = _aba(wb)
    linha = [registro.get(_CAMPO_POR_COLUNA[coluna]) for coluna in COLUNAS]
    ws.append(linha)


def salvar(wb: Workbook, caminho_final: Path) -> None:
    """Salva a planilha com o mesmo cuidado da gravação de qualquer arquivo
    na pasta sincronizada com o SharePoint (ver CLAUDE.md, "Cuidado técnico
    na gravação"): escreve num arquivo temporário primeiro e só then troca
    pelo arquivo final, pra nunca deixar a pasta com um .xlsx pela metade
    caso o OneDrive tente sincronizar no meio da escrita.
    """
    caminho_final.parent.mkdir(parents=True, exist_ok=True)
    caminho_tmp = caminho_final.with_name(f"_tmp_{caminho_final.name}")
    wb.save(str(caminho_tmp))
    caminho_tmp.replace(caminho_final)
