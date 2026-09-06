---
tipo: artigo
status: lido
tags: [literatura, cbc, solver, branch-and-cut]
---

# CBC User Guide

**Autor(es):** Forrest, John; Lougee-Heimer, Robin
**Ano:** 2005 (publicado em INFORMS TutORials in Operations Research; versão consultada teve acesso registrado em 2014/2026)
**Fonte:** In: Emerging Theory, Methods, and Applications. Catonsville, MD: INFORMS, 2005, p. 257-277. DOI: https://doi.org/10.1287/educ.1053.0020
**Arquivo local:** `Artigos e projetos/Artigos TCC/forrest-lougee-heimer-2014-cbc-user-guide.pdf`
**Capítulo(s) do TCC relacionado(s):** 6.3.2 Solver CBC e PuLP

## Resumo (em palavras próprias)
Guia técnico (voltado a desenvolvedores C++) do solver CBC (COIN-OR Branch and Cut), mantido pelo projeto COIN-OR. Pontos relevantes para o TCC (o restante do artigo é essencialmente uma referência de API C++, pouco aplicável ao uso via PuLP/Python):

- **O que é o CBC:** solver de código aberto para Programação Inteira Mista (MIP), escrito em C++, projetado para ser usado como biblioteca (não apenas executável standalone). Licenciado sob a Common Public License.
- **Algoritmo:** implementa o método **branch-and-cut** (combinação de branch-and-bound com planos de corte/cutting planes). O artigo descreve o algoritmo passo a passo:
  1. Relaxar a exigência de integralidade (tratar variáveis inteiras como contínuas) e resolver a LP relaxada — isso dá um limite (bound) para o valor ótimo.
  2. Se a solução da LP relaxada já é inteira, terminou (ótimo encontrado).
  3. Caso contrário, escolher uma variável fracionária e "ramificar" (branch): criar dois subproblemas — um forçando a variável a um limite inferior arredondado para baixo, outro a um limite superior arredondado para cima.
  4. Repetir recursivamente em cada nó da árvore de busca, podando (pruning) nós inviáveis ou cujo limite já é pior que a melhor solução conhecida.
  5. Opcionalmente, adicionar "cortes" (cuts) — restrições extras válidas que apertam a relaxação LP sem excluir soluções inteiras — para acelerar a convergência (isso é o que diferencia branch-and-cut de um branch-and-bound simples).
- **Dependências:** CBC precisa de um solver de LP (comumente o CLP, também do COIN-OR) e pode usar geradores de cortes da CGL (Cut Generation Library).
- **Flexibilidade:** o CBC permite customizar a ordem de exploração dos nós da árvore, o critério de escolha de variável de ramificação, heurísticas para achar soluções viáveis rapidamente, geração de cortes e solvers de subproblema — mas isso é relevante principalmente para quem usa CBC diretamente em C++, não para uso via PuLP (que já configura o CBC como solver padrão nos bastidores).

## Por que usar no TCC
Referência técnica para explicar, na seção 6.3.2, **por que** o CBC consegue resolver o modelo MILP do TCC (que tem variáveis binárias y_j e z_ij além da variável contínua x_ij): o branch-and-cut é justamente o método adequado para problemas com variáveis inteiras/binárias, ao contrário do método Simplex puro (que só resolve LP contínua). É a base teórica que já foi citada no pré-projeto para justificar a escolha do CBC como solver padrão do PuLP.

## Citação sugerida (ABNT)
FORREST, J.; LOUGEE-HEIMER, R. CBC User Guide. In: **Emerging Theory, Methods, and Applications**. Catonsville, MD: INFORMS, 2005. p. 257-277. DOI: https://doi.org/10.1287/educ.1053.0020.

## Ideias para o TCC
- Usar a descrição passo a passo do algoritmo branch-and-cut (bound → branch → poda) na seção 7.1.5 (Métodos de Solução), como complemento ao método Simplex, para explicar como o CBC resolve a parte inteira/binária do modelo que o Simplex sozinho não resolveria.
- Mencionar que o CBC é open-source e mantido pela comunidade COIN-OR, reforçando a justificativa de custo zero e robustez já usada no pré-projeto.
