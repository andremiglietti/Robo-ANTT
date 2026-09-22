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

import pymupdf
import pdfplumber


def _para_float_brasileiro(valor: str) -> float:
    """Converte "1.234,56" (formato brasileiro: ponto = milhar, vírgula =
    decimal) pra float. Levanta ValueError se não for um número válido -
    usado no fallback de subtração de extrair_campos_boleto()."""
    return float(valor.replace(".", "").replace(",", "."))


def _de_float_pra_brasileiro(valor: float) -> str:
    """Inverso de _para_float_brasileiro() - sempre 2 casas decimais."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


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


def _celulas_da_pagina(pdf_path: Path, indice_pagina: int = 0) -> list[str]:
    """O PDF é um formulário com bordas - cada célula da tabela contém
    "NÚMERO - RÓTULO\nVALOR" (rótulo e valor empilhados na mesma célula).
    Isso é bem mais confiável pra extrair campo por campo do que regex em
    cima do texto corrido (a ordem de leitura do texto corrido não segue o
    layout visual - testado em 16/09/2026, ver docstring do módulo).
    `indice_pagina` é 0-based (0 = página 1)."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        tabelas = pdf.pages[indice_pagina].extract_tables()
    celulas = []
    for tabela in tabelas:
        for linha in tabela:
            for celula in linha:
                if celula:
                    # ⚠️ Achado em 22/09/2026 (ver CLAUDE.md): um subconjunto de
                    # PDFs usa hífen suave (U+00AD, "soft hyphen" - invisível,
                    # não é o "-" normal) como separador entre o número do
                    # campo e o rótulo (ex.: "01\xadPLACA" em vez de
                    # "01 - PLACA"). Como \xad não é espaço nem "-" de verdade,
                    # as regex de _valor_do_campo() (que esperam um hífen
                    # literal) não batiam nesses documentos - causava campos
                    # inteiros (placa, data, descrição) voltando None em
                    # documentos que na verdade TÊM o dado. Normaliza pra "-"
                    # aqui, na origem, pra corrigir todo campo de uma vez.
                    celulas.append(celula.replace("\xad", "-").strip())
    return celulas


def _valor_de_celula_rotulo_multilinha(celulas: list[str], padrao_rotulo: str) -> str | None:
    """Como _valor_do_campo, mas pra células cujo RÓTULO em si ocupa mais de
    1 linha (ex.: `"VALOR COM\nDESCONTO(R$)\n80,87"` - `_valor_do_campo()`
    quebra no 1º "\n" e trataria "DESCONTO(R$)\n80,87" como o "valor", o que
    é errado). Aqui a busca do rótulo é feita no texto inteiro da célula
    (espaços normalizados), e o "valor" é sempre a ÚLTIMA linha da célula -
    só devolve algo se essa última linha parecer mesmo um número (evita
    devolver lixo se a suposição "última linha = valor" não bater)."""
    for celula in celulas:
        texto_normalizado = re.sub(r"\s+", " ", celula)
        if not re.search(padrao_rotulo, texto_normalizado, re.IGNORECASE):
            continue
        candidato = celula.rsplit("\n", 1)[-1].strip()
        if re.fullmatch(r"[\d.,]+", candidato):
            return candidato
    return None


def _ultimo_valor_do_campo(celulas: list[str], padrao_rotulo: str) -> str | None:
    """Como _valor_do_campo, mas devolve a ÚLTIMA célula que bate (não a
    primeira) - usado quando o mesmo rótulo aparece mais de uma vez na
    página e o campo que interessa é o último (ex.: "DATA DE EMISSÃO"
    aparece 2x na página do boleto em alguns layouts - a primeira é do
    documento fiscal, repetida; a última é do boleto em si)."""
    encontrado = None
    for celula in celulas:
        partes = celula.split("\n", 1)
        if len(partes) != 2:
            continue
        rotulo, valor = partes
        if re.fullmatch(padrao_rotulo, rotulo.strip(), re.IGNORECASE):
            encontrado = re.sub(r"\s+", " ", valor).strip()
    return encontrado


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
    celulas = _celulas_da_pagina(pdf_path, 0)
    cnpj_infrator = _valor_do_campo(celulas, r"CNPJ\s*/\s*CPF|CPF\s*/\s*CNPJ")
    if cnpj_infrator:
        # em valores estreitos o CNPJ pode quebrar linha no meio (ex.: "...0002-\n63"),
        # e a normalização de espaço em _valor_do_campo deixa um espaço solto ali -
        # CNPJ nunca tem espaço de verdade, então é seguro remover.
        cnpj_infrator = cnpj_infrator.replace(" ", "")
    return {
        # prefixo numérico ("01 - ") normalmente presente, mas opcional -
        # achado em 22/09/2026: alguns layouts (tipo ainda não mapeado, cai
        # em "Outros") têm a célula só "PLACA\n<valor>", sem numeração.
        "placa": _valor_do_campo(celulas, r"^\d*\s*-?\s*PLACA"),
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


# "Linha digitável" do código de barras do boleto/GRU: 3 dígitos do banco +
# dígito verificador, depois 4 blocos separados por espaço/ponto, terminando
# num bloco de 14 dígitos. Ex.: "001-9 00190.00009 02941.141109 24294.819172 2 79650000199216".
_PADRAO_CODIGO_BARRAS = re.compile(r"\d{3}-\d\s+\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14}")


def localizar_pagina_boleto(pdf_path: Path) -> int | None:
    """Acha o número da página (1-based) do boleto/1ª notificação de
    penalidade, procurando "NOSSO NÚMERO" + "VENCIMENTO" juntos (específico
    o bastante pra não confundir com outras páginas do processo que só
    mencionam "multa"/"vencimento" no meio de texto jurídico genérico -
    achado em 16/09/2026).

    Usa PyMuPDF (`pymupdf`) em vez de pdfplumber pra essa busca porque é MUITO
    mais rápido pra varrer o documento inteiro (~30 páginas em 0,5s contra
    quase 50s do pdfplumber - testado em 16/09/2026) - importante porque
    processos reais podem ter até ~79 páginas, e o boleto pode estar bem no
    fim (visto na página 57 de 69 num dos exemplos).

    Retorna None se o processo não tem boleto ainda - isso é normal (ex.:
    recurso ainda não julgado), não é erro. Ver CLAUDE.md, item 5.
    """
    doc = pymupdf.open(str(pdf_path))
    try:
        for indice, pagina in enumerate(doc):
            texto = pagina.get_text().upper()
            if "NOSSO N" in texto and "VENCIMENTO" in texto:
                return indice + 1
    finally:
        doc.close()
    return None


def extrair_campos_boleto(pdf_path: Path, numero_pagina: int) -> dict:
    """Extrai os campos do boleto (`numero_pagina` é 1-based - ver
    localizar_pagina_boleto). Usa regex no texto corrido, não nas células da
    tabela como extrair_campos_pagina1 - o boleto tem pelo menos 2 layouts
    bem diferentes entre os tipos de multa vistos até agora (o do "auto de
    trânsito" clássico e o da GRU - Guia de Recolhimento da União), mas as
    duas variações têm as mesmas frases-âncora no texto corrido.
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        texto = pdf.pages[numero_pagina - 1].extract_text() or ""

    m_vencimento = re.search(r"DATA DO VENCIMENTO\s+(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    m_codigo_barras = _PADRAO_CODIGO_BARRAS.search(texto)

    # "DATA DE EMISSÃO" aparece 2x nessa página em alguns layouts (a do
    # documento fiscal, repetida, e a do boleto/notificação em si) - a do
    # boleto é sempre a ÚLTIMA ocorrência. Usa as células da tabela (não
    # regex no texto corrido, que aqui agrupa os rótulos longe dos valores -
    # achado em 16/09/2026) pra achar esse campo com confiança.
    celulas = _celulas_da_pagina(pdf_path, numero_pagina - 1)
    data_emissao_boleto = _ultimo_valor_do_campo(celulas, r"\d*\s*-?\s*DATA\s+(?:DE\s+)?EMISS.O")

    # ⚠️ Achado em 22/09/2026 (ver CLAUDE.md): "valor" usava regex no texto
    # corrido - achado real: num sub-layout GRU de 3 colunas, o texto corrido
    # intercala colunas, e entre o rótulo "VALOR TOTAL DA MULTA(R$)" e o
    # valor de verdade (ex.: "146,12") aparece o CNPJ de uma coluna vizinha
    # ("...PELO CNPJ Nº 92.660.604/0171-58") - a regex antiga capturava esse
    # CNPJ por engano, um bug de CORREÇÃO (dado errado na planilha), não só
    # de completude. Trocado pra extração por células (como já era feito pra
    # data_emissao_boleto acima) - a célula "RÓTULO\nVALOR" nunca tem esse
    # problema de intercalação de coluna. Cascata de rótulos, do mais
    # específico ao mais genérico (visto nos layouts reais): "VALOR TOTAL DA
    # MULTA" (clássico) -> "VALOR DA MULTA" (GRU produtos perigosos) ->
    # "Valor" sozinho (rótulo genérico da ficha de compensação bancária,
    # presente e correto em TODOS os exemplos vistos até agora).
    valor = (
        _valor_do_campo(celulas, r"VALOR\s+TOTAL\s+DA\s+MULTA")
        or _valor_do_campo(celulas, r"VALOR\s+DA\s+MULTA")
        or _valor_do_campo(celulas, r"^Valor$", exato=True)
    )
    if valor:
        # célula pode vir com "R$ " embutido no valor (ex.: "VALOR DA MULTA\nR$ 1.400,00") - remove.
        valor = re.sub(r"R\$\s*", "", valor).strip()

    # ⚠️ Achado em 22/09/2026 (mesma família do bug de "valor" acima): a
    # regex de texto corrido pra "Desconto/Abatimento" também captura lixo
    # em alguns layouts - achados reais: valor virando só "," (célula
    # "2 - (-) Desconto / Abatimento" sem nenhum valor depois, num layout
    # antigo) ou só "4" (fragmento truncado, layout GRU onde a célula
    # "2 - (-) DESCONTO / ABATIMENTO\n420,00" tem o valor limpo, mas o texto
    # corrido intercala algo entre o rótulo e o valor de verdade).
    # Cascata: (1) célula "Desconto/Abatimento" direta - mais confiável,
    # igual ao fix de "valor"; (2) frase "conceder desconto de R$ X" no
    # texto corrido - necessária pro layout onde o boleto inteiro vem como
    # 1 célula gigante sem separação rótulo/valor (ex.: piso_minimo.pdf);
    # (3) rótulo "Desconto/Abatimento" no texto corrido; (4) cálculo por
    # subtração (Valor - Valor com Desconto) - achado em 68 de 83 casos
    # auditados: documentos antigos (numeração só numérica, ex.:
    # "0001443878") têm a célula "Desconto/Abatimento" genuinamente SEM
    # valor nenhum (nem no texto corrido) - só a célula "VALOR COM
    # DESCONTO(R$)" tem um número de verdade, e o desconto em si (pela
    # definição já confirmada em 15/09/2026: "valor do desconto, não o
    # total já com desconto aplicado") precisa ser calculado.
    # ⚠️ checa "tem pelo menos 1 dígito", não só "não é None" - uma célula
    # sem valor nenhum depois do rótulo pode produzir uma string vazia-ish
    # tipo "," (visto ao vivo), que é truthy em Python mas não é um número.
    def _parece_numero(v: str | None) -> bool:
        return bool(v) and bool(re.search(r"\d", v))

    valor_desconto = _valor_do_campo(celulas, r"\d*\s*-?\s*DESCONTO\s*/\s*ABATIMENTO")
    if not _parece_numero(valor_desconto):
        m_desconto = re.search(r"desconto\s+de\s+R\$\s*([\d.,]+)", texto, re.IGNORECASE)
        if not m_desconto:
            m_desconto = re.search(r"Desconto\s*/\s*Abatimento\D{0,10}?([\d.,]+)", texto, re.IGNORECASE)
        valor_desconto = m_desconto.group(1) if m_desconto else None
    if not _parece_numero(valor_desconto) and valor:
        valor_com_desconto = _valor_de_celula_rotulo_multilinha(celulas, r"VALOR\s+COM\s+DESCONTO")
        if valor_com_desconto:
            try:
                diferenca = _para_float_brasileiro(valor) - _para_float_brasileiro(valor_com_desconto)
                valor_desconto = _de_float_pra_brasileiro(diferenca)
            except ValueError:
                pass
    if not _parece_numero(valor_desconto):
        # nenhuma das 4 tentativas achou um número de verdade - devolve
        # None (célula vazia na planilha) em vez de lixo tipo "," ou "4".
        valor_desconto = None

    return {
        "data_vencimento": m_vencimento.group(1) if m_vencimento else None,
        "codigo_barras": m_codigo_barras.group().strip() if m_codigo_barras else None,
        "valor_desconto": valor_desconto,
        "valor": valor,
        "data_emissao_boleto": data_emissao_boleto,
    }


def localizar_pagina_notificacao(pdf_path: Path) -> int | None:
    """Acha o número da página (1-based) da "Notificação da Autuação" -
    página que vem antes do boleto e tem sua própria "Data de Emissão"
    (diferente da data de emissão do documento fiscal, da página 1, e da
    data de emissão do boleto - são 3 datas de emissão diferentes, cada uma
    numa página).

    ⚠️ Começa a procurar a partir da **página 2**, nunca a 1: a página 1 de
    vários tipos de auto menciona "notificação de autuação" de passagem,
    dentro de uma frase jurídica (ex.: "...contados do recebimento da
    notificação de autuação..."), o que dava falso positivo (achado em
    16/09/2026) - a notificação de verdade, com campos próprios, está
    sempre numa página separada.

    Mesma técnica de localizar_pagina_boleto (PyMuPDF, rápido o bastante pra
    varrer o documento inteiro). Pode devolver None se não achar (nesse caso
    o campo fica em branco na planilha, não é erro).
    """
    doc = pymupdf.open(str(pdf_path))
    try:
        for indice, pagina in enumerate(doc):
            if indice == 0:
                continue
            texto = pagina.get_text().upper()
            if "NOTIFICA" in texto and "AUTUA" in texto:
                return indice + 1
    finally:
        doc.close()
    return None


def extrair_data_emissao_notificacao(pdf_path: Path, numero_pagina: int) -> str | None:
    """Data de emissão da página de notificação (ver localizar_pagina_notificacao).
    Pega a ÚLTIMA célula "DATA DE EMISSÃO" da página - a primeira, quando
    existe mais de uma, costuma ser a repetição da data de emissão do
    documento fiscal (já capturada em extrair_campos_pagina1)."""
    celulas = _celulas_da_pagina(pdf_path, numero_pagina - 1)
    return _ultimo_valor_do_campo(celulas, r"\d*\s*-?\s*DATA\s+(?:DE\s+)?EMISS.O")
