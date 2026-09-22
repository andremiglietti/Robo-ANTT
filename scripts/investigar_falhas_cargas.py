"""
Investigação (22/09/2026, ver CLAUDE.md) da hipótese não confirmada sobre
as 16 falhas persistentes de download, todas no tipo de fiscalização
"Cargas" (erro: "Timeout 60000ms exceeded while waiting for event
'download'" - o clique funciona, o download em si nunca dispara a tempo),
concentradas em 4 CNPJs (92.660.604/0170-77, /0171-58, /0172-39, /0175-81).

Hipótese: PDFs de "Cargas" (que no disco viram as pastas "Piso Mínimo de
Frete", "Produtos Perigosos", "Vale-Pedágio" - ver CLAUDE.md) podem ser
anormalmente grandes/lentos de gerar no servidor, ultrapassando o timeout
de 60s de forma consistente - não dá pra baixar os 16 documentos que
falham pra medir direto (é POR ISSO que eles falham), mas dá pra comparar
o tamanho dos documentos VIZINHOS que baixaram com sucesso (mesmo CNPJ,
mesmo tipo) contra a média geral, como evidência indireta.

Só lê PDFs já em disco - sem sessão, sem contato com o portal.

USO:
    python scripts/investigar_falhas_cargas.py
"""
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from robo_antt.config import DOWNLOAD_DIR  # noqa: E402

# Pastas em disco que correspondem ao tipo de fiscalização "Cargas" na
# busca (ver CLAUDE.md - "Piso Mínimo de Frete"/"Produtos Perigosos"/
# "Vale-Pedágio" caem todos dentro de "Cargas" no dropdown do portal).
TIPOS_CARGAS = {"Piso Mínimo de Frete", "Produtos Perigosos", "Vale-Pedágio", "Vale Pedágio"}

CNPJS_SUSPEITOS = {
    "92660604017077": "92.660.604/0170-77",
    "92660604017158": "92.660.604/0171-58",
    "92660604017239": "92.660.604/0172-39",
    "92660604017581": "92.660.604/0175-81",
}


def _stats(valores: list[float]) -> str:
    if not valores:
        return "(nenhum documento)"
    media = statistics.mean(valores)
    mediana = statistics.median(valores)
    return f"n={len(valores)} | media={media:.1f} | mediana={mediana:.1f} | min={min(valores):.0f} | max={max(valores):.0f}"


def main() -> None:
    if not DOWNLOAD_DIR.exists():
        print("[ATENCAO] Pasta de downloads nao existe - nada pra analisar.")
        return

    paginas_por_tipo: dict[str, list[int]] = defaultdict(list)
    tamanho_por_tipo: dict[str, list[float]] = defaultdict(list)
    paginas_suspeitos_cargas: list[int] = []
    tamanho_suspeitos_cargas: list[float] = []
    maiores: list[tuple[int, str]] = []  # (paginas, caminho) pra achar os PDFs mais pesados de "Cargas"

    total_lidos = 0
    total_erro_leitura = 0
    for caminho in DOWNLOAD_DIR.glob("*/*/*.pdf"):
        cnpj = caminho.parent.parent.name
        tipo = caminho.parent.name
        try:
            doc = pymupdf.open(str(caminho))
            n_paginas = doc.page_count
            doc.close()
        except Exception:
            total_erro_leitura += 1
            continue
        total_lidos += 1
        tamanho_kb = caminho.stat().st_size / 1024

        paginas_por_tipo[tipo].append(n_paginas)
        tamanho_por_tipo[tipo].append(tamanho_kb)

        if tipo in TIPOS_CARGAS:
            maiores.append((n_paginas, str(caminho)))
            if cnpj in CNPJS_SUSPEITOS:
                paginas_suspeitos_cargas.append(n_paginas)
                tamanho_suspeitos_cargas.append(tamanho_kb)

    print(f"PDFs lidos com sucesso: {total_lidos} (erros de leitura: {total_erro_leitura})\n")

    print("=== Paginas por tipo (todos os CNPJs) ===")
    for tipo in sorted(paginas_por_tipo, key=lambda t: -len(paginas_por_tipo[t])):
        print(f"  {tipo}: {_stats(paginas_por_tipo[tipo])} paginas")

    print("\n=== Tamanho (KB) por tipo (todos os CNPJs) ===")
    for tipo in sorted(tamanho_por_tipo, key=lambda t: -len(tamanho_por_tipo[t])):
        print(f"  {tipo}: {_stats(tamanho_por_tipo[tipo])} KB")

    todos_cargas_paginas = [p for t in TIPOS_CARGAS for p in paginas_por_tipo.get(t, [])]
    todos_nao_cargas_paginas = [p for t, ps in paginas_por_tipo.items() if t not in TIPOS_CARGAS for p in ps]
    print("\n=== Comparacao direta: Cargas (Frete/Perigosos/Vale) vs resto ===")
    print(f"  Cargas (todos os CNPJs):     {_stats(todos_cargas_paginas)} paginas")
    print(f"  Outros tipos (todos CNPJs):  {_stats(todos_nao_cargas_paginas)} paginas")

    print(f"\n=== Documentos de Cargas SO dos 4 CNPJs suspeitos ({', '.join(CNPJS_SUSPEITOS.values())}) ===")
    print(f"  Paginas: {_stats(paginas_suspeitos_cargas)}")
    print(f"  Tamanho: {_stats(tamanho_suspeitos_cargas)} KB")

    maiores.sort(reverse=True)
    print("\n=== 10 maiores PDFs de Cargas em disco (paginas) ===")
    for n_paginas, caminho in maiores[:10]:
        print(f"  {n_paginas:4d} paginas - {caminho}")

    print(
        "\nInterpretacao: se os documentos de Cargas (em geral, ou dos 4 CNPJs suspeitos em "
        "particular) tiverem consistentemente MUITO mais paginas/KB que os outros tipos, isso "
        "sustenta a hipotese de que o servidor demora mais pra montar esses PDFs, justificando "
        "um timeout maior so pra downloads desse tipo. Se a diferenca for pequena/inexistente, "
        "a causa provavelmente NAO e o tamanho do documento (precisa investigar outra hipotese)."
    )


if __name__ == "__main__":
    main()
