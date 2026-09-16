"""
Extração de campos do PDF do auto de infração.

⚠️ Achado em 16/09/2026: o PDF do portal tem um problema de fonte - qualquer
biblioteca de extração de texto (testamos pypdf, pdfplumber e PyMuPDF, todas
com o mesmo resultado) devolve "�" no lugar de vogais acentuadas. Não é bug
das bibliotecas, é o PDF em si. Os campos numéricos/sem acento (placa, CNPJ,
datas, valores, números de documento) extraem perfeitamente; só texto livre
acentuado (descrição da infração, o nome do tipo de multa no cabeçalho) vem
degradado. Por isso a identificação do tipo de multa usa trechos SEM acento
como palavra-chave (ex.: "PESO", "FRETE", "PERIGOSOS", "VALE"), em vez de
comparar a string inteira.
"""
import re
from pathlib import Path

import pdfplumber


def extrair_texto_pagina1(pdf_path: Path) -> str:
    """Extrai o texto da página 1 (onde ficam os campos estruturados do auto -
    ver CLAUDE.md, item 5 da arquitetura: página 1 sempre tem o essencial,
    mesmo em processos com dezenas de páginas de histórico)."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        return pdf.pages[0].extract_text() or ""


# Palavras-chave sem acento por tipo de multa, na ordem em que devem ser
# testadas (a primeira que bater vence). Baseado nos 5 exemplos reais
# analisados em 15-16/09/2026. Tipos que ainda não vimos exemplo real
# (Cargas Internacional, Passageiros, Infraestrutura Rodoviária, Evasão de
# Pedágio) caem em "Outros" até termos um PDF de exemplo pra mapear a
# palavra-chave certa.
_PALAVRAS_CHAVE_TIPO_MULTA = [
    ("PESO", "Excesso de Peso"),
    ("FRETE", "Piso Mínimo de Frete"),
    ("PERIGOSOS", "Produtos Perigosos"),
    ("VALE", "Vale-Pedágio"),
]


def identificar_tipo_multa(texto_pagina1: str) -> str:
    """Lê o cabeçalho "AUTO DE INFRAÇÃO ..." da página 1 e classifica o tipo
    de multa usando palavras-chave sem acento (ver docstring do módulo).
    Usado pra decidir em qual pasta salvar o PDF (data/downloads/{cnpj}/{tipo}/).
    """
    m = re.search(r"AUTO DE INFRA.{2}O\s+(.{0,80})", texto_pagina1, re.IGNORECASE)
    trecho = m.group(1).upper() if m else texto_pagina1[:80].upper()

    for palavra_chave, tipo in _PALAVRAS_CHAVE_TIPO_MULTA:
        if palavra_chave in trecho:
            return tipo

    return "Outros"  # tipo ainda não mapeado - revisar manualmente


def _celulas_pagina1(pdf_path: Path) -> list[str]:
    """O PDF é um formulário com bordas - cada célula da tabela contém
    "NÚMERO - RÓTULO\nVALOR" (rótulo e valor empilhados na mesma célula).
    Isso é bem mais confiável pra extrair campo por campo do que regex em
    cima do texto corrido (a ordem de leitura do texto corrido não segue o
    layout visual - testado em 16/09/2026, ver docstring do módulo)."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        tabelas = pdf.pages[0].extract_tables()
    celulas = []
    for tabela in tabelas:
        for linha in tabela:
            for celula in linha:
                if celula:
                    celulas.append(celula.strip())
    return celulas


def _valor_do_campo(celulas: list[str], padrao_rotulo: str, exato: bool = False) -> str | None:
    """Acha a primeira célula cujo rótulo (a parte antes da primeira quebra
    de linha) bate com `padrao_rotulo` (regex, sem diferenciar maiúscula/
    minúscula) e devolve o valor (o resto da célula, com quebras de linha
    internas normalizadas pra espaço - alguns valores longos/estreitos vêm
    com quebra de linha no meio, ex.: CNPJ quebrado em duas linhas). `exato=True`
    exige que o rótulo inteiro bata (não só uma parte) - importante pra não
    confundir "DATA" com "DATA DE EMISSÃO", por exemplo.
    """
    for celula in celulas:
        partes = celula.split("\n", 1)
        if len(partes) != 2:
            continue
        rotulo, valor = partes
        bate = (
            re.fullmatch(padrao_rotulo, rotulo.strip(), re.IGNORECASE)
            if exato
            else re.search(padrao_rotulo, rotulo, re.IGNORECASE)
        )
        if bate:
            return re.sub(r"\s+", " ", valor).strip()
    return None


def extrair_campos_pagina1(pdf_path: Path) -> dict:
    """Extrai os campos da página 1 que são comuns aos 5 tipos de multa
    analisados (ver CLAUDE.md, item 5 da arquitetura). Campos com texto
    livre acentuado (descrição) saem com "�" no lugar de vogais acentuadas -
    limitação conhecida do PDF do portal, não desse código.
    """
    celulas = _celulas_pagina1(pdf_path)
    cnpj_infrator = _valor_do_campo(celulas, r"CNPJ\s*/\s*CPF|CPF\s*/\s*CNPJ")
    if cnpj_infrator:
        # em valores estreitos o CNPJ pode quebrar linha no meio (ex.: "...0002-\n63"),
        # e a normalização de espaço em _valor_do_campo deixa um espaço solto ali -
        # CNPJ nunca tem espaço de verdade, então é seguro remover.
        cnpj_infrator = cnpj_infrator.replace(" ", "")
    return {
        "placa": _valor_do_campo(celulas, r"^\d+\s*-\s*PLACA"),
        "cnpj_infrator": cnpj_infrator,
        # "DATA" sozinho (a data da infração) - exato, pra não confundir com
        # "DATA DE EMISSÃO" ou "DATA DA EXPEDIÇÃO", que são campos diferentes.
        # Inclui o prefixo numérico do campo ("28 - DATA") no próprio padrão,
        # já que o rótulo real sempre vem com ele.
        "data_autuacao": _valor_do_campo(celulas, r"\d*\s*-?\s*DATA", exato=True),
        "descricao_infracao": _valor_do_campo(
            celulas, r"\d*\s*-?\s*DESCRI.{1,2}O(?:\s*D[AO]\s*INFRA.{2}O)?", exato=True
        ),
        # "TIPO DE DOCUMENTO" em alguns tipos de auto, "TIPO DO DOCUMENTO" em outros
        "tipo_documento_fiscal": _valor_do_campo(celulas, r"TIPO\s+D[EO]\s*DOCUMENTO"),
        # rótulo varia entre "Nº DO DOCUMENTO" e "NÚMERO DO DOCUMENTO"
        "numero_documento_fiscal": _valor_do_campo(celulas, r"N[^\s]{0,6}\s+DO\s+DOCUMENTO"),
        # varia entre "DATA EMISSÃO" e "DATA DE EMISSÃO"
        "data_emissao_doc_fiscal": _valor_do_campo(celulas, r"DATA\s+(?:DE\s+)?EMISS.O"),
    }
