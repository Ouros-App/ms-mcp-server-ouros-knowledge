# Ouros — Guia de Conhecimento para IA

> Documento condensado a partir do **Termo de Abertura do Projeto (TAP)** e do documento **Pendências TAP**.
>
> Objetivo: servir como **fonte de contexto para agentes de IA, RAG, desenvolvimento, documentação e validação funcional** do projeto Ouros.
>
> **Regra de precedência:** quando houver conflito, o documento **Pendências TAP** representa decisões mais recentes e deve prevalecer sobre o TAP original. Contradições ou fórmulas ainda não fechadas estão marcadas como `TODO / NÃO DEFINIDO`.

---

## 1. Visão geral

**Ouros** é um aplicativo B2B voltado à gestão e análise de dados ambientais de produtores rurais integrados à Seara/JBS, com foco principal em granjas de **frango de corte**.

A solução busca:

- registrar consumo de **água** e **energia** por lote;
- normalizar o consumo por ave para permitir comparações mais justas;
- gerar um índice de eficiência e um ranking entre produtores;
- permitir que a empresa acompanhe desperdícios, alertas e desempenho;
- incentivar redução progressiva do uso de recursos;
- funcionar em cenários de conectividade limitada.

O problema central é a dificuldade de acompanhar, de forma individualizada, o consumo de recursos nas propriedades integradas. Sem dados primários detalhados, a empresa tende a depender de médias e estimativas.

---

## 2. Público e atores

### 2.1 Produtor integrado

Produtor rural parceiro da Seara responsável por uma granja de frangos de corte.

Pode:

- registrar dados de consumo;
- consultar os próprios indicadores;
- consultar sua posição no ranking;
- visualizar seu próprio CGI e o CGI de até **2 produtores imediatamente acima**;
- criar metas individuais;
- usar o simulador financeiro;
- receber alertas e recomendações;
- conversar com o Midas dentro do escopo permitido;
- gerar relatório baseado em seu dashboard.

Não pode:

- editar ou excluir registros já controlados pela empresa;
- acessar dados completos de outros produtores;
- acessar o painel administrativo da empresa.

### 2.2 Empresa integradora

Perfil administrativo da empresa, pensado principalmente para Seara/JBS.

Pode:

- visualizar dados de todos os produtores;
- filtrar dados por estado, produtor e período;
- acompanhar alertas;
- responder solicitações de ajuda;
- editar ou excluir registros;
- criar metas estaduais/regionais;
- consultar dados de integrados por meio do Midas;
- gerar relatórios com base nos dashboards.

---

## 3. Persona principal

Persona de referência do projeto:

- **Nome:** João Silva
- **Idade:** 45 anos
- **Ocupação:** produtor rural integrado
- **Localização:** zona rural
- **Perfil:** prático, focado em resultado, simples e resistente a mudanças complexas
- **Necessidades:** reduzir custos, organizar dados, acompanhar resultados sem aumentar muito a carga de trabalho
- **Preferência de UX:** poucos dados para inserir, interface simples, leitura rápida e baixa complexidade

Implicação para produto: a solução deve priorizar **clareza, simplicidade operacional e baixo atrito**.

---

## 4. Dados principais

Os dados ambientais fundamentais do sistema são:

- leitura inicial do hidrômetro;
- leitura final do hidrômetro;
- consumo total de água;
- consumo total de energia;
- preço regional do m³ de água;
- preço regional do kWh;
- quantidade de aves entregues no lote;
- identificação do produtor, granja, estado/região e lote;
- dados históricos de lotes anteriores.

O projeto assume que o uso de hidrômetro é obrigatório/padronizado nas granjas integradas consideradas pelo sistema.

A coleta é **manual**. Não há integração obrigatória com sensores ou hidrômetros inteligentes.

---

## 5. Métricas de consumo

### 5.1 Consumo de água por ave

```text
CAA = litros consumidos / número de aves entregues
```

Quanto menor o CAA, menor o consumo hídrico por ave.

### 5.2 Consumo de energia por ave

```text
CEA = kWh consumidos / número de aves entregues
```

Quanto menor o CEA, menor o consumo energético por ave.

### 5.3 Peso dos indicadores

A água tem prioridade maior na composição da eficiência:

```text
Água:    70%
Energia: 30%
```

### 5.4 Consumo Geral do Integrado — CGI

A definição fornecida é:

```text
CGI = (Nota Água × 0,7) + (Nota Energia × 0,3)
```

Quanto maior o CGI, melhor deve ser a eficiência do integrado.

### TODO / NÃO DEFINIDO — normalização das notas

Os documentos não definem matematicamente como `CAA` e `CEA`, que são consumos onde **menor é melhor**, são convertidos em `Nota Água` e `Nota Energia`, nas quais **maior deve ser melhor**.

Portanto, **não inventar uma fórmula de normalização** sem decisão explícita do projeto.

---

## 6. Ranking

### 6.1 Princípios

- O ranking é baseado em eficiência relativa.
- A comparação utiliza consumo **por ave**, não apenas consumo bruto.
- O ranking é separado por **estado e/ou região** para reduzir distorções.
- O ranking **não reinicia**.
- A posição é atualizada quando um novo lote é entregue e seus dados são sincronizados.

### 6.2 Ligas

Distribuição definida por percentis da população elegível:

| Liga | Faixa |
|---|---:|
| Ouro | [0, 10) (melhor eficiência / menor consumo) |
| Prata | [10, 30) |
| Bronze | [30, 60) |
| Cobre | [60, 90) |
| Ferro | [90, 100] (pior eficiência / maior desperdício) |

> O TAP original citava apenas Ferro, Bronze, Prata e Ouro. A versão mais recente adiciona **Cobre**. Usar cinco ligas.

### 6.3 Visibilidade do ranking

O produtor:

- vê sua própria posição;
- vê seu próprio CGI;
- vê o CGI de até **2 produtores acima dele**.

A empresa possui visão administrativa mais ampla.

### 6.4 Evolução histórica

O histórico do produtor pode ser exibido para acompanhamento, mas **a evolução não recebe uma nota separada no ranking**.

---

## 7. Funcionamento offline e sincronização

O aplicativo possui suporte parcial a uso offline.

### Offline

Pode:

- manter dados salvos localmente no dispositivo;
- continuar armazenando registros enquanto não houver internet.

Não pode:

- autenticar/fazer login sem internet;
- atualizar o ranking sem sincronização.

### Sincronização

Quando a conexão volta:

1. dados locais pendentes são enviados;
2. registros são processados;
3. indicadores são atualizados;
4. o ranking é recalculado/atualizado.

Os dados podem permanecer localmente por no máximo 90 dias, com criptografia em repouso e controle de acesso; após esse prazo, devem ser eliminados, salvo retenção diferente aprovada formalmente.

---

## 8. Segurança e permissões

Existem dois perfis principais:

1. **Proprietário/produtor da granja**
2. **Empresa integradora**

Regras:

- produtor acessa seus próprios dados;
- empresa acessa os dados de todos os produtores;
- produtor possui visibilidade muito limitada sobre concorrentes no ranking;
- apenas a empresa pode editar ou excluir registros.

Dados de consumo são considerados sensíveis porque podem revelar detalhes operacionais e financeiros da granja.

A solução deve evitar exposição indevida desses dados.

---

## 9. Validação de dados

A entrada é manual.

O projeto assume que a empresa integradora consegue confrontar os dados enviados com a realidade da operação e, portanto, possui capacidade de validar inconsistências.

Ainda assim, qualidade de dados é um risco relevante, incluindo:

- valores incorretos;
- estimativas;
- fotos ou registros ilegíveis, caso usados;
- divergências entre consumo informado e operação real.

---

## 10. Alertas

O sistema pode disparar alertas quando houver comportamento anormal entre lotes ou indicadores críticos.

Situações mencionadas:

- aumento significativo de consumo;
- redução anormal de consumo de um lote para outro;
- consumo fora do padrão histórico;
- mortalidade muito alta;
- pedido de ajuda pelo produtor.

Alguns desses eventos também podem notificar o suporte da Seara.

### TODO / NÃO DEFINIDO — thresholds

Os documentos não fornecem limites matemáticos exatos para determinar:

- o que é "alto consumo";
- o que é "redução muito grande";
- o que é "mortalidade muito alta".

Não criar thresholds arbitrários sem definição de produto.

---

## 11. Mortalidade

Mortalidade **não entra no CGI nem no ranking**.

Ela funciona como indicador operacional e gatilho de suporte.

Se a mortalidade estiver muito alta:

- o produtor pode ser alertado;
- o suporte/assistência da Seara deve ser notificado.

---

## 12. Metas

Existem dois tipos:

### Metas individuais

Criadas pelo próprio produtor.

### Metas estaduais/regionais

Criadas pela empresa.

Cada meta possui prazo/data final.

Status possíveis:

- pendente;
- em andamento;
- concluída.

O sistema **não calcula percentual de progresso**. O status é informado pelo usuário.

---

## 13. Simulador financeiro

O simulador permite comparar o cenário atual com um cenário-alvo.

Entradas relevantes:

- consumo atual de água;
- consumo atual de energia;
- quantidade de aves;
- preço do m³ de água;
- preço do kWh;
- consumo-alvo de água;
- consumo-alvo de energia.

Saídas esperadas:

- economia estimada de água;
- economia estimada de energia;
- economia financeira estimada;
- comparação entre cenário atual e cenário desejado.

Os valores usados na simulação:

- servem apenas para planejamento;
- **não entram no ranking**;
- não alteram os registros reais.

---

## 14. Gestão financeira

O sistema pode calcular:

- gasto total com água;
- gasto total com energia;
- gasto por ave;
- economia estimada entre cenários ou períodos.

A análise deve considerar variação na quantidade de aves, evitando interpretar crescimento do gasto bruto como piora automática de eficiência.

---

## 15. Midas — chatbot/RAG

**Midas** é a IA interna do Ouros.

### Para o produtor

Pode:

- responder dúvidas sobre uso do aplicativo;
- explicar funcionalidades;
- ajudar com dúvidas relacionadas à melhoria operacional dentro do escopo do projeto;
- recomendar vídeos ou materiais disponibilizados pela empresa;
- direcionar conteúdos relacionados ao problema detectado.

### Para a empresa

Pode:

- localizar rapidamente informações sobre produtores/integrados;
- responder perguntas baseadas nos dados e documentos disponíveis;
- consultar informações relacionadas ao ranking.

### Arquitetura conceitual

Midas deve operar como uma IA do tipo **RAG (Retrieval-Augmented Generation)**.

### Restrições

Midas:

- deve permanecer dentro do domínio do Ouros;
- não deve responder perguntas desconectadas do projeto;
- não deve gerar imagens;
- não deve inventar dados ausentes;
- deve priorizar dados cadastrados e documentos oficiais da base de conhecimento.

---

## 16. Recomendações automáticas

Continuam previstas.

Podem ser acionadas por:

- gastos excessivos;
- alertas;
- pedidos de ajuda;
- interação com Midas.

As recomendações devem usar principalmente IA para selecionar ou apresentar materiais disponibilizados pela empresa integradora.

---

## 17. Painel da empresa

O painel administrativo deve permitir:

- visão geral dos integrados;
- filtros por estado;
- filtros por produtor;
- filtros por período;
- identificação de alto consumo de água;
- identificação de alto consumo de energia;
- identificação de alta mortalidade;
- visualização de solicitações de ajuda;
- resposta a alertas e solicitações.

---

## 18. Dashboards

Devem transformar dados operacionais em indicadores simples e legíveis.

Possíveis informações:

- consumo de água;
- consumo de energia;
- consumo por ave;
- CGI;
- posição no ranking;
- liga atual;
- histórico de lotes;
- custos;
- alertas;
- metas.

A interface deve favorecer leitura rápida e "números grandes", evitando excesso de complexidade.

---

## 19. Relatórios PDF

Existem relatórios para:

- produtor;
- empresa.

Os relatórios são gerados com base nos dados que aparecem nos dashboards atualizados.

Podem conter:

- indicadores;
- gráficos;
- ranking;
- dados de consumo;
- histórico;
- custos e eficiência.

Não existe período fixo obrigatório para geração. O relatório reflete o estado do dashboard no momento da geração ou os filtros aplicados.

---

## 20. Clima

A função de clima permanece como elemento **informativo**.

- localização deriva da região cadastrada da granja;
- pode exibir temperatura e condições climáticas;
- GPS também é tratado como informativo;
- a API meteorológica ainda não foi definida.

### TODO

Escolher API de clima.

---

## 21. Funcionalidades removidas do app final

As seguintes ideias aparecem no TAP original, mas foram explicitamente removidas posteriormente:

- previsibilidade/predição de resultados futuros;
- selos e reconhecimento digital;
- calendário;
- controle de vacinação;
- linha do tempo de lotes ligada ao calendário;
- biblioteca/aba Explorar.

Não implementar essas funcionalidades como requisitos atuais, salvo nova decisão explícita.

---

## 22. Funcionalidades atuais consolidadas

### Core

- cadastro/login online;
- perfis de produtor e empresa;
- registro manual de consumo;
- hidrômetro inicial/final;
- energia;
- aves por lote;
- cálculo por ave;
- CGI;
- ranking por estado/região;
- ligas;
- sincronização offline;
- dashboards;
- histórico;
- alertas;
- mortalidade como indicador auxiliar;
- metas;
- simulador financeiro;
- gestão financeira;
- relatórios PDF;
- clima informativo;
- Midas;
- recomendações automáticas;
- painel administrativo da empresa.

---

## 23. Modelo comercial

O Ouros é vendido por **licença para empresas**.

Modelo descrito no TAP:

```text
Taxa fixa mensal: R$ 3.500
Valor por granja: R$ 5
```

Planos originalmente mencionados:

- trimestral;
- semestral com 5% de desconto;
- anual com 10% de desconto.

Decisão posterior:

- o app inteiro está incluído na licença;
- não há limite de usuários;
- não há limite de granjas;
- não há implementação ou treinamento incluídos;
- não existem níveis diferenciados de suporte.

### Atenção — inconsistência comercial

O documento mais recente afirma simultaneamente que:

- existe plano trimestral;
- "não é possível cancelar";
- "ele renova todo ano".

Essa regra comercial está ambígua e precisa ser esclarecida antes de virar lógica de sistema, contrato ou tela de cobrança.

---

## 24. Custos de referência do projeto

Tabela trimestral presente no TAP:

| Item | Tipo | Valor |
|---|---|---:|
| Água | Fixo | R$ 120,00 |
| Internet | Fixo | R$ 396,00 |
| Luz | Variável | R$ 196,91 |
| Salário | Variável | R$ 2.791,25 |
| ME LTDA | Variável | R$ 1.260,00 |
| Contabilidade | Fixo | R$ 585,00 |
| **Total fixo** |  | **R$ 1.101,00** |
| **Total variável** |  | **R$ 4.248,16** |
| **Total geral trimestral** |  | **R$ 5.349,16** |

Esses valores são referência de planejamento do TAP, não necessariamente parâmetros do produto.

---

## 25. Identidade visual

Nome: **Ouros**

Conceito visual associado a:

- reconhecimento;
- conquista;
- eficiência;
- sustentabilidade.

Paleta apresentada no TAP:

- azul escuro/fundação;
- dourado/conquista e reconhecimento;
- off-white/clareza;
- azul profundo/elegância e sofisticação.

A marca usa uma identidade escura com detalhes dourados e símbolo semelhante a uma pena/folha.

---

## 26. Benchmark

O TAP compara o Ouros com soluções como:

- Integra;
- Custo Fácil;
- Granvo.

Critérios comparados incluem:

- metodologia de ranking entre granjas;
- foco em sustentabilidade;
- assistência/suporte ao produtor;
- incentivo por notificações;
- gestão geral da granja.

A proposta do Ouros não é ser um ERP completo de gestão de granja. O foco principal é **eficiência de recursos + acompanhamento + ranking + suporte orientado por dados**.

---

## 27. Riscos e limitações

### 27.1 Infraestrutura física

Software sozinho não resolve falta de:

- hidrômetros;
- sistemas de reuso;
- equipamentos eficientes;
- infraestrutura de economia de água/energia.

O sistema pode diagnosticar desperdício sem conseguir eliminá-lo fisicamente.

### 27.2 Conectividade

Produtores com sinal ruim podem:

- sincronizar com atraso;
- receber atualização de ranking depois;
- ter experiência inferior.

### 27.3 Alfabetização digital

Parte dos produtores pode ter dificuldade com:

- apps;
- entrada manual de dados;
- autenticação;
- processos digitais frequentes.

### 27.4 Comparação injusta

Clima, região, renda, escala e estrutura da propriedade podem influenciar o consumo.

Mitigações previstas:

- consumo por ave;
- ranking segmentado geograficamente.

### 27.5 Segurança

Vazamento de dados pode expor:

- consumo;
- custos;
- eficiência;
- informações operacionais.

### 27.6 Resistência à adoção

O ranking pode ser percebido como:

- controle;
- fiscalização;
- ferramenta punitiva.

Isso pode reduzir engajamento real.

### 27.7 Custos de melhoria

Mesmo quando o sistema identifica oportunidades, nem todo produtor consegue financiar mudanças físicas.

### 27.8 Suporte

A expansão pode exigir estrutura organizacional suficiente para acompanhar alertas e produtores.

---

## 28. Premissas de UX e produto

Ao projetar qualquer fluxo:

1. minimizar digitação;
2. evitar telas excessivamente densas;
3. priorizar indicadores claros;
4. explicar números em linguagem simples;
5. manter ações principais visíveis;
6. considerar internet instável;
7. não exigir conhecimento técnico do produtor;
8. separar claramente visão do produtor e visão da empresa;
9. evitar expor dados competitivos além do necessário;
10. nunca permitir que gamificação comprometa justiça ou privacidade.

---

## 29. Regras para uma IA trabalhando no projeto

Uma IA que use este documento como contexto deve:

### Deve

- tratar este arquivo como visão consolidada do domínio;
- usar consumo por ave nas comparações;
- respeitar peso de 70% água e 30% energia;
- considerar cinco ligas: Ouro, Prata, Bronze, Cobre e Ferro;
- preservar separação entre produtor e empresa;
- lembrar que o app possui operação offline parcial;
- manter mortalidade fora do ranking;
- manter simulações fora do ranking;
- restringir o Midas ao domínio Ouros;
- sinalizar pontos não definidos em vez de inventar regras.

### Não deve

- reintroduzir funcionalidades removidas;
- inventar thresholds;
- inventar normalização de notas;
- tratar consumo bruto como métrica principal de eficiência;
- assumir que produtor pode editar/excluir registros;
- assumir login offline;
- assumir coleta automática por IoT;
- assumir que clima afeta automaticamente o ranking;
- expor dados completos de outros produtores;
- considerar mortalidade como parte do CGI.

---

## 30. Pontos em aberto

Antes de considerar a especificação totalmente fechada, ainda é necessário definir:

1. fórmula de transformação de CAA/CEA em `Nota Água` e `Nota Energia`;
2. regra exata de desempate do ranking;
3. comportamento quando existem poucos produtores em uma região;
4. thresholds dos alertas;
5. threshold de mortalidade;
6. política de validação/auditoria de registros;
7. API meteorológica;
8. detalhes de autenticação e recuperação de conta;
9. estratégia de sincronização e resolução de conflitos offline;
10. política de retenção e proteção de dados;
11. regra comercial final de renovação/cancelamento;
12. definição exata de "estado" vs "região" para segmentação do ranking.

---

## 31. Resumo operacional em uma frase

**Ouros é uma plataforma B2B para produtores integrados de frango de corte registrarem água e energia por lote, transformando esses dados em métricas por ave, ranking regional, dashboards, alertas, metas e suporte assistido por IA, enquanto a empresa obtém visão consolidada para acompanhar eficiência e desperdício.**
