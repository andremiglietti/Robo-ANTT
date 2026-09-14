# CLAUDE.md — Robô de Extração de Autos de Infração da ANTT

> Este arquivo resume todas as decisões e o contexto acumulado numa conversa anterior no claude.ai, para que o Claude Code continue o projeto sem precisar re-explicar nada. Mantenha este arquivo atualizado conforme o projeto avança.

## Objetivo do projeto

Criar um robô (Python + Playwright) que automatize a consulta de multas/autos de infração da empresa no portal da ANTT, baixe os PDFs dos autos, extraia os dados relevantes, cruze com a base interna de viagens/fretes da empresa e gere um relatório consolidado — substituindo um processo hoje manual e lento (que causa detecção de multas com até 6 meses de atraso).

O projeto é inspirado (benchmarking) num robô já existente em outra empresa do setor, com arquitetura equivalente, mas precisa ser construído do zero para o ambiente desta empresa.

**Prazo de entrega:** 30/09/2026. Início: 14/09/2026. Ritmo de trabalho: ~3h/dia, apenas dias úteis (13 dias úteis, ~39h totais, sem folga de buffer no cronograma).

---

## Decisões já confirmadas (não reabrir sem necessidade)

| Decisão | Detalhe |
|---|---|
| Credencial de login | CPF e senha do **representante legal** da empresa (decisão de negócio já tomada; risco de compliance conhecido e aceito, fora do escopo técnico) |
| Tipo de login | **Manual** — uma pessoa específica loga no portal para passar pelo captcha/verificação de segurança; o robô reaproveita essa sessão já autenticada em seguida (não há login 100% automatizado) |
| Responsável pelo login manual | Já confirmado com a empresa (pessoa e disponibilidade definidas) |
| Onde o robô roda | **Localmente**, no computador dessa mesma pessoa, **sob demanda** (sem agendamento automático — ela decide quando disparar a execução, ex.: duplo clique num atalho) |
| Onde salvar os resultados | Pasta local **sincronizada com o OneDrive** dessa pessoa (que por sua vez sincroniza com uma biblioteca do SharePoint) — não é integração direta via API do SharePoint/Graph |
| Cuidado técnico na gravação | Escrever primeiro em arquivo temporário e só then mover/renomear para a pasta sincronizada, evitando conflito com a sincronização do OneDrive em andamento |
| Acesso ao OneDrive | Confirmado que o computador da pessoa tem acesso ao OneDrive |

## Decisões pendentes / a confirmar

- Permissão de **escrita** (não só leitura) da conta na pasta específica do SharePoint (item 6.3 do checklist).
- Exigência de aprovação de InfoSec para automação com credencial real (item 6.4).
- Ponto de contato do TI para suporte contínuo pós-entrega (item 6.5).
- Estrutura da base interna de viagens/fretes para o cruzamento de dados (Bloco 4).
- Volume de CNPJs e de multas/mês (Bloco 5) — não bloqueia o desenvolvimento, só dimensionamento.

---

## Arquitetura técnica esperada

1. **Login manual + captura de sessão**: a pessoa loga manualmente; o estado da sessão (cookies) é salvo via `context.storage_state()` do Playwright e reaproveitado pelo robô em execuções separadas, sem precisar de nova senha a cada vez.
   - ✅ **Teste crítico validado (item 1.3 do checklist) — 14/09/2026:** `teste_sessao_1_capturar.py` e `teste_sessao_2_testar.py` foram executados contra o portal real. Resultado: uma nova janela do navegador, carregando apenas a sessão salva (`sessao_antt.json`), abriu **já autenticada na página inicial**, sem precisar reinserir CPF/senha. Confirma que a arquitetura de login manual + reaproveitamento de sessão via `storage_state()` é viável. Não foi testado ainda: por quanto tempo a sessão permanece válida (expiração) — isso ainda precisa ser observado ao longo dos próximos dias de uso real.
2. **Descoberta de CNPJs**: identificar automaticamente todos os CNPJs vinculados (matriz + filiais) a partir da sessão logada.
3. **Varredura paginada**: percorrer a listagem de processos/autos de infração, sem filtro restritivo, tratando a paginação do portal.
4. **Controle de duplicidade**: antes de baixar um auto, verificar se ele já existe no repositório local (arquivo + registro), para não reprocessar o que já foi capturado.
5. **Download e extração de PDF**: baixar o PDF do auto e extrair campos estruturados: placa, data da infração, número do documento fiscal (CIOT/MDF-e), enquadramento legal, descrição. O layout pode variar por tipo de multa (frete mínimo, pedágio, excesso de peso).
6. **Cruzamento com base interna**: usar o número do CIOT/MDF-e extraído para localizar a viagem correspondente na base interna da empresa e validar se a multa é devida (equivalente a um PROCV/SELECT).
7. **Checkpoint e retentativa**: manter um estado persistente (ex.: JSON) entre execuções, distinguindo falha de infraestrutura/sessão expirada (não tentar logar sozinho — sinalizar que precisa de novo login manual) de falha real de um documento específico.
8. **Saída**: gravar o resultado consolidado (planilha) na pasta sincronizada com o SharePoint, com o cuidado de escrita em arquivo temporário mencionado acima.

## Riscos conhecidos (herdados do benchmarking com o outro projeto)

- Uso do CPF/senha do representante legal é uma exposição de compliance conhecida e aceita — não é papel do desenvolvimento resolver isso, mas evitar hardcode de senha em texto puro no código.
- Dependência de uma pessoa específica para o login manual: sem ela disponível, o ciclo inteiro não roda. Não há agendamento automático — a regularidade de uso depende de disciplina operacional, não do sistema.
- Sessão pode expirar no meio de um ciclo — o robô deve parar de forma controlada e sinalizar a necessidade de novo login, não tentar contornar sozinho.
- Estrutura do portal da ANTT pode mudar sem aviso (já ocorreu no projeto de referência) — manter os seletores isolados/fáceis de atualizar.
- Cronograma sem dias de buffer — qualquer atraso relevante deve gerar decisão consciente de cortar escopo (ex.: adiar o cruzamento com a base interna) em vez de tentar compensar depois.

---

## Cronograma (13 dias úteis, 14/09 a 30/09/2026)

| Dia | Data | Tarefa |
|---|---|---|
| 1 | 14/09 (Seg) | Confirmar disponibilidade da pessoa + infraestrutura com TI + estruturar projeto |
| 2 | 15/09 (Ter) | Reunir prints das telas do portal |
| 3 | 16/09 (Qua) | Inspecionar login/CNPJ + **teste de captura de sessão (1.3)** |
| 4 | 17/09 (Qui) | Inspecionar consulta/tabela/paginação + conseguir PDF de exemplo |
| 5 | 18/09 (Sex) | Inspecionar botão de download + lógica de varredura multi-CNPJ |
| 6 | 21/09 (Seg) | Testar login real + captura de sessão contra o portal |
| 7 | 22/09 (Ter) | Testar varredura de CNPJs + paginação |
| 8 | 23/09 (Qua) | Implementar download de PDFs + verificação de duplicidade |
| 9 | 24/09 (Qui) | Implementar extração de campos do PDF |
| 10 | 25/09 (Sex) | Checkpoint/retentativa + teste ponta a ponta em escala pequena |
| 11 | 28/09 (Seg) | Cruzamento com base interna + gravação na pasta do SharePoint |
| 12 | 29/09 (Ter) | Teste final ponta a ponta + criar atalho de execução + guia de uso |
| 13 | 30/09 (Qua) | Revisão geral e entrega |

---

## Estrutura do projeto (estruturada em 14/09/2026)

```
Robo-ANTT/
├── CLAUDE.md               # este arquivo
├── requirements.txt         # dependências Python (playwright==1.62.0)
├── .gitignore               # exclui sessão salva, downloads, saída, venv
├── .venv/                   # ambiente virtual Python (não versionado)
├── src/robo_antt/           # pacote Python do robô (código real, ainda vazio — a construir dias 3–11)
├── scripts/                 # scripts avulsos executáveis
│   ├── teste_sessao_1_capturar.py
│   └── teste_sessao_2_testar.py
├── data/
│   ├── sessao/               # sessao_antt.json (cookies — nunca versionar)
│   ├── downloads/            # PDFs baixados dos autos (nunca versionar)
│   └── output/                # relatório/planilha final antes de ir para o SharePoint (nunca versionar)
└── docs/                    # material de apoio e planejamento
    ├── checklist_robo_antt.md
    ├── cronograma_robo_antt_3.md      # cronograma vigente (substitui a versão anterior)
    ├── arquitetura_solucao_antt.md / .html
    ├── apresentacao_antt_telas.pptx
    ├── painel_progresso_antt.html
    └── Bench ANTT.srt
```

Ambiente Python: `.venv` criado com Python 3.13, `playwright==1.62.0` instalado via `requirements.txt`, e o navegador Chromium do Playwright já baixado (`python -m playwright install chromium`). Para reativar o ambiente: `.venv\Scripts\activate` (PowerShell) e depois rodar os scripts em `scripts/` com `python scripts/nome_do_script.py`.

## Arquivos já produzidos

- `docs/checklist_robo_antt.md` — checklist detalhado de tudo que precisa ser levantado (portal, telas, PDF, base interna, infraestrutura), com status atual.
- `docs/cronograma_robo_antt_3.md` — cronograma vigente (versão 3, sem buffer de fim de semana), com riscos e observações. **Esta é a versão de referência — mais detalhada que a tabela resumida abaixo.**
- `docs/painel_progresso_antt.html` — painel interativo (abrir no navegador) para acompanhar % de conclusão do checklist e do cronograma, com gráfico de tendência. Os dados ficam salvos automaticamente entre acessos.
- `scripts/teste_sessao_1_capturar.py` — script que abre o navegador, permite login manual e salva a sessão autenticada em `data/sessao/sessao_antt.json`.
- `scripts/teste_sessao_2_testar.py` — script que carrega a sessão salva e tenta acessar uma página interna sem novo login, para validar se a captura de sessão funciona. **Já validado com sucesso em 14/09/2026.**

## Status atual do checklist (resumo)

✅ Já confirmado: 1.2 (responsável pelo login), 1.3 (captura de sessão validada em 14/09/2026), estruturação do projeto/ambiente Python/Playwright (Dia 1, "Comigo"), 6.1 (computador definido), 6.2 (acesso ao OneDrive confirmado).
⬜ Pendente: demais itens dos Blocos 1–6 (ver `docs/checklist_robo_antt.md` para a lista completa) — inclui as confirmações do Dia 1 com a pessoa responsável pelo login e com o TI (disponibilidade e infraestrutura), que são tarefas de negócio, não técnicas.

## Próximos passos sugeridos

1. ~~Rodar os testes de sessão~~ — feito, resultado positivo (ver acima).
2. ~~Estruturar o projeto (pastas, ambiente Python, Playwright)~~ — feito em 14/09/2026 (ver "Estrutura do projeto" acima).
3. Seguir para os itens do Bloco 2 (prints + "Inspecionar" das telas do portal) — tarefa do Dia 2 (15/09) do cronograma.
4. Ao longo dos próximos dias, observar quanto tempo a sessão salva permanece válida antes de expirar (não testado ainda) — isso vai definir a frequência com que o login manual precisa ser refeito.
5. Confirmar os itens pendentes do Bloco 6 (permissão de escrita no SharePoint, aprovação de InfoSec, ponto de contato do TI) e a confirmação de disponibilidade da pessoa do login manual (tarefas de negócio do Dia 1 ainda em aberto, fora do escopo técnico).

## Notas de segurança adicionadas nesta sessão

- `sessao_antt.json` contém os cookies de sessão autenticada do representante legal (equivalente a uma credencial ativa) e estava sem `.gitignore` — foi criado um `.gitignore` cobrindo esse arquivo, PDFs baixados e artefatos de ambiente Python, para evitar que sejam commitados por engano.
