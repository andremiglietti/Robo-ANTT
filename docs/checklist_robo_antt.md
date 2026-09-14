# Checklist — Informações Necessárias para Replicar o Robô de Extração ANTT

> Este checklist reúne tudo o que precisa ser providenciado para desenvolver o robô. Os itens estão organizados por bloco e por prioridade. Não é necessário ter conhecimento técnico para preencher nenhum deles — as instruções explicam passo a passo.

> **Decisões já confirmadas** (não fazem mais parte do levantamento, mas ficam registradas aqui):
> - Login será feito com CPF/senha do **representante legal**.
> - O login será feito **manualmente por uma pessoa**, para passar pelo captcha — o robô assume a sessão já autenticada a partir daí.
> - O robô vai rodar **localmente**, na máquina da própria pessoa responsável, **sob demanda** (sem agendamento automático) — ela decide quando disparar a execução.
> - O resultado final será salvo numa **pasta local sincronizada com o SharePoint** via OneDrive.

---

## 🔴 Bloco 1 — Login e Sessão

**☐ 1.1 Confirmar qual é o portal exato usado hoje**
- **O que é:** o nome do sistema onde vocês consultam as multas (ex.: SIFAMA, "Área do Autuado").
- **Por quê:** cada sistema tem uma estrutura de tela diferente; o robô precisa ser desenhado para o sistema certo.
- **Como conseguir:** pergunte a quem consulta o portal manualmente hoje: "qual site/sistema você acessa e qual o link exato (URL)?"

**☐ 1.2 Confirmar quem é a pessoa responsável pelo login manual e sua disponibilidade**
- **O que é:** já que não há agendamento automático, é essa pessoa quem decide quando o robô roda — mas ela precisa estar ciente de que é a "operadora" da ferramenta.
- **Por quê:** sem uma rotina mínima combinada, o robô fica parado sem ninguém lembrar de usá-lo, perdendo o principal benefício (detecção rápida das multas).
- **Como conseguir:** uma conversa direta com essa pessoa, alinhando expectativa de frequência de uso (ex.: "pelo menos uma vez por semana").

**☐ 1.3 Testar a captura/reaproveitamento da sessão de login**
- **O que é:** um teste em que a pessoa loga manualmente uma vez, e verificamos se é possível salvar essa sessão (cookies) para o robô reaproveitar sem precisar de novo login a cada execução.
- **Por quê:** essa é a base de toda a arquitetura técnica — se não for possível reaproveitar a sessão, o desenho do robô muda.
- **Como conseguir:** isso é feito em conjunto comigo, mas depende da pessoa estar disponível para logar durante o teste.

---

## 🔴 Bloco 2 — Telas do Portal: Prints e "Inspecionar"

Eu não tenho acesso à internet nem a credenciais de vocês, então preciso **ver** as telas — tanto sua aparência (print) quanto seu código por trás (Inspecionar) — para desenhar o caminho que o robô vai seguir.

### 2A — Prints simples de cada tela

**☐ 2.1** Print (ou vídeo curto) da tela de login

**☐ 2.2** Print da tela onde aparece a lista de CNPJs (matriz e filiais)

**☐ 2.3** Print da tela onde se consulta os processos/autos de infração, incluindo os filtros disponíveis

**☐ 2.4** Print da lista de resultados da consulta, incluindo o **rodapé** (para ver a paginação: números de página, "próximo", "carregar mais", etc.)

**☐ 2.5** Print da tela de detalhe de um auto, mostrando o botão/link de baixar o PDF

> 💡 Dica: se for mais fácil, um vídeo de tela de 2-3 minutos navegando do login até baixar um PDF substitui todos esses prints.

### 2B — O "Inspecionar" das páginas (o código por trás da tela)

**O que é isso e por que é importante:** por trás de toda página existe um código (HTML) que diz onde fica cada botão, campo e link. O robô não "vê" a tela como um humano — ele lê esse código para saber, por exemplo, onde digitar o CPF ou qual link baixa o PDF. Um print mostra *como a página parece*; o "Inspecionar" mostra *como ela é feita por dentro* — e essa segunda informação é o que realmente define se o robô vai funcionar.

**Como abrir o "Inspecionar" (Chrome, Edge e a maioria dos navegadores):**
1. Abra a página do portal normalmente.
2. Clique com o **botão direito do mouse** sobre o elemento desejado (ex.: campo de CPF).
3. No menu, clique em **"Inspecionar"** (ou "Inspect").
4. Um painel com código vai abrir, com o trecho referente ao elemento **destacado em azul/cinza**.
5. Clique com o botão direito **sobre a linha destacada nesse painel** (não na página normal) → **"Copy" → "Copy outerHTML"**.
6. Cole o conteúdo copiado num arquivo de texto (Bloco de Notas, Word, Google Docs) ou envie diretamente na conversa.

> 💡 Alternativa mais simples: com o painel do "Inspecionar" aberto, tire um print da tela inteira (incluindo o painel de código do lado). Também funciona, embora copiar o texto seja mais preciso.

**Elementos específicos a inspecionar:**

**☐ 2.6.1** Campo de CPF/CNPJ do login → Inspecionar → copiar
**☐ 2.6.2** Campo de senha → Inspecionar → copiar
**☐ 2.6.3** Botão "Entrar"/"Login" → Inspecionar → copiar
**☐ 2.6.4** Caixa/lista de seleção de CNPJ (matriz/filiais) → Inspecionar → copiar. Se for uma lista suspensa, abra-a primeiro e clique com botão direito numa das opções já visíveis.
**☐ 2.6.5** Cada campo de filtro da consulta (tipo de multa, data, etc.) → Inspecionar → copiar
**☐ 2.6.6** Botão "Consultar"/"Pesquisar" → Inspecionar → copiar
**☐ 2.6.7** Uma linha real da tabela de resultados (não o cabeçalho) → Inspecionar → copiar
**☐ 2.6.8** Botão/número de "próxima página" (paginação) → Inspecionar → copiar
**☐ 2.6.9** Link/ícone de download do PDF do auto → Inspecionar → copiar (um dos mais importantes)

**Forma alternativa mais completa (opcional, se for viável):**
1. Abra a página desejada.
2. Aperte **F12** para abrir o painel de desenvolvedor direto.
3. Vá até a aba **"Elements"** ("Elementos").
4. Clique com o botão direito na tag `<html>` no topo → **"Copy" → "Copy outerHTML"**.
5. Isso copia o código inteiro da página de uma vez — cole num arquivo de texto e envie.

**⚠️ Cuidados antes de enviar:**
- **Nunca** copie ou envie a senha real digitada nos campos.
- Dados de multas reais (placas, CNPJs, valores) podem ser mantidos, mas podem ser mascarados se preferir.
- O código HTML de estrutura (nomes de campos, botões) não é uma credencial e não dá acesso a nada sozinho.

---

## 🔴 Bloco 3 — Exemplo Real do Documento (PDF do Auto de Infração)

**☐ 3.1** Pelo menos 1 PDF real de um auto de infração (qualquer tipo)
- **Por quê:** preciso ver onde, dentro do PDF, aparecem os dados a extrair (placa, data, número de CIOT/MDF-e, enquadramento legal, etc.).
- **Cuidado:** se houver dados sensíveis, pode borrar/substituir por dados fictícios, mas mantendo o **layout** (posição das informações) intacto.

**☐ 3.2** Se possível, um PDF de cada tipo de multa recebida (frete mínimo, pedágio, excesso de peso, etc.)
- **Por quê:** o layout pode variar por tipo de infração, exigindo lógicas de leitura diferentes.

---

## 🟡 Bloco 4 — Base de Dados Interna da Empresa

**☐ 4.1** Onde ficam os dados das viagens/fretes hoje (planilha Excel, ERP, banco de dados?)
- **Como conseguir:** pergunte para TI/operações: "onde estão registrados os dados de cada viagem, com CIOT/MDF-e, placa e data?"

**☐ 4.2** Um exemplo (mesmo que fictício) de como esses dados estão organizados
- Ex.: print da planilha ou das colunas da tabela do sistema.

**☐ 4.3** Formato desejado do resultado final (planilha Excel nova, atualização de planilha existente, inserção em banco de dados)

---

## 🟢 Bloco 5 — Volume da Operação

**☐ 5.1** Quantos CNPJs a empresa tem (matriz + filiais)

**☐ 5.2** Volume médio de multas recebidas por mês

---

## 🟡 Bloco 6 — Máquina Local e SharePoint

**☐ 6.1** Confirmar qual computador será usado para rodar o robô
- **Por quê:** como o login é manual, precisa ser um computador ao qual a pessoa responsável tenha acesso físico direto e regular.
- **Como conseguir:** pergunte ao TI: "podemos usar o computador de [nome da pessoa] para rodar um programa localmente, sob demanda?"

**☐ 6.2** Confirmar se o OneDrive pode ser instalado/configurado nesse computador com acesso à biblioteca do SharePoint de destino
- **Como conseguir:** pergunte ao TI: "é possível instalar e configurar o OneDrive nesse computador com uma conta que tenha acesso à pasta do SharePoint onde os resultados serão salvos?"

**☐ 6.3** Confirmar se essa conta tem permissão de **escrita** (não só leitura) na pasta específica do SharePoint
- **Por quê:** sem permissão de escrita, o robô consegue gerar o arquivo localmente, mas ele nunca aparece para o resto da equipe no SharePoint.

**☐ 6.4** Perguntar se existe alguma exigência de aprovação de segurança da informação (InfoSec) antes de rodar uma automação com credencial real de login
- **Por quê:** melhor descobrir isso com antecedência do que no fim do projeto.

**☐ 6.5** Perguntar quem no TI ficará como ponto de contato caso o computador precise de suporte, reinstalação ou apresente algum problema técnico depois da entrega
- **Por quê:** evita que o robô fique "órfão" (sem ninguém responsável) depois de pronto — foi exatamente isso que aconteceu no projeto original quando o desenvolvedor saiu da empresa.

---

## Resumo de Prioridades

| Prioridade | Bloco | Pode começar sem isso? |
|---|---|---|
| 🔴 Bloqueante | 1.3 — teste de captura de sessão | Não — valida se a arquitetura toda (login manual + robô assume a sessão) é tecnicamente possível |
| 🔴 Bloqueante | Bloco 2 — prints + Inspecionar | Não — sem ver a estrutura da tela não dá para escrever a navegação |
| 🔴 Bloqueante | Bloco 3 — PDF de exemplo | Não — sem isso não dá para escrever a extração de dados |
| 🟡 Importante | Bloco 4 — base interna | Pode começar sem, mas o cruzamento de dados fica pendente |
| 🟡 Importante | Bloco 6 — máquina local + SharePoint | Pode escrever o código sem, mas a entrega final (gravação dos resultados) depende disso estar resolvido |
| 🟢 Pode esperar | Bloco 5 — volume | Ajuda a dimensionar, mas não trava o início do desenvolvimento |

**Sugestão de próximo passo:** comece pelo item 1.3 (teste de captura de sessão) e pelo Bloco 2 — são as informações mais urgentes e que já permitem começar a montar o esqueleto do robô.
