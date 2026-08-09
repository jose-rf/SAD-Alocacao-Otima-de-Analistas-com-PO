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
| 3 | Horas x horas contratadas | `Σ_i x[i,j] ≤ Hj·y[j]` |
| 4 | Vinculo `x` ↔ `z` (big-M) | `x[i,j] ≤ M·z[i,j]` |
| 5 | Horas minimas por alocacao | `x[i,j] ≥ h_min·z[i,j]` |
| 6 | Numero maximo de analistas | `Σ_i z[i,j] ≤ Njmax` |
| 7 | Projeto aceito tem ao menos um analista | `Σ_i z[i,j] ≥ y[j]` |
| 8 | Senioridade minima | `Si ≥ Sjmin·z[i,j]` |
| 8′ | Competencias comportamentais (Big Five) | `COMi/COLi/ORGi/ADAi/ESTi ≥ mínimo·z[i,j]` |
| 9 | Habilidades tecnicas | `SKILLik ≥ REQjk·z[i,j]` |
| 10 | Ausencia programada | `z[i,j] ≤ 1 − Ai` |
| 11 | Nao negatividade | `x[i,j] ≥ 0` |

A unica generalizacao em relacao ao artigo e a Equacao 7, parametrizada por
um numero minimo de analistas por projeto (`min_analistas`, campo presente
no prototipo de interface); com `min_analistas = 1` (padrao) a restricao e
identica a do artigo. O parametro big-M e calculado automaticamente como o
maior valor entre as horas contratadas dos projetos e a disponibilidade dos
analistas.

As competencias comportamentais sao baseadas no modelo conceitual **Big
Five** (Goldberg, 1990): Comunicacao (Extroversao), Colaboracao
(Amabilidade), Organizacao (Conscienciosidade), Adaptabilidade (Abertura a
Experiencia) e Estabilidade Emocional (Neuroticismo invertido), preenchidas
pelo gestor em escala de 0 a 100.

---

## Estrutura do codigo

```
optimization.py   # modelo MILP (Equacoes 1-11) — dataclasses Analista/Projeto,
                   # construcao e resolucao via PuLP/CBC, diagnostico de recusa
app.py             # interface Streamlit (cadastro, execucao e resultados)
requirements.txt   # dependencias
```

## Interface (Streamlit)

A interface segue o fluxo prototipado em alta fidelidade no Figma (secao
6.2.4.1 do pre-projeto):

1. **Analistas** — cadastro dinamico: nome, senioridade, custo/hora,
   disponibilidade, ausencia programada, competencias tecnicas (tabela
   editavel) e perfil comportamental Big Five (sliders).
2. **Projetos** — cadastro dinamico: nome, receita esperada, horas
   contratadas, numero minimo/maximo de analistas, nivel tecnico minimo,
   competencias tecnicas exigidas e perfil comportamental minimo exigido.
3. **Parametros e execucao** — configuracao de `h_min` e execucao do
   solver (PuLP/CBC).
4. **Resultado** — lucro liquido, receita total, custo total, projetos
   aceitos/total, distribuicao de horas por analista, alocacao detalhada e
   justificativa de aceitacao/recusa de cada projeto (`y[j]`).
5. **Exportacao** — download do relatorio completo em `.txt`.

Dados de exemplo (ficticios, ver secao 6.1.3 do pre-projeto) sao carregados
automaticamente ao abrir o sistema.

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
- [pandas](https://pandas.pydata.org/) — tabelas editaveis de competencias e resultados

---

## Contexto academico

Pesquisa de natureza aplicada e abordagem quantitativa (Gil, 2008), que
utiliza dados ficticios calibrados pelos autores como insumo de teste do
modelo (nao se trata de um estudo de caso). O prototipo nao possui banco de
dados nem integracoes corporativas — o foco e a validacao do modelo
matematico de alocacao proposto.

## Licenca

MIT
