# Guia de Uso — Robô ANTT

Este guia explica como usar o robô no dia a dia. Não é preciso saber
programação nem nada de informática além de usar o computador
normalmente.

## O que este programa faz

Ele busca automaticamente, no portal da ANTT, todas as multas (autos de
infração) da empresa, baixa os documentos e organiza tudo numa planilha
Excel — sem precisar entrar auto por auto manualmente.

## Antes de começar

- Você vai precisar fazer o login manual no portal da ANTT (CPF, senha e
  a verificação de segurança) — essa parte o programa não consegue fazer
  sozinho, por segurança do próprio portal.
- O programa trabalha com "workers" — cada worker é como uma cópia do
  robô trabalhando ao mesmo tempo, e cada um precisa de um login seu,
  um de cada vez. Quanto mais workers, mais rápido termina, mas mais
  logins você precisa fazer no começo.
- Recomendado: **5 workers**.

## Passo a passo

### 1. Abrir o programa

Dê 2 cliques no atalho **"Rodar_Robo_ANTT"**. Uma janela chamada
"Robô ANTT" vai abrir.

### 2. Escolher quantos workers usar

Digite um número (recomendado: **5**) e clique em **"Iniciar"**.

### 3. Fazer os logins

Para cada worker, uma janela do navegador abre sozinha na tela de login
da ANTT.

1. Faça o login normalmente: CPF, senha, e a verificação de segurança
   (captcha), se aparecer.
2. Quando a página principal do portal aparecer, **volte para a janela
   do Robô ANTT** e clique em **"Já fiz login - continuar"**.
3. Repita para cada worker — a janela do robô avisa quando é a vez do
   próximo login.

Depois do último login, você não precisa fazer mais nada — os workers já
começam a trabalhar sozinhos, em segundo plano.

### 4. Acompanhar o andamento

A tela mostra uma linha por worker, com uma barra de progresso e uma
frase em português explicando onde cada um está. Isso pode levar
**horas**, dependendo de quantas multas novas existirem desde a última
vez — pode deixar a janela aberta e fazer outra coisa, voltando de vez
em quando só para conferir.

### 5. Quando terminar

A tela mostra **"CONCLUÍDO"**, o caminho da planilha final, quantas multas
foram verificadas no total e quantas são novas nesta execução, e uma
frase dizendo se a varredura da empresa inteira já está 100% completa ou
se ainda falta alguma coisa.

A planilha final fica em:

```
OneDrive - Yara International ASA\Dados ANTT\Relatorio_Multas.xlsx
```

**Importante sobre "100% completo":** normalmente, quando a tela diz que
ainda falta alguma coisa, é só rodar o programa de novo que ele resolve
sozinho. Mas existe um grupo pequeno e já conhecido de documentos (por
volta de 170) que têm um problema permanente no servidor da própria
ANTT — não é um problema deste programa, e rodar de novo não vai
resolver esses específicos, por mais vezes que se tente. Quando a tela
disser algo como "não precisa rodar de novo por causa disso", é
exatamente esse caso — **não indica erro nenhum**, é esperado. A lista
completa desses documentos fica em `Falhas_Pendentes_Revisao_Manual.xlsx`
(ao lado da planilha final), já entregue pra revisão manual/contato com a
ANTT se algum dia for necessário.

## Se algo parar no meio (acontece, é normal)

De vez em quando um worker para antes de terminar. Os motivos mais
comuns:

- **A sessão expirou** — o login "vence" depois de um tempo, que varia
  bastante (às vezes minutos, às vezes muitas horas) e não dá pra prever.
- **O portal da ANTT caiu em manutenção** — fora do nosso controle,
  volta sozinho depois de um tempo.

Nos dois casos, o worker avisa isso claramente na tela e para sozinho,
**sem perder nenhum dado** do que já tinha sido feito até ali.

**O que fazer:** feche o programa e abra de novo (mesmo atalho). Ele
continua exatamente de onde parou — não repete trabalho já feito, não
duplica nada na planilha. Só é preciso fazer login de novo para os
workers que pararam.

## Perguntas frequentes

**Preciso entender de programação para usar isso?**
Não. Só é preciso saber fazer login no portal da ANTT, como já se faz
normalmente.

**Posso fechar a janela do navegador depois de logar?**
Sim, sem problema, assim que clicar em "Já fiz login" — o trabalho
continua sozinho em segundo plano.

**Posso desligar o computador no meio da varredura?**
Não é recomendado — melhor deixar rodando até terminar, ou fechar o
programa direito antes de desligar. Mas se precisar desligar mesmo
assim, é seguro: nada fica corrompido, o pior caso é ter que refazer um
pouco de trabalho na próxima vez.

**Quantos workers eu devo usar?**
5 é o recomendado (bom equilíbrio entre velocidade e quantidade de
logins). Pode usar menos se preferir fazer menos logins — só vai demorar
mais para terminar.

**A planilha já vem pronta para usar no Excel, sem precisar arrumar
nada?**
Sim — datas e valores já vêm no formato certo (dá para ordenar por data,
somar a coluna "Valor", filtrar por período, etc., sem precisar
converter nada manualmente).

**Como sei se a empresa inteira já está 100% coberta, não só esta
execução?**
A própria tela de conclusão já informa isso automaticamente, ao final
de cada execução.

## Em caso de dúvida técnica

Ponto de contato: André Miglietti.

---

*Guia referente à interface gráfica (IHM) validada em 23/09/2026, com
ajustes de texto/mensagens revisados pela última vez em 25/09/2026. Se a
aparência da tela mudar no futuro, os passos gerais devem continuar os
mesmos.*
