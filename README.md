# Alocacao Otima de Analistas — Modulo de SAD (TCC)

Modulo de Sistema de Apoio a Decisao (SAD) para alocacao de analistas em
projetos de assessoria em regime de horas, desenvolvido como Trabalho de
Conclusao de Curso (TCC) do curso de Sistemas de Informacao — UEMG, unidade
Passos.

> **Sistema para Alocacao de Analistas em Projetos de Assessoria em Regime de
> Horas: uma abordagem por Programacao Linear Inteira Mista (MILP) com foco
> na maximizacao do lucro liquido**
> Jose Rodrigues de Franca; Julia Alves de Brito — Orientador: Prof. Eduardo
> Henrique Marques Ferreira

O objetivo e recomendar, de forma matematicamente otima, quais analistas
devem ser alocados a quais projetos (e por quantas horas), de modo a
**maximizar o lucro liquido** da organizacao, respeitando disponibilidade,
senioridade, competencias tecnicas e comportamentais dos profissionais.

---

## Sobre o modelo (Programacao Linear Inteira Mista)

O problema e formulado exatamente como descrito na secao 6.2.2 do
pre-projeto de TCC, resolvido com o solver **CBC** via biblioteca **PuLP**.

**Conjuntos**

| Conjunto | Significado |
|---|---|
| `I` | analistas disponiveis |
| `J` | projetos candidatos a aceitacao |
| `K` | habilidades tecnicas consideradas |

**Variaveis de decisao**

| Variavel | Tipo | Papel |
|---|---|---|
| `x[i,j]` | continua, ≥ 0 | horas do analista `i` alocadas ao projeto `j` |
| `y[j]` | binaria | projeto `j` aceito (1) ou recusado (0) |
| `z[i,j]` | binaria | analista `i` vinculado (1) ou nao (0) ao projeto `j` |

**Funcao objetivo (Equacao 1)** — maximizar o lucro liquido:

```
Maximizar Z = Σ_j Rj·y[j]  −  Σ_i Σ_j Ci·x[i,j]
```

**Restricoes (Equacoes 2 a 11)**

| # | Restricao | Expressao |
|---|---|---|
| 2 | Disponibilidade do analista | `Σ_j x[i,j] ≤ Di` |
| 3 | Horas == horas contratadas (teto + piso) | `Σ_i x[i,j] ≤ Hj·y[j]`  **e**  `Σ_i x[i,j] ≥ Hj·y[j]` |
| 4 | Vinculo `x` ↔ `z` (big-M) | `x[i,j] ≤ M·z[i,j]` |
| 5 | Horas minimas por alocacao | `x[i,j] ≥ h_min·z[i,j]` |
| 6 | Numero maximo de analistas | `Σ_i z[i,j] ≤ Njmax` |
| 7 | Numero minimo de analistas (Njmin) | `Σ_i z[i,j] ≥ Njmin·y[j]` |
| 8 | Senioridade minima | `Si ≥ Sjmin·z[i,j]` |
| 8′ | Competencias comportamentais (Big Five) | `COMi/COLi/ORGi/ADAi/ESTi ≥ mínimo·z[i,j]` |
| 9 | Cobertura conjunta de habilidades tecnicas | para cada `k` com `REQjk > 0`: `Σ_(i ∈ I_jk) z[i,j] ≥ y[j]`, onde `I_jk = {i : SKILLik ≥ REQjk}` |
| 10 | Ausencia programada | `z[i,j] ≤ 1 − Ai` |
| 11 | Nao negatividade | `x[i,j] ≥ 0` |

O codigo implementa as Equacoes 1 a 11 da secao 6.2.2, com tres ajustes
explicitos e documentados em relacao ao texto original (ver secao seguinte):
piso de horas na Equacao 3, generalizacao da Equacao 7 por `Njmin` e
reformulacao da Equacao 9 para cobertura conjunta de habilidades pela
equipe (em vez de exigencia individual por analista).

As competencias comportamentais sao baseadas no modelo conceitual **Big
Five** (Goldberg, 1990): Comunicacao (Extroversao), Colaboracao
(Amabilidade), Organizacao (Conscienciosidade), Adaptabilidade (Abertura a
Experiencia) e Estabilidade Emocional (Neuroticismo invertido), preenchidas
pelo gestor em escala de 0 a 100.

### Fidelidade ao pre-projeto e ajustes explicitos

As 11 equacoes do artigo estao implementadas de base, mas o codigo tem tres
ajustes deliberados em relacao ao texto original — todos lineares, sem
variaveis novas, e documentados aqui, no README e nos comentarios de
`optimization.py`:

1. **Piso de horas contratadas (Equacao 3).** A restricao original so' evita
   que a equipe ultrapasse `Hj`; sozinha, ela permite que o modelo aceite um
   projeto (`yj=1`), reconheca a receita `Rj` inteira e aloque menos horas
   que `Hj`, superestimando o lucro. Foi adicionada uma restricao simetrica
   com `≥`, de modo que `yj=1` forca `Σ_i x[i,j] == Hj` e `yj=0` forca
   `Σ_i x[i,j] == 0`.
2. **Njmin — minimo de analistas por projeto (Equacao 7 generalizada).** O
   artigo fixa "ao menos um analista responsavel" (`Σ_i z[i,j] ≥ y[j]`). O
   codigo generaliza para um parametro `Njmin` configuravel por projeto
   (default = 1, com validacao `1 ≤ Njmin ≤ Njmax` no cadastro), reduzindo-se
   ao caso do artigo quando `Njmin = 1`.
3. **Cobertura conjunta de habilidades tecnicas (Equacao 9 reformulada).** O
   artigo exige que cada analista vinculado cubra sozinho todas as
   habilidades exigidas pelo projeto (`SKILLik ≥ REQjk` por analista). O
   codigo passa a exigir cobertura por equipe: para cada habilidade exigida,
   basta que ao menos um analista vinculado a atenda. E' um relaxamento
   estrito do espaco de solucoes viaveis anterior — toda solucao antes
   viavel continua viavel — portanto o lucro liquido otimo nunca piora, so'
   pode manter ou aumentar. Senioridade (Equacao 8) e competencias
   comportamentais (Equacao 8′) continuam exigidas individualmente de cada
   analista vinculado; a mudanca vale so' para habilidades tecnicas.

Alem desses tres ajustes, tres parametros sao descritos no pre-projeto de
forma qualitativa (sem formula fechada) e precisaram de uma decisao de
implementacao para o codigo ser executavel:

- **Big-M** (secao 6.2.1.5 define apenas como "um valor suficientemente
  grande") — calculado automaticamente como o maior valor entre `Hj` de
  todos os projetos e `Di` de todos os analistas.
- **Codificacao numerica de `Si`/`Sjmin`** — o artigo trata senioridade como
  categorias comparaveis (Junior/Pleno/Senior) sem formalizar a conversao
  numerica; o codigo usa Junior=1, Pleno=2, Senior=3 para viabilizar
  `Si ≥ Sjmin·z[i,j]`.
- **Requisitos com minimo igual a zero** (competencias comportamentais e
  tecnicas) — quando um projeto nao exige minimo para uma dimensao (valor
  0), a restricao correspondente e omitida por ser redundante
  (`valor ≥ 0·z[i,j]` seria sempre verdadeira). O espaco de solucoes nao se
  altera.

Nenhum desses pontos muda o resultado da otimizacao em relacao ao que as
equacoes do artigo produziriam.

Ha, alem disso, uma unica peca de codigo que **nao faz parte do modelo
MILP**: a funcao `_diagnosticar_recusa()` em `optimization.py`, que gera o
texto explicativo exibido ao lado de cada projeto recusado na tela de
Resultado (ex.: "nenhum analista atende a senioridade minima..."). Essa
logica e puramente descritiva — nao entra em nenhuma restricao do solver e
nao influencia `x[i,j]`, `y[j]` ou `z[i,j]` — e existe apenas como recurso
de UX do SAD para tornar a recusa de um projeto compreensivel ao gestor,
conforme o papel de "explicar a decisao ao usuario" atribuido a um SAD na
secao 7.4.1 do pre-projeto.

### Decisoes de implementacao ainda nao refletidas no texto do TCC

As funcionalidades abaixo foram implementadas no protototipo mas **ainda nao
foram atualizadas no texto do pre-projeto** (secoes 6.2.2.6, 6.2.3, 6.2.4.1,
6.2.4.2, 6.2.6 e os diagramas UML de 6.2.7) — a recomendacao registrada e'
sempre implementar no protototipo primeiro e so' entao atualizar o texto,
para nao repetir o problema encontrado em 06/09/2026 (o TCC ja' afirmava
existir uma validacao de faixa de `Di` que não existia de fato no codigo):

- **CPF como chave do analista** — campo novo (`analistas.cpf`), com
  validacao de formato (`000.000.000-00`) e indice `UNIQUE` parcial no
  banco (ignora valor vazio, pra' permitir a linha em branco que "+
  Adicionar analista" cria antes do preenchimento).
- **Teto de disponibilidade por calendario** — `Di` passa a ter um teto
  calculado como `dias_no_mes(periodo_referencia) × 24h`, com uma nota na
  interface sugerindo um teto mais realista de jornada CLT (~220h/mes)
  como alternativa. Isso e' o criterio real hoje — o texto do TCC precisa
  refletir essa formula quando for atualizado.
- **Persistencia de horas comprometidas entre execucoes** (candidata →
  confirmada) — ver secao dedicada acima. E' uma premissa nova do modelo
  de dados (nao uma equacao do MILP em si): a disponibilidade `Di` usada
  numa rodada de otimizacao passa a descontar as horas ja' comprometidas
  em execucoes confirmadas do mesmo periodo de referencia.
- **Selecao de subconjunto de analistas/projetos por rodada** — o modelo
  deixa de rodar obrigatoriamente sobre todo o cadastro; o gestor escolhe
  o escopo de cada execucao na pagina "Geracao da Alocacao".
- **Menu lateral com 5 paginas** — reorganiza a navegacao antes descrita
  como fluxo de rolagem continua (secao 6.2.4.1/6.2.4.2); as telas de
  habilidades tecnicas, que o texto do pre-projeto ainda trata como
  placeholder "[a ser desenvolvido]", ja' existem de fato desde a etapa
  anterior e agora ganham pagina propria no menu.

---

## Estrutura do codigo

```
optimization.py   # modelo MILP (Equacoes 1-11) — dataclasses Analista/Projeto,
                   # construcao e resolucao via PuLP/CBC, diagnostico de recusa
db.py              # persistencia SQLite (schema, CRUD, seed de dados de exemplo)
app.py             # interface Streamlit (cadastro, execucao e resultados)
requirements.txt   # dependencias
alocacao.db        # banco SQLite local (gerado em tempo de execucao, git-ignored)
```

## Persistencia (SQLite)

O SAD persiste os dados em um banco **SQLite** local (`alocacao.db`, criado
automaticamente na primeira execucao), com sete tabelas:

| Tabela | Papel |
|---|---|
| `analistas` | cadastro de analistas (CPF, Si, Ci, Di, Ai, Big Five) |
| `projetos` | cadastro de projetos (Rj, Hj, Sjmin, Njmax, Njmin, Big Five minimo) |
| `habilidades` | catalogo global de competencias tecnicas (nome unico, normalizado) |
| `analista_habilidade` | associativa (chave composta `id_analista`+`id_habilidade`) — SKILLik |
| `projeto_habilidade_requerida` | associativa (chave composta `id_projeto`+`id_habilidade`) — REQjk |
| `execucoes` | historico de execucoes do solver (parametros, resultado agregado, situacao candidata/confirmada, periodo de referencia, hash dos dados de entrada) |
| `alocacoes` | historico detalhado de cada alocacao `x[i,j]` por execucao |

Cada edicao de campo na interface grava direto no banco (sem botao "salvar"
separado); a tela sempre le o estado atual do SQLite no topo do script.

`CPF` e' a chave de identificacao do analista: campo com validacao de
formato (`000.000.000-00`) e indice `UNIQUE` parcial no banco (ignora
CPF vazio, para permitir a linha em branco criada por "+ Adicionar
analista" ate' o gestor preencher).

## Persistencia de horas comprometidas entre execucoes (candidata → confirmada)

Toda execucao do solver e' registrada com `situacao = candidata` e um
`periodo_referencia` (`AAAA-MM`). Uma previa pode ser gerada quantas vezes o
gestor quiser sem comprometer horas de ninguem. Só' quando o gestor clica em
**"Escolher esta alocacao"** (Dashboard de Resultados) a execucao passa a
`situacao = confirmada` — a partir dai', as horas dela contam.

A disponibilidade **efetiva** de cada analista usada pelo modelo passa a ser:

```
Di_efetivo = Di − Σ(horas em execucoes CONFIRMADAS do mesmo periodo_referencia)
```

calculada dinamicamente a cada execucao (consulta agregada sobre
`alocacoes` + `execucoes`), e nao como coluna redundante armazenada —
mesma logica de normalizacao da secao 7.4.5 do pre-projeto. As horas
comprometidas resetam a cada novo periodo de referencia (mes/ano).

## Interface (Streamlit)

A interface usa **menu lateral (sidebar) com 5 paginas**, mais um seletor
global de **periodo de referencia** (mes/ano) no topo da sidebar:

1. **Cadastro de Analistas** — cadastro dinamico com listagem: nome, CPF,
   senioridade, custo/hora, disponibilidade (teto calculado pelo calendario
   do periodo de referencia — `dias_no_mes × 24h` — com nota sugerindo um
   teto mais realista de jornada CLT em torno de 220h/mes), ausencia
   programada e perfil comportamental Big Five (sliders com nome completo:
   Comunicacao, Colaboracao, Organizacao, Adaptabilidade, Estabilidade
   Emocional; a sigla COM/COL/ORG/ADA/EST fica so' internamente).
2. **Cadastro de Projetos** — cadastro dinamico com listagem: nome, receita
   esperada, horas contratadas, numero maximo (Njmax) e minimo (Njmin) de
   analistas, nivel tecnico minimo e perfil comportamental minimo exigido.
3. **Cadastro de Habilidades Tecnicas** — catalogo global de habilidades
   (`habilidades`) em uma pagina so', com duas abas: proficiencia dos
   analistas (SKILLik, `analista_habilidade`) e exigencia dos projetos
   (REQjk, `projeto_habilidade_requerida`; REQjk = 0 equivale a "nao
   exigida" e nao gera restricao na Equacao 9).
4. **Geracao da Alocacao** — configuracao de `h_min`, **selecao de um
   subconjunto** de analistas e projetos para a rodada (por default, todo o
   cadastro), disponibilidade efetiva do periodo (ver secao acima),
   comparacao do hash dos dados de entrada com a ultima execucao (avisa se
   os dados mudaram) e botao **"Reprocessar / gerar previa da alocacao"**
   (cria uma execucao `candidata`).
5. **Dashboard de Resultados** — historico de execucoes (selecionavel por
   id/data/periodo/situacao), lucro liquido, receita total, custo total,
   alocacao detalhada, projetos aceitos/recusados (motivo de recusa
   disponivel so' para a execucao mais recente da sessao, nao persistido),
   botao **"Escolher esta alocacao"** (confirma a execucao selecionada) e
   exportacao do relatorio completo em `.txt`.

Dados de exemplo (ficticios, ver secao 6.1.3 do pre-projeto) sao carregados
automaticamente na primeira execucao, quando o banco ainda esta' vazio.

---

## Instalacao e execucao

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Tecnologias

- **Python 3.10+**
- [PuLP](https://coin-or.github.io/pulp/) — modelagem do problema MILP
- [CBC](https://github.com/coin-or/Cbc) — solver open-source (branch-and-cut), incluido no PuLP
- [Streamlit](https://streamlit.io/) — interface web interativa
- [pandas](https://pandas.pydata.org/) — tabelas de resultados
- **SQLite** (`sqlite3`, biblioteca padrao do Python) — persistencia de cadastros e historico de execucoes

---

## Contexto academico

Pesquisa de natureza aplicada e abordagem quantitativa (Gil, 2008), que
utiliza dados ficticios calibrados pelos autores como insumo de teste do
modelo (nao se trata de um estudo de caso). O prototipo usa um banco SQLite
local apenas para persistir cadastros e historico de execucoes entre
sessoes — nao ha integracoes corporativas; o foco e a validacao do modelo
matematico de alocacao proposto.

## Licenca

MIT
