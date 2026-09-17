"""
TESTE DE SESSÕES SIMULTÂNEAS — PARTE 3: verificar

Roda sozinho (sem login manual) - reaproveita a detecção de sessão
expirada já usada pelo robô de verdade (SessaoExpiradaError, em
src/robo_antt/portal.py), pra ficar consistente com o resto do projeto.

Pré-requisito: já ter rodado, NESTA ORDEM:
  1. scripts/teste_sessao_dupla_A_capturar.py
  2. scripts/teste_sessao_dupla_B_capturar.py

O que este script faz: testa a Sessão A, depois a Sessão B, depois a
Sessão A DE NOVO - pra ver se logar na B derrubou a A (sinal de que o
portal só permite 1 sessão ativa por CPF) ou se as duas continuam
válidas ao mesmo tempo (sinal de que múltiplas sessões são possíveis).
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

from robo_antt.config import VISTAS_URL
from robo_antt.portal import PortalIndisponivelError, SessaoExpiradaError, abrir_tela_processos

ARQUIVO_A = Path(__file__).resolve().parent.parent / "data" / "sessao" / "teste_dupla_sessao_A.json"
ARQUIVO_B = Path(__file__).resolve().parent.parent / "data" / "sessao" / "teste_dupla_sessao_B.json"


def _testar(p, arquivo: Path, rotulo: str) -> str:
    """Devolve 'valida', 'invalida' ou 'portal_indisponivel'."""
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(arquivo))
    page = context.new_page()
    try:
        abrir_tela_processos(page)
        print(f"[{rotulo}] sessão VÁLIDA (acessou a tela de processos sem cair no login)")
        return "valida"
    except SessaoExpiradaError:
        print(f"[{rotulo}] sessão INVÁLIDA (caiu na tela de login)")
        return "invalida"
    except PortalIndisponivelError as e:
        print(f"[{rotulo}] portal indisponível agora, não deu pra testar: {e}")
        return "portal_indisponivel"
    finally:
        browser.close()


def main():
    if not ARQUIVO_A.exists() or not ARQUIVO_B.exists():
        print("Faltam os arquivos de sessão A e/ou B.")
        print("Rode primeiro scripts/teste_sessao_dupla_A_capturar.py e scripts/teste_sessao_dupla_B_capturar.py.")
        return

    with sync_playwright() as p:
        print("=== Passo 1: testando Sessão A ===")
        a_antes = _testar(p, ARQUIVO_A, "Sessão A")

        print("\n=== Passo 2: testando Sessão B ===")
        b = _testar(p, ARQUIVO_B, "Sessão B")

        print("\n=== Passo 3: testando Sessão A DE NOVO (logar na B derrubou a A?) ===")
        a_depois = _testar(p, ARQUIVO_A, "Sessão A (depois de B)")

    print("\n=== RESULTADO ===")
    if "portal_indisponivel" in (a_antes, b, a_depois):
        print("Teste inconclusivo - portal ficou indisponível em algum momento. Tente de novo mais tarde.")
    elif a_antes == "valida" and b == "valida" and a_depois == "valida":
        print("AS DUAS SESSÕES CONTINUAM VÁLIDAS AO MESMO TEMPO.")
        print("=> O portal permite múltiplas sessões simultâneas com o mesmo CPF.")
        print("=> Rodar 'workers' com sessões independentes é tecnicamente possível - ainda")
        print("   falta confirmar se o enfileiramento do servidor (achado de 16/09/2026) é")
        print("   por SESSÃO ou pela CONTA inteira (só isso não garante ganho de velocidade).")
    elif a_antes == "valida" and b == "valida" and a_depois == "invalida":
        print("A Sessão B DERRUBOU a Sessão A (A parou de funcionar depois que B logou).")
        print("=> O portal parece permitir só 1 sessão ativa por vez por CPF.")
        print("=> Múltiplos workers com o mesmo login não são viáveis dessa forma.")
    else:
        print(f"Resultado não previsto (A antes={a_antes}, B={b}, A depois={a_depois}) - ver detalhes acima.")


if __name__ == "__main__":
    main()
