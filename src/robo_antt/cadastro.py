"""
Mapeamento CNPJ -> Apelido, lido da planilha de cadastro fornecida pelo
time (`docs/CNPJ Dados cadastrais das Unidades.xlsb`) - pedido em reunião
com o time, 25/09/2026: "colocar junto ao nome da pasta do CNPJ o
Apelido".

Usado só pra nomear as pastas de download de forma mais legível pra quem
navega manualmente em `Autos/` (ex.: "92660604012784 - VIX3" em vez de só
o número) - não afeta nenhuma lógica de negócio (busca no portal, chave
de duplicidade etc. continuam usando o CNPJ puro em todo lugar).
"""
import re
from pathlib import Path

from pyxlsb import open_workbook

from robo_antt.config import BASE_DIR

CADASTRO_PATH = BASE_DIR / "docs" / "CNPJ Dados cadastrais das Unidades.xlsb"

_cache: dict[str, str] | None = None


def _normalizar_cnpj(valor) -> str | None:
    """A coluna CNPJ na planilha vem com tipos misturados - número puro
    (float, ex.: 92660604012784.0) na maioria das linhas, mas string já
    formatada (ex.: "92.660.604/0173-10") em algumas - achado ao vivo em
    25/09/2026, inspecionando o arquivo real. Normaliza os 2 formatos pro
    mesmo padrão usado no resto do projeto (só dígitos, zero-padded 14
    posições)."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return str(int(valor)).zfill(14)
    apenas_digitos = re.sub(r"\D", "", str(valor))
    return apenas_digitos.zfill(14) if apenas_digitos else None


def carregar_apelidos(caminho: Path = CADASTRO_PATH) -> dict[str, str]:
    """{cnpj: apelido} juntando as 2 abas da planilha ("CNPJ ATIVOS YARA" +
    "CNPJ BAIXADOS") - lida e cacheada 1x por processo (a planilha não
    muda durante uma execução, e cada worker é seu próprio processo, então
    o cache é naturalmente por worker, sem risco de ficar desatualizado
    entre eles).

    Se o arquivo não existir (ex.: alguém rodando numa cópia do projeto
    sem `docs/` completo), devolve `{}` - achar um apelido é sempre
    OPCIONAL, nunca bloqueia o robô (ver nome_pasta_cnpj())."""
    global _cache
    if _cache is not None:
        return _cache
    if not caminho.exists():
        _cache = {}
        return _cache

    apelidos: dict[str, str] = {}
    with open_workbook(str(caminho)) as wb:
        for nome_aba in wb.sheets:
            with wb.get_sheet(nome_aba) as sheet:
                for linha in sheet.rows():
                    if not linha or len(linha) < 2:
                        continue
                    cnpj = _normalizar_cnpj(linha[0].v)
                    apelido = linha[1].v
                    # linha de cabeçalho ("CNPJ"/"Apelido") normaliza pra
                    # cnpj=None (sem dígito nenhum) - filtrada aqui sem
                    # precisar pular por posição de linha.
                    if cnpj and isinstance(apelido, str) and apelido.strip():
                        apelidos[cnpj] = apelido.strip()
    _cache = apelidos
    return apelidos


def nome_pasta_cnpj(cnpj: str, caminho_cadastro: Path = CADASTRO_PATH) -> str:
    """"{cnpj} - {apelido}" se o apelido for conhecido, senão só o CNPJ.

    ⚠️ Achado ao vivo em 25/09/2026: 3 dos 37 CNPJs já vistos pelo robô
    (92660604011540, 92660604013594, 92660604014051) não têm entrada na
    planilha de cadastro - o fallback sem apelido é um caso real, não só
    teórico, e precisa continuar funcionando (nunca falhar por causa de
    um CNPJ que a planilha de cadastro não conhece ainda)."""
    apelido = carregar_apelidos(caminho_cadastro).get(cnpj)
    return f"{cnpj} - {apelido}" if apelido else cnpj
