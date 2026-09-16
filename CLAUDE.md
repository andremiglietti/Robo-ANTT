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
   - ✅ **Teste crítico validado (item 1.3 do checklist) — 14/09/2026:** `teste_sessao_1_capturar.py` e `teste_sessao_2_testar.py` foram executados contra o portal real. Resultado: uma nova janela do navegador, carregando apenas a sessão salva (`sessao_antt.json`), abriu **já autenticada na página inicial**, sem precisar reinserir CPF/senha. Confirma que a arquitetura de login manual + reaproveitamento de sessão via `storage_state()` é viável.
   - 🔴 **Achado importante em 16/09/2026 pela manhã — a sessão de 14/09 expirou.** A sessão salva em 14/09 às ~15:58 não funcionava mais em 16/09 às 08:02 (**menos de 40h depois**). O código que detecta isso (`SessaoExpiradaError`) funcionou exatamente como esperado — parou de forma controlada e sinalizou a necessidade de novo login.
   - ✅ A pessoa responsável refez o login manual em 16/09 às 08:07 (nova `sessao_antt.json`), e essa sessão nova foi usada com sucesso em todos os testes ao vivo do resto do dia (ver itens 2-3 abaixo).
   - ⬜ **Ainda não sabemos a duração exata** — só que é "menos de 40h". Não deu pra testar isso de propósito hoje (ver observação de "achados operacionais" abaixo).
2. **Descoberta de CNPJs**: identificar automaticamente todos os CNPJs vinculados (matriz + filiais) a partir da sessão logada.
   - ✅ Confirmado em 15/09/2026: a tela `VistasAoProcesso.aspx` tem um `<select id="Corpo_ddlRepresentado">` com todos os CNPJs (matriz + filiais) da empresa já pré-carregados no HTML (não precisa de chamada extra) — outerHTML capturado em `codigos_site/vistas_ao_processo.docx`.
   - ✅ **`listar_cnpjs()` validado AO VIVO em 16/09/2026** (`src/robo_antt/portal.py`): retornou **61 CNPJs reais** (matriz + filiais) da Yara Brasil Fertilizantes S/A.
3. **Varredura paginada**: percorrer a listagem de processos/autos de infração e tratar a paginação do portal.
   - ✅ Confirmado em 15/09/2026: a tabela de resultados (`table#Corpo_gdvResultado`) e a paginação (`Corpo_ucPaginadorResultado`) só existem no DOM **depois** do clique em "Pesquisar" — são renderizadas via AJAX (UpdatePanel do ASP.NET), não aparecem no HTML estático inicial.
   - 🔴 **Decisão revertida em 16/09/2026 — buscar sem "Tipo de Fiscalização" NÃO funciona.** A ideia original (registrada aqui ontem) era deixar esse filtro em branco pra pegar tudo de uma vez. Testado ao vivo: o "Processando..." trava **indefinidamente** (>20s sem resposta, sem timeout visível) quando o campo fica vazio. **A varredura precisa iterar pelos 7 valores conhecidos de `Corpo_ddlTipoFiscalizacao`** (`TIPOS_FISCALIZACAO` em `config.py`: Excesso de Peso, Cargas, Passageiros, Cargas Internacional, Passageiros Internacional, Infraestrutura Rodoviária, Evasão de Pedágio) — um search por tipo, por CNPJ. Hipótese (não 100% confirmada) de que isso ainda cobre os tipos "extras" vistos nos PDFs: os prefixos `CRGTF`/`CRGPP` (piso mínimo, produtos perigosos) sugerem que caem dentro da categoria **"Cargas"** do dropdown, junto com `FELVP` (vale-pedágio) — o "Tipo de Multa" granular de cada linha continua vindo do cabeçalho da página 1 do PDF (item 5), não do filtro de busca.
   - ✅ **`selecionar_cnpj()` corrigido e validado AO VIVO em 16/09/2026.** A primeira versão usava `select_option(..., force=True)` no `<select>` do Representado — **não funciona**: o `<select>` real fica `display:none` porque o portal usa o plugin `chosen.js` pra desenhar o dropdown visível (o com campo de busca, dos prints). Setar o valor direto via JS deixa o widget visual preso em "Selecione" e a busca trava. A correção clica no widget de verdade e depois no `<li data-option-array-index="N">` correspondente — testado ao vivo, funciona (o texto visível e o valor real do `<select>` ficam consistentes).
   - ✅ **Busca com filtro validada AO VIVO em 16/09/2026** (CNPJ matriz + Tipo de Fiscalização = Excesso de Peso): retornou os mesmos dados vistos manualmente em 15/09 (`EPSMA00087472019`, paginação "1 de 20").
   - ✅ **VARREDURA COMPLETA VALIDADA AO VIVO em 16/09/2026** (portal voltou da manutenção): `varrer_cnpj()` rodou os 7 tipos de fiscalização pra 1 CNPJ (matriz) sem travar nem dar erro — achou **5 processos reais** (3 Excesso de Peso + 2 Passageiros, os outros 5 tipos vazios pra esse CNPJ), em **158s (~2,6 min) por CNPJ**. Com 61 CNPJs no total, uma varredura completa da empresa levaria em torno de **2,5–3h** — dado útil pra dimensionar o uso real (Bloco 5).
   - 🔴 **Bug encontrado e corrigido: o paginador do portal ("X de Y") não é confiável.** Confirmado **manualmente pelo usuário**: o número de páginas mostrado é fixo/decorativo e não reflete a quantidade real de resultados — aparece mesmo quando não há nenhum resultado. Ao clicar em "próxima página" além do que realmente existe, o servidor responde **"Nenhum registro encontrado"** (confirmado inspecionando a resposta HTTP real da requisição AJAX, não só o comportamento da tela). Corrigido: `varrer_busca_atual()` agora para de paginar assim que uma página vier vazia, **independente** do que o paginador diz — não confia mais no "X de Y".
   - 🔴 **Segundo bug encontrado e corrigido: o modal "Processando..." (`#Progress_DivProgress`) às vezes continua na tela e bloqueia o próximo clique** (erro "element intercepts pointer events"), acontecendo entre uma busca e a troca de tipo de fiscalização seguinte. Corrigido: o código agora espera esse modal sumir antes de clicar em "Pesquisar", na próxima página, ou ao selecionar um CNPJ.
   - 🔴 **Terceiro bug encontrado e corrigido (ainda em 16/09/2026, durante os testes de download): o tempo de resposta do portal varia muito** — a mesma busca levou 8s numa hora e mais de 30s (chegando perto de 1 minuto) em outra, sem padrão óbvio. `buscar()` tinha só 1 tentativa de 30s e, ao estourar, assumia "sem resultado" — o que fez o robô **pular um processo real** num dos testes (viu "0 resultados" quando na verdade a busca ainda estava processando). Corrigido: `buscar()` agora tenta esperar de novo até 3 vezes (até ~90s no total) antes de desistir.
   - ⚠️ **Achado técnico à parte:** `page.goto(...)` com `wait_until="load"` ou `"networkidle"` **nunca resolve** nessa tela — trava até estourar o timeout, mesmo com a página já pronta pra uso (aparentemente há alguma requisição de fundo contínua). A correção foi usar `wait_until="commit"` + esperar o seletor específico aparecer, e nunca usar `wait_for_load_state("networkidle")` nessa tela.

**Achados operacionais de 16/09/2026 (importantes pra quando o robô rodar de verdade):**
- **O portal fica indisponível por manutenção, sem aviso prévio.** A causa real de boa parte da "lentidão" observada mais cedo hoje era o portal mostrando a página **"Estamos atualizando o sistema. Por favor, acesse novamente em alguns minutos."** — confirmado inspecionando o conteúdo real da página, não só o comportamento de timeout. Isso não tem nada a ver com sessão expirada nem com volume de requisições do robô.
- O código agora distingue isso corretamente: `abrir_tela_processos()` detecta esse texto e lança um erro específico, **`PortalIndisponivelError`** (diferente de `SessaoExpiradaError`) — importante porque a ação de recuperação é diferente: manutenção = tentar de novo mais tarde (não precisa de login novo); sessão expirada = precisa de login manual novo. Isso alimenta diretamente o item 6 (checkpoint/retentativa), que já previa essa distinção.
- Mesmo com essa causa esclarecida, mantive por precaução uma pausa deliberada entre ações que batem no servidor (`PAUSA_ENTRE_ACOES_MS = 2000` em `config.py`, usada entre troca de tipo de fiscalização e entre páginas) — não custa nada e evita bater no portal sem necessidade, inclusive durante os próprios testes.
- ✅ **Portal voltou e a varredura completa foi validada** (ver item 3 acima) — achados corrigidos no mesmo dia: paginador não confiável, e modal "Processando..." bloqueando cliques seguintes.
4. **Controle de duplicidade**: antes de baixar um auto, verificar se ele já existe no repositório local (arquivo + registro), para não reprocessar o que já foi capturado.
   - ✅ Confirmado em 15/09/2026: o PDF já é baixado com o nome do **número do Auto de Infração** (ex.: `EPSMA00087472019.pdf`), sem precisar renomear.
   - ✅ **`already_downloaded()` implementado e validado em 16/09/2026** (`src/robo_antt/download.py`): como a pasta final depende do tipo de multa (só conhecido depois de abrir o PDF - ver item 5), a checagem faz um glob por `data/downloads/{cnpj}/*/{numero_auto}.pdf`. Testado: encontra o arquivo certo **sem precisar do navegador/sessão** (retorna na hora, não gasta tempo nem toca no portal) — importante pra não desperdiçar as ~2,6min/CNPJ da varredura reprocessando o que já foi baixado.
5. **Download e extração de PDF**: baixar o PDF do auto e extrair campos estruturados. O layout pode variar por tipo de multa (frete mínimo, pedágio, excesso de peso, produtos perigosos).
   - ✅ **Caminho de download confirmado em 15/09/2026, implementado e validado AO VIVO em 16/09/2026** (`baixar_pdf()` em `src/robo_antt/download.py`): na tela `VistasAoProcesso.aspx`, cada linha da tabela de resultados tem um botão-imagem (lupa, `id="Corpo_gdvResultado_btnVisualizar_N"`, `onclick="showProgressJavaScript(solicitarVistas);"`). Ao clicar, o sistema processa e **baixa o PDF do auto diretamente** (download direto do navegador, sem abrir nova aba/visualizador) — apesar do nome da função JS ("solicitar vistas") sugerir um pedido com aprovação futura, na prática o download é imediato/síncrono. Capturado com `page.expect_download()`. **Testado com um processo real** (`EPSMA00087472019`, já arquivado/pago): baixou certo, foi pro caminho certo (`data/downloads/{cnpj}/{tipo_multa}/{auto}.pdf`), e o conteúdo bate (número do auto e CNPJ conferidos no texto extraído).
   - ❌ **Descartado:** a tela "Relatório de Multas" (`/spmi/Site/RelacaoMultas/ConsultarMultas.aspx`) só gera um relatório agregado de todas as multas por CPF — não permite baixar o PDF de um auto individual, então não serve para o fluxo de extração por multa.
   - ✅ **Estrutura do PDF confirmada em 15/09/2026** (5 exemplos analisados: excesso de peso, piso mínimo de frete ×2, produtos perigosos, vale-pedágio): o PDF baixado é o **processo inteiro** (auto + notificação + boleto + recursos + SERASA + arquivamento), podendo ter de 5 a **79 páginas**.
     - Página 1 (sempre) — "AUTO DE INFRAÇÃO [TIPO]": nº do auto, infrator (nome/CNPJ), veículo (placa), data/local da infração, tipificação (código, artigo, resolução, descrição, amparo legal), tipo/nº do documento fiscal.
     - Uma página **posterior** (nº varia, geralmente a "1ª Notificação de Penalidade"/boleto — pg. 7 no exemplo de excesso de peso) — **Valor da multa, Valor com desconto, Data de vencimento e Código de barras** ficam aqui, não na página 1. Ainda não confirmado se esse boleto existe em 100% dos processos (pode não existir se a multa ainda não foi notificada/gerada) — tratar como campo opcional na extração.
   - 🔴 **Achado importante em 16/09/2026 — o PDF do portal tem um bug de fonte.** Testamos 3 bibliotecas de extração de texto em Python (`pypdf`, `pdfplumber`, `PyMuPDF`) e **todas** devolvem "�" no lugar de vogais acentuadas — não é limitação de nenhuma biblioteca específica, é a fonte incorporada no PDF que não mapeia esses caracteres corretamente. Campos sem acento (placa, CNPJ, datas, valores, números de documento) extraem perfeitamente; só texto livre acentuado (descrição da infração, nome do tipo de multa no cabeçalho) vem degradado. `pdfplumber` foi escolhido por ter a ordem de leitura mais próxima do layout visual (`pypdf`/PyMuPDF embaralham a ordem label/valor).
   - ✅ **`identificar_tipo_multa()` implementado em `src/robo_antt/extracao.py`** — classifica o tipo de multa (usado pra decidir a pasta de destino) usando palavras-chave **sem acento** (ex.: "PESO", "FRETE", "PERIGOSOS", "VALE") em vez de comparar o texto inteiro, contornando o bug de fonte. **Validado contra os 5 PDFs de exemplo: acertou os 5.** Tipos que ainda não vimos em exemplo real (Cargas Internacional, Passageiros, Infraestrutura Rodoviária, Evasão de Pedágio) caem em `"Outros"` até termos um PDF de exemplo desses pra mapear a palavra-chave certa.
   - ✅ **`extrair_campos_pagina1()` implementado e validado em 16/09/2026** (`src/robo_antt/extracao.py`): extrai Placa, CNPJ do infrator, Data Autuação, Descrição da Infração, Tipo/Número do Documento Fiscal e Data de Emissão do Documento Fiscal. **Testado contra os 5 PDFs de exemplo: 35/35 campos corretos** (7 campos × 5 tipos de multa).
     - Técnica usada: em vez de regex no texto corrido (ordem de leitura não confiável - ver acima), usa `pdfplumber.extract_tables()`, que devolve cada campo como uma célula `"RÓTULO\nVALOR"` (o PDF é um formulário com bordas) — muito mais robusto. Os rótulos variam de nome entre os 5 tipos (ex.: "Nº DO DOCUMENTO" vs "NÚMERO DO DOCUMENTO", "CNPJ/CPF" vs "CPF/CNPJ", "TIPO DE DOCUMENTO" vs "TIPO DO DOCUMENTO") — os padrões de busca foram escritos pra tolerar as variações vistas nos 5 exemplos.
     - "Descrição da Infração" sai com o bug de acentuação (`�`) do PDF, mas os demais campos (sem acento) saem limpos.
   - ✅ **Extração da página do boleto implementada e validada em 16/09/2026** (`localizar_pagina_boleto()` + `extrair_campos_boleto()` em `src/robo_antt/extracao.py`): extrai `Data Vencimento`, `Valor`, `Valor Desconto`, `Código de Barras` e a data de emissão do boleto.
     - **Achado de performance:** localizar a página certa com `pdfplumber` é lento demais em processos grandes (30 páginas ≈ 50s). Trocado por **PyMuPDF** só para essa busca (30 páginas ≈ 0,5s — ~90x mais rápido), mantendo `pdfplumber` para extrair os campos da página já localizada (ele lê a ordem visual melhor). O boleto pode estar em qualquer lugar do PDF, não só perto do início — visto na página 57 de 69 num dos exemplos.
     - Sinal usado pra achar a página certa: presença de **"NOSSO Nº" + "VENCIMENTO"** juntos — testado que só "MULTA"/"VENCIMENTO" dá falso positivo (uma página de termo de adesão genérico menciona os dois numa frase, sem ser boleto de verdade).
     - **Confirmado com dados reais: nem todo processo tem página de boleto** (2 dos 5 exemplos não têm — o de piso mínimo em andamento e o de vale-pedágio recente) — a função retorna `None` nesse caso, sem erro, exatamente como o CLAUDE.md já previa.
     - Dois formatos de boleto bem diferentes encontrados nos exemplos (o de "auto de trânsito" clássico, com células de tabela limpas, e o "GRU - Guia de Recolhimento da União", com o valor do desconto embutido numa frase de instrução em vez de uma célula separada) — a extração tenta os dois formatos. **Testado nos 3 exemplos com boleto: todos os campos corretos.**
   - ✅ **`Data Emissão Notificação` resolvida em 16/09/2026** (`localizar_pagina_notificacao()` + `extrair_data_emissao_notificacao()`): essa data é de uma página **diferente** do boleto — a "Notificação da Autuação", que vem *antes* do boleto e não tem "NOSSO Nº"/"VENCIMENTO" (por isso precisa de uma busca separada, não dava pra reaproveitar `localizar_pagina_boleto()`).
     - ⚠️ Achado: a busca **não pode considerar a página 1** — em vários tipos de auto, a página 1 menciona "notificação de autuação" de passagem dentro de uma frase jurídica genérica (ex.: "...contados do recebimento da notificação de autuação..."), dando falso positivo. A função pula a página 1 de propósito e só considera a partir da página 2.
     - **Testado nos 5 exemplos: os 5 corretos**, incluindo os 2 tipos mais novos/eletrônicos (vale-pedágio, piso mínimo via MDF-e) que têm essa notificação numa página própria mesmo (achado revisado — a suposição anterior de que "já vem embutida na página 1" para esses tipos estava errada).
   - **Com isso, a planilha final tem todas as 15 colunas cobertas pela extração** (`Link do Arquivo` e `Situação`/`Data do Auto` vêm da varredura; os outros 13 campos do PDF, entre página 1, boleto e notificação).
   - ⚠️ **O "documento fiscal" NÃO é sempre CIOT/MDF-e** — o campo "Tipo de Documento" observado varia por auto: `DANFE` (excesso de peso, produtos perigosos), `MDFE` (vale-pedágio, piso mínimo em 1 dos 2 exemplos) ou `CONTRATO DE TRANSPORTE` (piso mínimo no outro exemplo). A extração precisa ler o par "Tipo de Documento" + "Número do Documento" genericamente, não assumir CIOT/MDF-e fixo.
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
- Sessão pode expirar no meio de um ciclo — o robô deve parar de forma controlada e sinalizar a necessidade de novo login, não tentar contornar sozinho. ⚠️ Confirmado em 16/09/2026 que a expiração é rápida (menos de 40h) — ver item 1 da arquitetura. Isso pode exigir login manual bem mais frequente do que o esperado inicialmente.
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
- `src/robo_antt/config.py` — caminhos (sessão, downloads, output) e seletores confirmados do portal.
- `src/robo_antt/portal.py` — navegação: abrir sessão salva, distinguir sessão expirada (`SessaoExpiradaError`) de portal em manutenção (`PortalIndisponivelError`), listar CNPJs, selecionar CNPJ/tipo de fiscalização, buscar processos e percorrer a paginação (tolerando o paginador não confiável e o modal "Processando..." travado). Escrito e **validado ao vivo por completo em 16/09/2026** — varredura de 1 CNPJ pelos 7 tipos, achando processos reais, sem travar.
- `scripts/testar_varredura.py` — script de teste (só leitura, não baixa PDF nem solicita vistas) para validar a varredura ponta a ponta.
- `src/robo_antt/extracao.py` — extração **completa** de campos do PDF (`pdfplumber` + `pymupdf`): tipo de multa, campos da página 1 (placa, CNPJ, data, descrição, documento fiscal), campos do boleto (vencimento, valor, desconto, código de barras, data de emissão) e data de emissão da notificação — localizando as páginas certas dentro de processos de até 79 páginas. Tolerante ao bug de acentuação do PDF e às variações de rótulo/layout entre os 5 tipos de multa. **Validado nos 5 PDFs de exemplo: todos os campos corretos**, incluindo os 2 casos sem boleto (corretamente vazio, não erro).
- `src/robo_antt/download.py` — clica na lupa da linha, captura o download, identifica o tipo de multa e salva em `data/downloads/{cnpj}/{tipo_multa}/{auto}.pdf`; checagem de duplicidade sem precisar abrir o navegador. **Validado ao vivo em 16/09/2026** com um processo real (`EPSMA00087472019`).

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
- Bloco 5 (volume de CNPJs/multas por mês) — não bloqueia, e já temos uma estimativa de tempo de execução (ver item 3 da arquitetura: ~2,6 min/CNPJ, ~2,5–3h pra varrer os 61 CNPJs).
- Bloco 6.3–6.5 (permissão de escrita no SharePoint, aprovação de InfoSec, ponto de contato do TI) — tarefas de negócio, não técnicas.
- Confirmação de disponibilidade recorrente da pessoa do login manual (Dia 1, item 1.2 parcial) — **ganhou urgência** com o achado de que a sessão dura menos de 40h (e nos testes de hoje, às vezes bem menos que isso).

**Ou seja: os Blocos 1–3 do checklist estão fechados, e a varredura + download do PDF + extração COMPLETA de campos estão escritos e validados** — ao vivo contra o portal real (varredura, download) e contra os 5 PDFs de exemplo (extração, 100% dos campos corretos) — inclusive corrigindo diversos bugs reais que só apareceram testando contra o sistema de verdade (hack do `chosen.js`, busca sem filtro de tipo travando, paginador não confiável, modal "Processando..." bloqueando cliques, tempo de resposta variável, bug de fonte do PDF, páginas de boleto/notificação em posição variável). Falta juntar as peças num fluxo único e gerar a planilha Excel de fato.

## Próximos passos sugeridos

1. ~~Testes de sessão, estruturação do projeto, Bloco 2 (prints/Inspecionar), Bloco 3 (PDF de exemplo), definição da saída~~ — tudo concluído (14–15/09/2026).
2. ~~Escrever e validar ao vivo a lógica de varredura multi-CNPJ, busca por tipo e paginação~~ — feito e validado por completo em 16/09/2026 (`src/robo_antt/portal.py`).
3. ~~Escrever e validar ao vivo o download do PDF + identificação do tipo de multa~~ — feito em 16/09/2026 (`src/robo_antt/download.py`, `src/robo_antt/extracao.py`).
4. ~~Extrair todos os campos do PDF (página 1, boleto, notificação)~~ — feito e validado em 16/09/2026, 100% dos campos corretos nos 5 exemplos (`src/robo_antt/extracao.py`).
5. **Gerar a planilha Excel final** (`openpyxl` ou similar): criar se não existir, atualizar se existir, juntando os dados da varredura (Número do Processo, Auto de Infração, Situação, Data do Auto) com os da extração do PDF (as 13 colunas restantes) — Dia 11 do cronograma antecipado.
6. Escrever um `main.py`/script orquestrador que liga tudo: varredura → checa duplicidade → baixa → extrai → grava na planilha, com checkpoint/retentativa (JSON de estado entre execuções, item 6 da arquitetura) e gravação seguindo o cuidado de arquivo temporário na pasta do SharePoint.
7. Confirmar os itens pendentes do Bloco 6 (permissão de escrita no SharePoint, aprovação de InfoSec, ponto de contato do TI) — em paralelo, não bloqueia o código.

## Notas de segurança adicionadas nesta sessão

- `sessao_antt.json` (cookies de sessão ativa) — protegido no `.gitignore` desde 14/09/2026.
- PDFs de autos (`*.pdf`) — contêm CPF de motoristas, CNPJ, endereços; protegidos no `.gitignore` desde 15/09/2026.
- `prints/` e `codigos_site/` — contêm o **nome completo e CPF do representante legal** em texto puro (ex.: telas de login/home) e o CPF também aparece dentro do HTML capturado; protegidos no `.gitignore` em 15/09/2026.
