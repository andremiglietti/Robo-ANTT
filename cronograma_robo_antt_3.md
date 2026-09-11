# Cronograma — Robô de Extração ANTT
**Período:** 14/09 a 30/09, apenas dias úteis (segunda a sexta) · **Ritmo:** ~3h/dia · **Total estimado:** ~39h em 13 dias úteis

> **Premissas confirmadas nesta versão:**
> - Login feito com CPF/senha do representante legal; uma pessoa faz o login **manualmente** para passar o captcha, e o robô reaproveita essa sessão já autenticada.
> - Robô roda **localmente**, sem agendamento automático — a mesma pessoa decide quando disparar a execução (ex.: duplo clique num atalho).
> - Resultado final é salvo numa **pasta local sincronizada com o SharePoint** (via OneDrive), sem integração direta por API.
> - Sem finais de semana neste cronograma — isso remove os dias de buffer que existiam na versão anterior. **O prazo fica mais apertado**; ver observação no fim do documento.

---

## Semana 1 (14/09 a 18/09) — Levantamento + Esqueleto do robô

**Objetivo da semana:** reunir os Blocos 1, 2 e 3 do checklist, validar a captura de sessão do login manual, e já ter o esqueleto de código estruturado.

| Dia | Data | Tarefa (≈3h) |
|---|---|---|
| 1 | Seg 14/09 | Confirmar com a pessoa responsável pelo login uma rotina de disponibilidade (mesmo sem agendamento fixo, ela precisa saber que é a operadora do robô). Confirmar com o TI: qual computador será usado, se o OneDrive pode ser configurado nele com acesso à biblioteca do SharePoint de destino. Comigo: estruturar o projeto (pastas, ambiente Python, Playwright). |
| 2 | Ter 15/09 | Reunir os prints das telas (Bloco 2A): login, seleção de CNPJ, consulta, lista de resultados (com rodapé/paginação), tela de detalhe do auto. |
| 3 | Qua 16/09 | Fazer o "Inspecionar" dos campos de login e do seletor de CNPJ (itens 2.6.1 a 2.6.4). **Teste 1B:** a pessoa loga manualmente uma vez e testamos se conseguimos capturar/reaproveitar essa sessão. Isso valida a arquitetura toda — priorizar. |
| 4 | Qui 17/09 | "Inspecionar" da consulta, tabela de resultados e paginação (2.6.5 a 2.6.8). Conseguir 1 PDF real de auto (Bloco 3.1). |
| 5 | Sex 18/09 | "Inspecionar" do botão de download do PDF (2.6.9). Comigo: escrever a lógica de varredura multi-CNPJ e paginação com os dados coletados. |

**Checkpoint:** até 18/09, a captura de sessão precisa estar validada (item 3), e todo o material de telas/PDF reunido. Sem isso, a Semana 2 não avança.

---

## Semana 2 (21/09 a 25/09) — Núcleo do robô (Core Engine)

**Objetivo da semana:** robô capturando e extraindo dados reais, ponta a ponta, mesmo em escala pequena.

| Dia | Data | Tarefa (≈3h) |
|---|---|---|
| 6 | Seg 21/09 | Testar contra o portal real: login manual → captura de sessão → robô assume o controle. Ajustar com base nos erros. |
| 7 | Ter 22/09 | Testar a varredura de CNPJs (matriz + filiais) e a listagem paginada de processos. |
| 8 | Qua 23/09 | Implementar download dos PDFs + verificação de duplicidade (comparação com o que já foi baixado). |
| 9 | Qui 24/09 | Implementar extração de campos do PDF (placa, data, CIOT/MDF-e, enquadramento legal). |
| 10 | Sex 25/09 | Implementar checkpoint/estado e política de retentativa (distinguindo falha de sessão/rede de falha real do documento). Rodar um ciclo de teste ponta a ponta em escala pequena. |

**Checkpoint:** até 25/09, o robô roda um ciclo completo (login manual → varredura → download → extração), ainda sem cruzar com a base interna nem gravar no SharePoint.

---

## Semana 3 (28/09 a 30/09) — Integração final e entrega

**Objetivo:** cruzar com a base interna, gravar no SharePoint, testar e entregar. Só 3 dias — sem folga.

| Dia | Data | Tarefa (≈3h) |
|---|---|---|
| 11 | Seg 28/09 | Implementar cruzamento com a base interna (Bloco 4) e geração da planilha/relatório final. Implementar a gravação do resultado na pasta local sincronizada com o SharePoint (escrevendo em arquivo temporário e só depois movendo, para evitar conflito de sincronização). |
| 12 | Ter 29/09 | Teste final ponta a ponta com dados reais. Criar o atalho/arquivo de execução simples (duplo clique) para a pessoa operar sem precisar de linha de comando. Escrever um mini-guia de uso para ela. |
| 13 | Qua 30/09 | Revisão geral, ajustes finais e entrega. |

---

## O que mudou em relação à versão anterior

- ❌ **Removida** a espera pela decisão jurídica sobre credencial (já definida: CPF do representante legal).
- ❌ **Removida** a necessidade de configurar agendador (Task Scheduler/cron) — execução é sob demanda.
- ❌ **Removida** a pergunta sobre acesso remoto (RDP/VNC) ao servidor — como a mesma pessoa loga e roda localmente na própria máquina, não há necessidade de acesso remoto para essa etapa.
- ✅ **Adicionada** a etapa de configuração do OneDrive/SharePoint na máquina local (Dia 1).
- ✅ **Adicionado** o cuidado técnico de gravação segura na pasta sincronizada (Dia 11).
- ⚠️ **Removido o buffer de fim de semana** que existia na versão anterior (dias 19, 20, 26, 27) — o cronograma agora não tem dias de folga para absorver imprevistos.

## Riscos atualizados

| Risco | Impacto | Mitigação |
|---|---|---|
| Sem dias de buffer no cronograma (só dias úteis) | Alto — qualquer atraso de 1 dia empurra a entrega para depois de 30/09 | Priorizar rigorosamente o teste de captura de sessão (Dia 3) e o teste ponta a ponta (Dia 10) — são os pontos mais prováveis de gerar retrabalho; se atrasarem, cortar escopo (ex.: adiar o cruzamento com base interna) em vez de atrasar a entrega |
| Pessoa do login manual não está disponível quando necessário | Médio — sem agendamento fixo, depende da rotina dela | Definir uma expectativa informal de frequência (ex.: "pelo menos 1x por semana"), já que sem isso o benefício do robô (detecção rápida de multas) se perde por falta de uso, não por falha técnica |
| Sessão expira no meio do ciclo | Médio — pode interromper capturas em andamento | O robô deve parar de forma controlada e sinalizar que precisa de novo login manual, sem tentar logar sozinho |
| Captura de sessão (Dia 3) não funcionar como esperado | Alto — muda a arquitetura se não for possível reaproveitar a sessão | Validar isso nos primeiros dias, antes de construir o restante em cima dessa premissa |
| OneDrive não sincronizar corretamente (arquivo corrompido/parcial no SharePoint) | Baixo-Médio | Escrever sempre em arquivo temporário e mover/renomear só ao final da geração completa |
| Uso do CPF/senha do representante legal (risco de compliance já conhecido) | Não afeta o prazo diretamente, mas é um risco institucional | Fora do escopo deste cronograma; recomenda-se registro formal da decisão para fins de governança |

## Observação final

Com o corte para dias úteis (13 dias, ~39h) e a remoção do buffer de fim de semana, o cronograma passa a ser **viável, mas sem margem para imprevistos**. Qualquer atraso relevante em algum dos dois testes-chave (captura de sessão no Dia 3, ou teste ponta a ponta no Dia 10) deve disparar uma decisão consciente de cortar escopo — por exemplo, entregar o robô funcionando com extração e planilha, deixando o cruzamento automático com a base interna para uma segunda etapa logo após 30/09 — em vez de tentar recuperar o atraso trabalhando mais horas por dia.
