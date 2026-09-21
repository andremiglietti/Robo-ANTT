"""
Gravação segura de arquivos em pastas sincronizadas com o OneDrive/SharePoint
(ver CLAUDE.md, "Cuidado técnico na gravação").

Usado por checkpoint.py e planilha.py, que gravam do mesmo jeito: escrevem
num arquivo temporário primeiro e só then trocam pelo arquivo final, pra
nunca deixar a pasta com um arquivo pela metade caso o OneDrive tente
sincronizar no meio da escrita.
"""
import time
from pathlib import Path


def substituir_com_retentativa(origem: Path, destino: Path, tentativas: int = 5, espera_segundos: float = 1.0) -> None:
    """Troca `origem` por `destino` (`Path.replace()`), com retentativa
    curta em caso de `PermissionError`.

    ⚠️ Achado ao vivo em 18-19/09/2026: numa execução de ~4h30 (751
    documentos processados), o worker parou com
    `[WinError 5] Access is denied` bem nesse `replace()`. Causa provável:
    o projeto inteiro mora dentro de uma pasta sincronizada pelo OneDrive
    (`Desktop\\Robo-ANTT`) - então até `data/output/` (checkpoint,
    planilhas-fatia dos workers), que devia ser só local, acaba sendo
    sincronizado também. Depois de centenas de gravações ao longo de
    várias horas, é bem provável que o OneDrive tenha segurado o arquivo
    (escaneando/subindo) bem na hora do `replace()`. Esse tipo de trava
    costuma ser passageiro (resolve sozinho em segundos) - por isso
    retentativa curta em vez de desistir na primeira falha, que derrubava a
    execução inteira por causa de um lock temporário de terceiros.
    """
    for tentativa in range(tentativas):
        try:
            origem.replace(destino)
            return
        except PermissionError:
            if tentativa == tentativas - 1:
                raise
            time.sleep(espera_segundos)
