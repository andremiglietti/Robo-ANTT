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
   - ❌ **Decisão: sem workers/paralelismo, ao contrário do robô de referência do benchmarking.** O usuário perguntou se valeria usar múltiplos "workers" (abas/processos em paralelo) pra acelerar, como o outro projeto fazia. Testado ao vivo em 16/09/2026: abri 2 abas de verdade na MESMA sessão (o cookie é compartilhado entre abas, confirmado pelo usuário), disparando buscas **simultâneas** (via `asyncio.gather`, não só teoricamente) em 2 CNPJs diferentes. Resultado: uma aba respondeu certo mas mais lenta que o normal (34s), a **outra travou e nunca respondeu** (45s+ sem nada, nem "vazio"). Bate com a hipótese de que esse portal (ASP.NET WebForms) trava/enfileira a sessão no servidor por requisição — comum nesse tipo de sistema. **Conclusão: manter sequencial** (1 sessão, 1 aba, 1 CNPJ por vez) — paralelismo aqui parece não só arriscado (pode travar o robô) como provavelmente não traria ganho real de velocidade nesse portal específico. O robô de referência provavelmente tinha uma arquitetura diferente (múltiplas sessões independentes, ou um portal mais tolerante a concorrência) que não se aplica aqui sem testar.
   - 💡 Se a velocidade da varredura virar um problema real no futuro, a etapa de **extração de PDF já baixado** (não toca no portal, só lê arquivo local) é 100% segura de paralelizar - diferente da varredura/download, que ficam de fora dessa ideia pelo motivo acima.
   - 🔴 **Bug encontrado e corrigido: o paginador do portal ("X de Y") não é confiável.** Confirmado **manualmente pelo usuário**: o número de páginas mostrado é fixo/decorativo e não reflete a quantidade real de resultados — aparece mesmo quando não há nenhum resultado. Ao clicar em "próxima página" além do que realmente existe, o servidor responde **"Nenhum registro encontrado"** (confirmado inspecionando a resposta HTTP real da requisição AJAX, não só o comportamento da tela). Corrigido: `varrer_busca_atual()` agora para de paginar assim que uma página vier vazia, **independente** do que o paginador diz — não confia mais no "X de Y".
   - 🔴 **Segundo bug encontrado e corrigido: o modal "Processando..." (`#Progress_DivProgress`) às vezes continua na tela e bloqueia o próximo clique** (erro "element intercepts pointer events"), acontecendo entre uma busca e a troca de tipo de fiscalização seguinte. Corrigido: o código agora espera esse modal sumir antes de clicar em "Pesquisar", na próxima página, ou ao selecionar um CNPJ.
   - 🔴 **Terceiro bug encontrado e corrigido (ainda em 16/09/2026, durante os testes de download): o tempo de resposta do portal varia muito** — a mesma busca levou 8s numa hora e mais de 30s (chegando perto de 1 minuto) em outra, sem padrão óbvio. `buscar()` tinha só 1 tentativa de 30s e, ao estourar, assumia "sem resultado" — o que fez o robô **pular um processo real** num dos testes (viu "0 resultados" quando na verdade a busca ainda estava processando). Corrigido: `buscar()` agora tenta esperar de novo até 3 vezes (até ~90s no total) antes de desistir.
   - ✅✅ **TESTE EM ESCALA MAIOR — 16/09/2026 (à tarde): 90 multas reais processadas de ponta a ponta com sucesso** (1 CNPJ, tipo Excesso de Peso, processos de **2014 a 2023**) — todos os 15 campos da planilha saíram corretos, incluindo formatos de placa antigos e novos, valores, datas em sequência coerente e código de barras. Essa é a validação mais forte até agora de que o robô funciona em escala real, não só nos exemplos pequenos testados antes.
   - 🔴 **Quarto bug encontrado e corrigido (mesmo teste): o fechamento do modal de confirmação (achado anterior) não era robusto o bastante.** Em ~20 downloads seguidos, o modal `#divMensagemPesquisa` ficou aberto e travou **todos** os cliques seguintes pelo resto da execução (não só o próximo) — o timeout de 15s pra detectar o modal aparecendo era curto demais nesse portal. Corrigido: timeout bem mais generoso (45s) e, mais importante, `baixar_pdf()` agora chama `preparar_para_clicar()` **antes** de cada clique também (não só depois do download) — se um modal ficou pendurado de qualquer chamada anterior por qualquer motivo, a próxima chamada se autocorrige em vez de ficar travada pro resto da execução. O mesmo `preparar_para_clicar()` foi aplicado em `buscar()`, `ir_proxima_pagina()` e `selecionar_cnpj()` também, por consistência.
   - 🔴 **Quinto bug: um TERCEIRO modal desconhecido (`#divMensagem`)**, genérico, apareceu bloqueando cliques em ~5 downloads que vieram com problema (ver achado seguinte). Tratado da mesma forma (`fechar_modal_mensagem_generica()`) — mas o id do botão "Ok" (`#MessageBox_ButtonOk`) foi **inferido pelo padrão de nomenclatura** dos outros modais, não confirmado com outerHTML capturado ao vivo dessa modal específica. Vale confirmar/ajustar se aparecer de novo.
   - 🔴 **Sexto achado: alguns downloads vêm com a página HTML do portal em vez do PDF de verdade.** Em 5 dos ~97 downloads desse teste, o "PDF" capturado começava com `<!DOCTYPE html...>` em vez de `%PDF-` — provavelmente um erro do servidor específico desses documentos (todos com prefixos de auto nunca vistos antes: `EPSB2`, `EPSC1`, `EPSC2`). Sem correção, isso teria **corrompido silenciosamente** o resultado (um HTML salvo com nome de `.pdf`). Corrigido: `baixar_pdf()` agora valida os primeiros bytes do arquivo (`%PDF-`) antes de aceitar o download como válido - se não for um PDF de verdade, apaga o arquivo temporário e falha esse documento específico (fica registrado no checkpoint pra revisão manual, não trava a execução).
   - 📋 **Novos formatos de número de auto vistos** (processos antigos, 2014-2016): puramente numéricos, sem prefixo de letras (ex.: `0001443878`) - diferente do padrão `EPSMA.../CRGTF...` visto nos exemplos mais recentes. Não precisou de nenhum ajuste no código (o número é tratado como texto opaco em todo lugar), só registro pra referência futura.
   - 📋 **Um caso na pasta "Outros" (tipo não identificado) revelou uma exceção à regra "página 1 sempre tem o essencial":** o auto `CRGPF00004092019` foi baixado, mas sua página 1 é um **"Comprovante de erro retornado ao cadastrar crédito na Dívida Ativa"**, não o auto de infração em si - aparentemente pra esse processo específico (mais antigo), o PDF "Vistas" devolvido tem uma composição de páginas diferente do padrão. Caiu corretamente na pasta `Outros` pra revisão manual, sem quebrar a extração dos outros 89 documentos - o sistema de fallback funcionou como esperado.
   - ⚠️ **Achado técnico à parte:** `page.goto(...)` com `wait_until="load"` ou `"networkidle"` **nunca resolve** nessa tela — trava até estourar o timeout, mesmo com a página já pronta pra uso (aparentemente há alguma requisição de fundo contínua). A correção foi usar `wait_until="commit"` + esperar o seletor específico aparecer, e nunca usar `wait_for_load_state("networkidle")` nessa tela.

**Achados operacionais de 16/09/2026 (importantes pra quando o robô rodar de verdade):**
- **O portal fica indisponível por manutenção, sem aviso prévio.** A causa real de boa parte da "lentidão" observada mais cedo hoje era o portal mostrando a página **"Estamos atualizando o sistema. Por favor, acesse novamente em alguns minutos."** — confirmado inspecionando o conteúdo real da página, não só o comportamento de timeout. Isso não tem nada a ver com sessão expirada nem com volume de requisições do robô.
- O código agora distingue isso corretamente: `abrir_tela_processos()` detecta esse texto e lança um erro específico, **`PortalIndisponivelError`** (diferente de `SessaoExpiradaError`) — importante porque a ação de recuperação é diferente: manutenção = tentar de novo mais tarde (não precisa de login novo); sessão expirada = precisa de login manual novo. Isso alimenta diretamente o item 6 (checkpoint/retentativa), que já previa essa distinção.
- Mesmo com essa causa esclarecida, mantive por precaução uma pausa deliberada entre ações que batem no servidor (`PAUSA_ENTRE_ACOES_MS = 2000` em `config.py`, usada entre troca de tipo de fiscalização e entre páginas) — não custa nada e evita bater no portal sem necessidade, inclusive durante os próprios testes.
- ✅ **Portal voltou e a varredura completa foi validada** (ver item 3 acima) — achados corrigidos no mesmo dia: paginador não confiável, e modal "Processando..." bloqueando cliques seguintes.
- ⚠️ **Correção de um achado anterior:** o primeiro teste ao vivo da varredura completa (mais cedo em 16/09) tinha reportado "5 processos (3 Excesso de Peso + 2 Passageiros)" pro CNPJ matriz. Testado de novo depois, já com o código mais maduro (detecção de página vazia corrigida): "Passageiros" retorna **0 resultados** pra esse CNPJ, de forma consistente e reproduzível. A leitura de "2 Passageiros" foi provavelmente um efeito de um bug que já existia naquela hora e só foi corrigido depois (a tabela pode ter sido lida antes do AJAX da troca de tipo terminar, mostrando dado antigo) - não um dado real que "sumiu". Fica o registro pra não gerar confusão se alguém comparar os números depois.
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
   - ✅ **Implementado e validado ao vivo em 16/09/2026** (`src/robo_antt/checkpoint.py`): `data/output/checkpoint.json` guarda os autos já processados com sucesso e as falhas (com motivo) - autos já processados são pulados em execuções futuras sem reprocessar. `SessaoExpiradaError`/`PortalIndisponivelError` sobem e param a execução inteira (não marcam falha de documento); qualquer outro erro (de 1 documento específico, ou de navegação num tipo/CNPJ) é capturado, registrado e a varredura continua pros próximos.
   - ✅ **Orquestrador implementado e validado ao vivo** (`src/robo_antt/orquestrador.py`, função `rodar()`): liga varredura → checagem de duplicidade → download → extração → planilha, salvando planilha e checkpoint **a cada CNPJ concluído** (não só no final - uma varredura completa pode levar horas, ver estimativa no item 3).
   - 🔴 **Achado ao vivo em 16/09/2026 — outro modal bloqueando cliques.** Depois de CADA download (clique na lupa), o portal abre um modal de confirmação ("Vistas ao Processo Solicitada com Sucesso!" + pesquisa de satisfação, `#divMensagemPesquisa`) que fica aberto até ser fechado, bloqueando o próximo clique (busca seguinte, próxima página, ou próximo download). Corrigido: `fechar_modal_confirmacao_download()` em `portal.py` marca "Não Responder" e clica "Ok" automaticamente logo depois de cada download (chamado dentro de `baixar_pdf()`) - o robô não deve interagir com a pesquisa de satisfação da ANTT.
   - ✅ **Teste ao vivo completo:** rodou o orquestrador pra 1 CNPJ, todos os 7 tipos de fiscalização - baixou os PDFs novos que faltavam (incluindo o que falhou antes da correção do modal, confirmando o fix), preencheu a planilha corretamente, e terminou sem erro mesmo com a maioria dos tipos vazios (o robô distingue "sem resultado" de erro de verdade).
7. **Saída**: gravar o resultado consolidado (planilha) na pasta sincronizada com o SharePoint, com o cuidado de escrita em arquivo temporário mencionado acima.
   - ✅ **`src/robo_antt/planilha.py` implementado e validado em 16/09/2026:** cria a planilha com o cabeçalho certo se não existir, abre e preserva o conteúdo se já existir; `ja_registrado()` evita duplicar linha pro mesmo auto (complementa a checagem de arquivo em `download.py` - protege até contra o caso do PDF já existir de uma execução anterior mas a linha não ter sido gravada por algum motivo); grava com o mesmo cuidado de arquivo temporário + troca das outras saídas.
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

## Estrutura do projeto (estruturada em 14/09/2026, robô completo em 16/09/2026)

```
Robo-ANTT/
├── CLAUDE.md               # este arquivo
├── requirements.txt         # dependências Python (playwright, pdfplumber, pymupdf, openpyxl)
├── .gitignore               # exclui sessão salva, PDFs, prints/código do portal, downloads, saída, venv
├── .venv/                   # ambiente virtual Python (não versionado)
├── src/robo_antt/           # pacote Python do robô
│   ├── config.py             # caminhos, seletores do portal, tipos de fiscalização
│   ├── portal.py              # navegação: sessão, CNPJs, busca, paginação, modais
│   ├── download.py            # baixa o PDF (clique na lupa) e organiza por CNPJ/tipo
│   ├── extracao.py            # extrai todos os campos do PDF (página 1, boleto, notificação)
│   ├── planilha.py            # cria/atualiza a planilha Excel final
│   ├── checkpoint.py          # estado persistente entre execuções
│   └── orquestrador.py        # liga tudo - ponto de entrada principal (rodar())
├── scripts/                 # scripts avulsos executáveis
│   ├── teste_sessao_1_capturar.py
│   ├── teste_sessao_2_testar.py
│   └── testar_varredura.py
├── prints/                  # [NÃO versionado] prints de todas as telas do portal (login, home, consulta, tabela paginada)
├── codigos_site/            # [NÃO versionado] outerHTML (.docx/.txt) dessas mesmas telas — usado pra achar os seletores reais
├── data/
│   ├── sessao/               # sessao_antt.json (cookies — nunca versionar)
│   ├── downloads/            # PDFs baixados, organizados por CNPJ/tipo de multa — nunca versionar
│   └── output/                # checkpoint.json (estado interno do robô — local de propósito, não sincroniza)
└── docs/                    # material de apoio e planejamento
    ├── checklist_robo_antt.md
    ├── cronograma_robo_antt_3.md      # cronograma vigente (substitui a versão anterior)
    ├── arquitetura_solucao_antt.md / .html
    ├── apresentacao_antt_telas.pptx
    ├── painel_progresso_antt.html
    └── Bench ANTT.srt
```

Ambiente Python: `.venv` criado com Python 3.13; dependências em `requirements.txt`; navegador Chromium do Playwright já baixado (`python -m playwright install chromium`). Para reativar o ambiente: `.venv\Scripts\activate` (PowerShell). Rodar o robô: `python -c "from robo_antt.orquestrador import rodar; rodar()"` (com `src/` no `PYTHONPATH`, ou de dentro de `src/`) — ainda sem um atalho/CLI amigável pra pessoa não-técnica (Dia 12 do cronograma).

**Saída do robô (fora do repositório, pasta sincronizada com o OneDrive/SharePoint):**
```
C:\Users\a847468\OneDrive - Yara International ASA\Dados ANTT\
├── Relatorio_Multas.xlsx     # planilha final (as 15 colunas)
└── Autos\
    └── {cnpj}\{tipo_multa}\{auto_infracao}.pdf
```

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
- `src/robo_antt/download.py` — clica na lupa da linha, captura o download, fecha o modal de confirmação/pesquisa de satisfação que aparece depois, identifica o tipo de multa e salva em `data/downloads/{cnpj}/{tipo_multa}/{auto}.pdf`; checagem de duplicidade sem precisar abrir o navegador. **Validado ao vivo em 16/09/2026** com processos reais.
- `src/robo_antt/checkpoint.py` — estado persistente entre execuções (`data/output/checkpoint.json`): autos já processados (pra não repetir) e falhas por documento (com motivo). **Validado ao vivo.**
- `src/robo_antt/planilha.py` — cria/atualiza a planilha Excel final (`data/output/relatorio_multas.xlsx`), com checagem de duplicidade por linha e gravação seguindo o cuidado de arquivo temporário. **Validado ao vivo.**
- `src/robo_antt/orquestrador.py` — liga tudo (varredura → download → extração → planilha), com checkpoint e tratamento de falha por CNPJ/tipo sem derrubar a execução inteira. **Validado ao vivo, ponta a ponta**, com um CNPJ real e os 7 tipos de fiscalização.

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

**O robô está funcionalmente completo de ponta a ponta** (login/sessão → varredura → download → extração → planilha → checkpoint), escrito e validado ao vivo contra o portal real e contra os 5 PDFs de exemplo — corrigindo cerca de 10 bugs reais ao longo do dia que só apareceram testando contra o sistema de verdade. **A saída já está apontada pra pasta real sincronizada com o OneDrive/SharePoint** (ver abaixo). O que falta agora é (a) itens de negócio do Bloco 6, e (b) rodar numa escala maior/real antes da entrega.

✅ **Caminho do OneDrive/SharePoint confirmado e configurado em 16/09/2026:** `C:\Users\a847468\OneDrive - Yara International ASA\Dados ANTT` (`SHAREPOINT_DIR` em `config.py`). Estrutura:
  - `Dados ANTT\Relatorio_Multas.xlsx` — a planilha final (`PLANILHA_PATH`).
  - `Dados ANTT\Autos\{cnpj}\{tipo_multa}\{auto}.pdf` — os PDFs baixados (`DOWNLOAD_DIR`).
  - O checkpoint (`checkpoint.json`) continua **local** (`data/output/`, não sincronizado) — é memória interna do robô, não um entregável, e escrever nele a cada CNPJ geraria sincronização do OneDrive à toa.
  - Testado (sem gastar outro clique real no portal): `planilha.py` grava corretamente em `Dados ANTT\Relatorio_Multas.xlsx`, e `download.already_downloaded()` resolve o caminho novo certo.

## Próximos passos sugeridos

1. ~~Testes de sessão, estruturação do projeto, Bloco 2 (prints/Inspecionar), Bloco 3 (PDF de exemplo), definição da saída~~ — tudo concluído (14–15/09/2026).
2. ~~Escrever e validar ao vivo a lógica de varredura multi-CNPJ, busca por tipo e paginação~~ — feito e validado por completo em 16/09/2026 (`src/robo_antt/portal.py`).
3. ~~Escrever e validar ao vivo o download do PDF + identificação do tipo de multa~~ — feito em 16/09/2026 (`src/robo_antt/download.py`, `src/robo_antt/extracao.py`).
4. ~~Extrair todos os campos do PDF (página 1, boleto, notificação)~~ — feito e validado em 16/09/2026, 100% dos campos corretos nos 5 exemplos (`src/robo_antt/extracao.py`).
5. ~~Gerar a planilha Excel final~~ — feito e validado em 16/09/2026 (`src/robo_antt/planilha.py`).
6. ~~Escrever o orquestrador (varredura → duplicidade → download → extração → planilha) com checkpoint/retentativa~~ — feito e validado ao vivo em 16/09/2026 (`src/robo_antt/orquestrador.py`, `src/robo_antt/checkpoint.py`).
7. ~~Trocar `DOWNLOAD_DIR`/`PLANILHA_PATH` pelo caminho real da pasta sincronizada com o OneDrive/SharePoint~~ — feito em 16/09/2026 (`C:\Users\a847468\OneDrive - Yara International ASA\Dados ANTT`, ver acima). Ainda falta confirmar que essa conta tem permissão de **escrita** ali de verdade (Bloco 6.3) - o teste de hoje só validou que o caminho existe e o robô sabe escrever nele localmente, não testou a sincronização de fato subir pro SharePoint.
8. ~~Rodar um teste em escala maior~~ — feito em 16/09/2026: **90 multas reais processadas com sucesso** (1 CNPJ, 1 tipo, processos de 2014-2023), achando e corrigindo mais 3 bugs no caminho (modal de confirmação não fechava direito em execuções longas, um terceiro modal desconhecido, downloads que vinham como HTML em vez de PDF). Ainda vale rodar um teste cobrindo **múltiplos CNPJs e múltiplos tipos** de uma vez antes de considerar a empresa toda (~2,5-3h) - o de hoje validou profundidade (1 combinação, muitos documentos), falta validar amplitude (várias combinações).
9. Confirmar os itens pendentes do Bloco 6 (permissão de escrita no SharePoint, aprovação de InfoSec, ponto de contato do TI) — em paralelo, não bloqueia o código.
10. Dia 12 do cronograma: criar o atalho de execução (duplo clique) e um mini-guia de uso pra pessoa responsável, que não é técnica.

## Notas de segurança adicionadas nesta sessão

- `sessao_antt.json` (cookies de sessão ativa) — protegido no `.gitignore` desde 14/09/2026.
- PDFs de autos (`*.pdf`) — contêm CPF de motoristas, CNPJ, endereços; protegidos no `.gitignore` desde 15/09/2026.
- `prints/` e `codigos_site/` — contêm o **nome completo e CPF do representante legal** em texto puro (ex.: telas de login/home) e o CPF também aparece dentro do HTML capturado; protegidos no `.gitignore` em 15/09/2026.
