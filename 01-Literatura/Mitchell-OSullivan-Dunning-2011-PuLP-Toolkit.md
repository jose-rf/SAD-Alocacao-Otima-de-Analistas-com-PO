---
tipo: artigo
status: lido
tags: [literatura, pulp, python, milp]
---

# PuLP: A Linear Programming Toolkit for Python

**Autor(es):** Mitchell, Stuart; O'Sullivan, Michael; Dunning, Iain
**Ano:** 2011
**Fonte:** Auckland: University of Auckland, Department of Engineering Science
**Link:** http://www.optimization-online.org/DB_FILE/2011/09/3178.pdf
**Arquivo local:** `Artigos e projetos/Artigos TCC/PuLP A Linear Programming Toolkit for.pdf`
**Capítulo(s) do TCC relacionado(s):** 6.3.2 Solver CBC e PuLP

## Resumo (em palavras próprias)
Artigo dos próprios criadores da biblioteca PuLP, explicando as decisões de design por trás dela. Pontos centrais:

- **Objetivo do PuLP:** permitir descrever modelos de programação linear/inteira mista (MILP) usando a sintaxe natural do Python, sem palavras-chave especiais — ao contrário de linguagens de modelagem dedicadas (AMPL) ou de outras bibliotecas Python como o Pyomo.
- **Licença e portabilidade:** PuLP é gratuito, licenciado sob MIT (permissiva), escrito em Python puro, sem dependências externas — o que facilita seu uso tanto em protótipos acadêmicos quanto embutido em sistemas maiores (relevante para justificar seu uso em um módulo de SAD).
- **Interface com solvers:** PuLP converte as expressões Python em uma representação numérica (matriz esparsa) e a repassa a uma classe de interface de solver. Suporta tanto solvers comerciais (CPLEX, Gurobi) quanto abertos (CBC, que é o solver padrão).
- **Estilo "Pythonic":** o modelo é construído literalmente "somando" expressões ao objeto `LpProblem` (`prob += expressao`), usando list comprehensions e laços `for` que mapeiam quase 1:1 para a notação matemática (ex.: `for i in I: for j in J: prob += x[i,j] <= M * z[i,j]` mapeia diretamente `x_ij ≤ M·z_ij, ∀i,j`).
- **Modelos concretos, não abstratos:** diferente do Pyomo, o PuLP não separa modelo abstrato de dados — os dados já entram concretos na definição do modelo, o que os autores defendem ser mais simples e suficiente para a maioria dos casos práticos (inclusive quando embutido em uma aplicação maior, como um SAD).
- **Dois exemplos completos no artigo:** Capacitated Facility Location (aceitação/alocação com variável binária de uso de localidade — estruturalmente parecido com aceitar/recusar projeto no modelo do TCC) e Wedding Planner (problema de particionamento, com função de custo em Python puro dentro do objetivo).
- **Comparação com Pyomo:** PuLP tem sintaxe mais direta e legível para restrições indexadas; Pyomo suporta modelos abstratos e mais integrações, mas com sintaxe mais verbosa.

## Por que usar no TCC
Referência primária para justificar a escolha do PuLP na seção 6.3.2 (já parcialmente citada no pré-projeto). O padrão de código do artigo (`prob += lpSum(...)`, `LpVariable.dicts`, laços `for` mapeando conjuntos I/J/K) é diretamente comparável à implementação em [`alocacao_analistas (1).py`](../alocacao_analistas%20(1).py).

## Citação sugerida (ABNT)
MITCHELL, S.; O'SULLIVAN, M.; DUNNING, I. **PuLP: A Linear Programming Toolkit for Python**. Auckland: University of Auckland, Department of Engineering Science, 2011.

## Ideias para o TCC
- Usar o exemplo do Capacitated Facility Location como analogia pedagógica ao explicar a formulação MILP na seção 7.1.3 (ambos usam variável binária para "usar/aceitar" uma opção, ligada a uma restrição de capacidade).
- Citar a característica "modelos concretos" do PuLP para justificar por que os dados fictícios (analistas, projetos) são definidos diretamente no código/Streamlit, sem camada de abstração adicional.
