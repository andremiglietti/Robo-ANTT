# Cronograma — Robô de Extração ANTT
**Período:** 14/09 a 30/09 (17 dias) · **Ritmo:** ~3h/dia · **Total estimado:** ~51h

> Regra de ouro deste cronograma: tudo que depende de **outras pessoas** (jurídico, TI) começa no Dia 1, em paralelo ao seu trabalho — não em sequência. É isso que torna o prazo viável.

---

## Semana 1 (14/09 a 20/09) — Levantamento + Esqueleto do robô

**Objetivo da semana:** reunir os Blocos 1, 2 e 3 do checklist e já ter um esqueleto de código rodando localmente (mesmo sem acesso real ao portal ainda).

> **Premissa confirmada:** o login será feito com CPF/senha do representante legal, e uma pessoa fará o login **manualmente** para passar pelo captcha — o robô assume a sessão já autenticada a partir daí (mesmo modelo do projeto original). Isso remove a espera pelo jurídico, mas cria uma dependência humana recorrente (ver Bloco 1.2-B abaixo e a tabela de riscos atualizada).

| Dia | Data | Tarefa (≈3h) |
|---|---|---|
| 1 | Seg 14/09 | **Disparar em paralelo:** (a) identificar e confirmar com a pessoa que fará o login manual (representante legal ou alguém autorizado por ele) uma janela fixa de disponibilidade recorrente (ex.: toda sexta de manhã); (b) marcar com o TI a conversa sobre infraestrutura (Bloco 6) — inclui decidir *onde* essa pessoa vai logar (direto no servidor do robô, ou em outra máquina, exigindo transferência de sessão). Depois, comigo: começar a estruturar o projeto (pastas, ambiente Python, dependências do Playwright). |
| 1B | (mesma semana) | **Novo item — Bloco 1.2-B:** fazer um teste simples de "captura de sessão": a pessoa loga manualmente uma vez, e verificamos se conseguimos salvar/reaproveitar essa sessão (cookies) para o robô operar em seguida, sem novo login. Esse teste precisa acontecer cedo, porque valida a viabilidade técnica de todo o desenho. |
| 2 | Ter 15/09 | Reunir prints da tela de login + gravar/tirar prints do fluxo de consulta (Bloco 2A completo). |
| 3 | Qua 16/09 | Fazer os "Inspecionar" dos elementos de login e do seletor de CNPJ (itens 2.6.1 a 2.6.4). Comigo: já escrevo a lógica de login com base no que chegar. |
| 4 | Qui 17/09 | Fazer os "Inspecionar" da consulta, tabela de resultados e paginação (itens 2.6.5 a 2.6.8). Conseguir 1 PDF real de auto (Bloco 3.1). |
| 5 | Sex 18/09 | "Inspecionar" do botão de download do PDF (2.6.9). Comigo: escrevo a lógica de varredura multi-CNPJ e paginação com os dados coletados. |
| 6 | Sáb 19/09 | Dia mais leve: revisão do que foi escrito até aqui, ajustes finos, cobrar resposta do jurídico/TI se ainda não veio. |
| 7 | Dom 20/09 | Folga ou buffer, caso algum item da semana tenha atrasado. |

**Checkpoint de fim de semana:** até dia 20, você deveria ter a decisão sobre credencial (ou pelo menos um encaminhamento), todos os prints/Inspecionar do portal, e 1 PDF de exemplo. Sem isso, a Semana 2 trava.

---

## Semana 2 (21/09 a 27/09) — Núcleo do robô (Core Engine)

**Objetivo da semana:** ter o robô capturando e extraindo dados de verdade, ainda que rodando manualmente (sem agendamento automático).

| Dia | Data | Tarefa (≈3h) |
|---|---|---|
| 8 | Seg 21/09 | Testar o login real do robô contra o portal (você roda, eu ajusto com base nos erros/retornos). |
| 9 | Ter 22/09 | Testar a varredura de CNPJs (matriz + filiais) e a listagem paginada de processos. |
| 10 | Qua 23/09 | Implementar o download dos PDFs + verificação de duplicidade (comparação com o que já foi baixado). |
| 11 | Qui 24/09 | Implementar a extração de campos do PDF (placa, data, CIOT/MDF-e, enquadramento), com base no PDF de exemplo. |
| 12 | Sex 25/09 | Implementar checkpoint/estado (para retomar de onde parou) e a política de retentativa em caso de falha do portal. |
| 13 | Sáb 26/09 | Rodar um ciclo de teste ponta a ponta (login → varredura → download → extração) num volume pequeno de CNPJs. |
| 14 | Dom 27/09 | Buffer para corrigir o que falhar no teste do dia 26. |

**Checkpoint de fim de semana:** até dia 27, o robô deveria estar rodando um ciclo completo, mesmo que ainda manualmente e sem o cruzamento com a base interna.

---

## Semana 3 (28/09 a 30/09) — Integração final e entrega

**Objetivo:** cruzar com a base interna, gerar a saída final e fechar a entrega. Só 3 dias — por isso a folga das semanas anteriores é o que sustenta esse prazo.

| Dia | Data | Tarefa (≈3h) |
|---|---|---|
| 15 | Seg 28/09 | Implementar o cruzamento com a base interna (Bloco 4) e gerar a planilha/relatório final. |
| 16 | Ter 29/09 | Teste final ponta a ponta com dados reais; ajustes de última hora; decidir e documentar onde o robô vai rodar (Bloco 6), mesmo que a automação completa do agendamento fique para depois. |
| 17 | Qua 30/09 | Revisão geral, empacotamento do que será entregue (código + instruções de uso) e entrega. |

---

## O que pode furar esse prazo (e o que fazer se acontecer)

| Risco | Impacto | Mitigação |
|---|---|---|
| Pessoa do login manual não está disponível no momento em que o robô precisa rodar | Alto — sem o login manual, o ciclo inteiro não começa | Definir logo no Dia 1 uma janela fixa e recorrente (dia/horário) com essa pessoa, tratando isso como parte do processo operacional, não como favor pontual |
| Sessão expira no meio do ciclo (o robô "perde" a autenticação durante a varredura) | Médio-Alto — pode interromper capturas em andamento | O robô precisa detectar sessão expirada e parar de forma controlada (registrando onde parou), sinalizando que precisa de novo login manual — não deve tentar logar sozinho |
| Captura de sessão (Bloco 1.2-B) não funcionar tecnicamente como esperado | Alto — muda a arquitetura toda se não for possível reaproveitar a sessão | Validar isso já nos primeiros dias (item 1B), antes de construir o restante em cima dessa premissa |
| Uso do CPF/senha do representante legal traz exposição de compliance (risco já conhecido do projeto original) | Não afeta o prazo diretamente, mas é um risco institucional | Fora do escopo deste cronograma, mas recomenda-se registrar formalmente que essa decisão foi tomada e por quem, para fins de governança |
| TI demora para disponibilizar servidor/VPS (Bloco 6) | Baixo para o prazo de 30/09, alto para produção | O robô pode ficar pronto e testado sem estar hospedado definitivamente — a hospedagem final pode ser tratada logo após a entrega, sem bloquear o "código funcionando" |
| Portal muda de layout ou fica instável (como já ocorreu no projeto original) | Médio — exige retrabalho nos seletores | Reservar os dias de buffer (19, 20, 27/09) exatamente para isso |

## Conclusão

O prazo é **viável com meu apoio no desenvolvimento**, desde que as informações dos Blocos 1, 2 e 3 comecem a ser levantadas já no dia 14/09 e a decisão jurídica sobre a credencial seja cobrada em paralelo desde o primeiro dia. O ponto mais frágil não é o código — é o tempo de resposta de pessoas fora do seu controle direto (jurídico e TI). Se algum desses dois travar além do dia 18-20/09, o cronograma da Semana 3 fica insuficiente e a entrega provavelmente precisaria ser renegociada.
