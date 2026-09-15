# CLAUDE.md — Robô de Extração de Autos de Infração da ANTT

> Este arquivo resume todas as decisões e o contexto acumulado numa conversa anterior no claude.ai, para que o Claude Code continue o projeto sem precisar re-explicar nada. Mantenha este arquivo atualizado conforme o projeto avança.

## Objetivo do projeto

Criar um robô (Python + Playwright) que automatize a consulta de multas/autos de infração da empresa no portal da ANTT, baixe os PDFs dos autos, extraia os dados relevantes e gere um relatório consolidado (Excel) — substituindo um processo hoje manual e lento (que causa detecção de multas com até 6 meses de atraso).

> ⚠️ Atualizado em 15/09/2026: **não há cruzamento com base interna de viagens/fretes** — não existe esse registro na empresa e não será necessário. O escopo do robô é varredura + download + extração + planilha consolidada.

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
- Volume de CNPJs e de multas/mês (Bloco 5) — não bloqueia o desenvolvimento, só dimensionamento.
- ~~Bloco 4 (estrutura da base interna)~~ — descartado em 15/09/2026: não existe registro de viagens na empresa, não haverá cruzamento de dados.

---

## Arquitetura técnica esperada

1. **Login manual + captura de sessão**: a pessoa loga manualmente; o estado da sessão (cookies) é salvo via `context.storage_state()` do Playwright e reaproveitado pelo robô em execuções separadas, sem precisar de nova senha a cada vez.
   - ✅ **Teste crítico validado (item 1.3 do checklist) — 14/09/2026:** `teste_sessao_1_capturar.py` e `teste_sessao_2_testar.py` foram executados contra o portal real. Resultado: uma nova janela do navegador, carregando apenas a sessão salva (`sessao_antt.json`), abriu **já autenticada na página inicial**, sem precisar reinserir CPF/senha. Confirma que a arquitetura de login manual + reaproveitamento de sessão via `storage_state()` é viável. Não foi testado ainda: por quanto tempo a sessão permanece válida (expiração) — isso ainda precisa ser observado ao longo dos próximos dias de uso real.
2. **Descoberta de CNPJs**: identificar automaticamente todos os CNPJs vinculados (matriz + filiais) a partir da sessão logada.
   - ✅ Confirmado em 15/09/2026: a tela `VistasAoProcesso.aspx` tem um `<select id="Corpo_ddlRepresentado">` com todos os CNPJs (matriz + filiais) da empresa já pré-carregados no HTML (não precisa de chamada extra) — outerHTML capturado em `codigos_site/vistas_ao_processo.docx`.
3. **Varredura paginada**: percorrer a listagem de processos/autos de infração, sem filtro restritivo, tratando a paginação do portal.
   - ✅ Confirmado em 15/09/2026: a tabela de resultados (`table#Corpo_gdvResultado`) e a paginação (`Corpo_ucPaginadorResultado`) só existem no DOM **depois** do clique em "Pesquisar" — são renderizadas via AJAX (UpdatePanel do ASP.NET), não aparecem no HTML estático inicial. outerHTML capturado em `codigos_site/tabela_pesquisar.txt`.
4. **Controle de duplicidade**: antes de baixar um auto, verificar se ele já existe no repositório local (arquivo + registro), para não reprocessar o que já foi capturado.
   - ✅ Confirmado em 15/09/2026: o PDF já é baixado com o nome do **número do Auto de Infração** (ex.: `EPSMA00087472019.pdf`), sem precisar renomear. A verificação de duplicidade pode ser um simples "já existe `{numero_auto}.pdf` em `data/downloads/{cnpj}/{tipo_multa}/`?" (caminho atualizado em 15/09 — ver item 7/Saída) antes de clicar na lupa daquela linha — não precisa de um índice/registro separado só para isso.
5. **Download e extração de PDF**: baixar o PDF do auto e extrair campos estruturados. O layout pode variar por tipo de multa (frete mínimo, pedágio, excesso de peso, produtos perigosos).
   - ✅ **Caminho de download confirmado em 15/09/2026:** na tela `VistasAoProcesso.aspx`, cada linha da tabela de resultados tem um botão-imagem (lupa, `id="Corpo_gdvResultado_btnVisualizar_N"`, `onclick="showProgressJavaScript(solicitarVistas);"`). Ao clicar, o sistema processa e **baixa o PDF do auto diretamente** (download direto do navegador, sem abrir nova aba/visualizador) — apesar do nome da função JS ("solicitar vistas") sugerir um pedido com aprovação futura, na prática o download é imediato/síncrono. Esse é o elemento que o robô deve clicar; no Playwright, deve ser capturado com `page.expect_download()` ao redor do clique.
   - ❌ **Descartado:** a tela "Relatório de Multas" (`/spmi/Site/RelacaoMultas/ConsultarMultas.aspx`) só gera um relatório agregado de todas as multas por CPF — não permite baixar o PDF de um auto individual, então não serve para o fluxo de extração por multa.
   - ✅ **Estrutura do PDF confirmada em 15/09/2026** (5 exemplos analisados: excesso de peso, piso mínimo de frete ×2, produtos perigosos, vale-pedágio): o PDF baixado é o **processo inteiro** (auto + notificação + boleto + recursos + SERASA + arquivamento), podendo ter de 5 a **79 páginas**.
     - Página 1 (sempre) — "AUTO DE INFRAÇÃO [TIPO]": nº do auto, infrator (nome/CNPJ), veículo (placa), data/local da infração, tipificação (código, artigo, resolução, descrição, amparo legal), tipo/nº do documento fiscal.
     - Uma página **posterior** (nº varia, geralmente a "1ª Notificação de Penalidade"/boleto — pg. 7 no exemplo de excesso de peso) — **Valor da multa, Valor com desconto, Data de vencimento e Código de barras** ficam aqui, não na página 1. ⚠️ Corrige uma nota anterior deste arquivo que dizia "só precisa ler a página 1" — não é mais verdade, dado o pedido de colunas de 15/09 (ver item 8). Ainda não confirmado se esse boleto existe em 100% dos processos (pode não existir se a multa ainda não foi notificada/gerada) — tratar como campo opcional na extração.
   - ⚠️ **O "documento fiscal" NÃO é sempre CIOT/MDF-e** — o campo "Tipo de Documento" observado varia por auto: `DANFE` (excesso de peso, produtos perigosos), `MDFE` (vale-pedágio, piso mínimo em 1 dos 2 exemplos) ou `CONTRATO DE TRANSPORTE` (piso mínimo no outro exemplo). A extração precisa ler o par "Tipo de Documento" + "Número do Documento" genericamente, não assumir CIOT/MDF-e fixo. (Deixou de ser bloqueante para cruzamento de dados, já que o Bloco 4 foi descartado — mas ainda importa para popular corretamente a planilha, se alguma coluna for baseada nesse par.)
   - Cada tipo de auto tem um layout de tabela diferente (nº de veículos, campos de cálculo de piso mínimo, ONU/produto perigoso, etc.), mas todos compartilham o núcleo acima.
6. **Checkpoint e retentativa**: manter um estado persistente (ex.: JSON) entre execuções, distinguindo falha de infraestrutura/sessão expirada (não tentar logar sozinho — sinalizar que precisa de novo login manual) de falha real de um documento específico.
7. **Saída**: gravar o resultado consolidado (planilha) na pasta sincronizada com o SharePoint, com o cuidado de escrita em arquivo temporário mencionado acima.
   - ✅ **Definido em 15/09/2026 — escopo final da saída (substitui a ideia original de cruzamento com base interna):**
     - **Uma planilha Excel** (criar se não existir, senão atualizar) com, no mínimo, estas colunas: `Link do Arquivo`, `Número do Processo`, `Auto de Infração`, `Tipo de Multa`, `CNPJ`, `Data Autuação`, `Data Emissão Doc. Fiscal`, `Data Emissão Notificação`, `Data Emissão Boleto`, `Data Vencimento`, `Valor`, `Valor Desconto`, `Placa`, `Descrição da Infração`, `Código de Barras`.
       - ✅ Decisão de 15/09/2026: as datas de "emissão" viraram **3 colunas separadas** (doc. fiscal / notificação / boleto) em vez de uma só — o PDF tem até 3 datas de emissão diferentes conforme a página, e juntar tudo numa coluna perderia informação.
     - **Os PDFs de cada processo** são salvos numa estrutura de pastas **separada por CNPJ e depois por tipo de multa**, ex.: `data/downloads/{cnpj}/{tipo_multa}/{numero_auto}.pdf`. A coluna "Link do Arquivo" da planilha aponta para esse caminho.
     - Mapeamento de origem de cada coluna (a confirmar/ajustar na implementação, dia 9):
       - Direto da tabela de varredura (sem abrir PDF): `Número do Processo`, `Auto de Infração` (+ `Situação`/`Data do Auto`, úteis embora não estejam na lista de colunas pedida).
       - Direto do filtro de busca usado (já conhecido pelo robô antes de baixar): `Tipo de Multa`, `CNPJ`.
       - Da página 1 do PDF: `Placa`, `Descrição da Infração`, `Data Autuação` (data da infração), `Data Emissão Doc. Fiscal` (campo "Data de Emissão" ao lado do Tipo/Nº do Documento — DANFE/MDF-e/Contrato).
       - De páginas posteriores do PDF (notificação de autuação / boleto): `Data Emissão Notificação`, `Data Emissão Boleto`, `Data Vencimento`, `Valor`, `Valor Desconto`, `Código de Barras`.
       - ✅ Confirmado em 15/09/2026: `Valor Desconto` = campo **"Desconto / Abatimento"** do boleto (ex.: R$ 398,43 no exemplo de excesso de peso) — é o valor do desconto em si, não o total já com desconto aplicado.
     - Controle de duplicidade (item 4) e essa estrutura de pastas devem usar o mesmo CNPJ/tipo de multa como chave.

## Riscos conhecidos (herdados do benchmarking com o outro projeto)

- Uso do CPF/senha do representante legal é uma exposição de compliance conhecida e aceita — não é papel do desenvolvimento resolver isso, mas evitar hardcode de senha em texto puro no código.
- Dependência de uma pessoa específica para o login manual: sem ela disponível, o ciclo inteiro não roda. Não há agendamento automático — a regularidade de uso depende de disciplina operacional, não do sistema.
- Sessão pode expirar no meio de um ciclo — o robô deve parar de forma controlada e sinalizar a necessidade de novo login, não tentar contornar sozinho.
- Estrutura do portal da ANTT pode mudar sem aviso (já ocorreu no projeto de referência) — manter os seletores isolados/fáceis de atualizar.
- Cronograma sem dias de buffer — qualquer atraso relevante deve gerar decisão consciente de cortar escopo (ex.: entregar sem alguns tipos de multa menos comuns, ou sem alguma coluna da planilha) em vez de tentar compensar depois.

---

## Cronograma (13 dias úteis, 14/09 a 30/09/2026)

| Dia | Data | Tarefa | Status |
|---|---|---|---|
| 1 | 14/09 (Seg) | Confirmar disponibilidade da pessoa + infraestrutura com TI + estruturar projeto | ✅ Estruturação feita; confirmações de negócio com pessoa/TI ainda não reportadas de volta |
| 2 | 15/09 (Ter) — **hoje** | Reunir prints das telas do portal | ✅ Feito — e mais (ver abaixo) |
| 3 | 16/09 (Qua) | Inspecionar login/CNPJ + **teste de captura de sessão (1.3)** | ✅ Feito (adiantado — sessão testada dia 1, Inspecionar feito dia 2) |
| 4 | 17/09 (Qui) | Inspecionar consulta/tabela/paginação + conseguir PDF de exemplo | ✅ Feito (adiantado 2 dias — 5 PDFs de exemplo, um por tipo de multa) |
| 5 | 18/09 (Sex) | Inspecionar botão de download + lógica de varredura multi-CNPJ | 🔶 Metade feita: botão de download já inspecionado/confirmado. A lógica de varredura (código) ainda **não foi escrita** |
| 6 | 21/09 (Seg) | Testar login real + captura de sessão contra o portal | ⬜ |
| 7 | 22/09 (Ter) | Testar varredura de CNPJs + paginação | ⬜ |
| 8 | 23/09 (Qua) | Implementar download de PDFs + verificação de duplicidade | ⬜ |
| 9 | 24/09 (Qui) | Implementar extração de campos do PDF | ⬜ |
| 10 | 25/09 (Sex) | Checkpoint/retentativa + teste ponta a ponta em escala pequena | ⬜ |
| 11 | 28/09 (Seg) | ~~Cruzamento com base interna~~ (descartado — sem base interna) + geração da planilha Excel final + gravação na pasta do SharePoint | ⬜ |
| 12 | 29/09 (Ter) | Teste final ponta a ponta + criar atalho de execução + guia de uso | ⬜ |
| 13 | 30/09 (Qua) | Revisão geral e entrega | ⬜ |

**Balanço em 15/09/2026 (Dia 2 do calendário):** todo o levantamento/investigação até o Dia 4 está pronto, e metade do Dia 5. Ou seja, **~3 dias de investigação adiantados**. Isso cria uma folga útil para a fase de código (Dias 6–10), que é onde o risco de atraso é maior — mas nenhuma linha de código do robô foi escrita ainda (`src/robo_antt/` continua vazio); o adiantamento é só na parte de levantamento/checklist, não em implementação.

---

## Estrutura do projeto (estruturada em 14/09/2026, evidências adicionadas em 15/09/2026)

```
Robo-ANTT/
├── CLAUDE.md               # este arquivo
├── requirements.txt         # dependências Python (playwright==1.62.0)
├── .gitignore               # exclui sessão salva, PDFs, prints/código do portal, downloads, saída, venv
├── .venv/                   # ambiente virtual Python (não versionado)
├── src/robo_antt/           # pacote Python do robô (código real, ainda vazio — começa a ser escrito no Dia 3, 16/09)
├── scripts/                 # scripts avulsos executáveis
│   ├── teste_sessao_1_capturar.py
│   └── teste_sessao_2_testar.py
├── prints/                  # [NÃO versionado] prints de todas as telas do portal (login, home, consulta, tabela paginada)
├── codigos_site/            # [NÃO versionado] outerHTML (.docx/.txt) dessas mesmas telas — usado pra achar os seletores reais
├── data/
│   ├── sessao/               # sessao_antt.json (cookies — nunca versionar)
│   ├── downloads/            # PDFs de exemplo (excesso_peso, piso_minimo ×2, produtos_perigosos, vale_pedagio) + print da tabela — nunca versionar
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
- `scripts/teste_sessao_1_capturar.py` / `teste_sessao_2_testar.py` — capturam e testam o reaproveitamento da sessão logada. **Validados com sucesso em 14/09/2026.**
- `prints/` + `codigos_site/` — evidência visual e técnica (outerHTML) de login, home, seleção de CNPJ, consulta com filtros, tabela de resultados paginada e o fluxo de download (lupa/"Vistas"). Coletados em 15/09/2026.
- `data/downloads/` — 5 PDFs de exemplo (um por tipo de multa) + print da tabela de resultados indicando as colunas relevantes. Coletados em 15/09/2026.

## Status atual do checklist (resumo)

✅ Já confirmado:
- Bloco 1: 1.2 (responsável pelo login), 1.3 (captura de sessão validada em 14/09/2026).
- Bloco 2 (telas + Inspecionar): **completo em 15/09/2026** — login, home, seleção de CNPJ, consulta com filtros, tabela paginada e o botão de download (lupa) todos capturados e com outerHTML real.
- Bloco 3 (PDF de exemplo): **completo em 15/09/2026** — 5 exemplos (um por tipo de multa), estrutura de campos mapeada.
- Bloco 4 (base interna): **descartado** — não existe, não é mais parte do escopo.
- Estruturação do projeto/ambiente Python/Playwright (Dia 1).
- 6.1 (computador definido), 6.2 (acesso ao OneDrive confirmado).
- Definição completa da saída (planilha Excel + estrutura de pastas por CNPJ/tipo de multa) — não estava no checklist original, mas fechada em 15/09/2026.

⬜ Pendente:
- Bloco 5 (volume de CNPJs/multas por mês) — não bloqueia.
- Bloco 6.3–6.5 (permissão de escrita no SharePoint, aprovação de InfoSec, ponto de contato do TI) — tarefas de negócio, não técnicas.
- Confirmação de disponibilidade recorrente da pessoa do login manual (Dia 1, item 1.2 parcial).
- Observar por quanto tempo a sessão salva permanece válida (não testado ainda).

**Ou seja: os Blocos 1–3 do checklist, que eram bloqueantes para começar a escrever código, estão todos fechados.** Só restam itens de negócio/infraestrutura (Bloco 6) que não impedem o desenvolvimento.

## Próximos passos sugeridos

1. ~~Testes de sessão, estruturação do projeto, Bloco 2 (prints/Inspecionar), Bloco 3 (PDF de exemplo), definição da saída~~ — tudo concluído (14–15/09/2026).
2. **Começar a escrever o código real em `src/robo_antt/`** (Dia 3 em diante) usando os seletores já capturados: login (`Corpo_txtLoginCpjCnpj`/`Corpo_txtLoginSenha`/`Corpo_btnLogin`), seleção de CNPJ (`Corpo_ddlRepresentado`), busca (`Corpo_ddlTipoFiscalizacao` + `Pesquisar`), tabela (`Corpo_gdvResultado`) e download (`Corpo_gdvResultado_btnVisualizar_N`).
3. Ao longo dos próximos dias, observar quanto tempo a sessão salva permanece válida antes de expirar — isso vai definir a frequência com que o login manual precisa ser refeito.
4. Confirmar os itens pendentes do Bloco 6 (permissão de escrita no SharePoint, aprovação de InfoSec, ponto de contato do TI) e a disponibilidade recorrente da pessoa do login manual — em paralelo, não bloqueiam o código.

## Notas de segurança adicionadas nesta sessão

- `sessao_antt.json` (cookies de sessão ativa) — protegido no `.gitignore` desde 14/09/2026.
- PDFs de autos (`*.pdf`) — contêm CPF de motoristas, CNPJ, endereços; protegidos no `.gitignore` desde 15/09/2026.
- `prints/` e `codigos_site/` — contêm o **nome completo e CPF do representante legal** em texto puro (ex.: telas de login/home) e o CPF também aparece dentro do HTML capturado; protegidos no `.gitignore` em 15/09/2026.
