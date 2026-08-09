# Metodologia de Pesquisa

Resumo estruturado da seção 6 do Pré-Projeto (ABNT), para consulta rápida e evolução conforme o TCC avança.

## 6.1 Classificação da pesquisa
- **Natureza:** pesquisa aplicada (Gil, 2008) — foco na aplicação prática, não apenas na construção teórica do modelo.
- **Abordagem:** quantitativa (Gil, 2008) — variáveis representadas numericamente e processadas em MILP.
- **Dados fictícios:** usados por sensibilidade dos dados reais (salários, margens, perfil de clientes) e para permitir controle deliberado de cenários de teste (ausência de analistas, recusa de projetos, conflitos de disponibilidade). Parâmetros calibrados com base na experiência dos autores, não definidos de forma subjetiva.

## 6.2 Etapas do desenvolvimento
1. Definição de variáveis de decisão e parâmetros → ver [[../03-Modelo-Matematico/README|Modelo Matemático]]
2. Modelagem do problema (conjuntos, função objetivo, restrições, premissas)
3. Implementação em Python/PuLP → ver [[../04-Implementacao/README|Implementação]]
4. Desenvolvimento da interface (Figma → Streamlit)
5. Validação e análise dos resultados (cenários simulados, análise de sensibilidade)

## 6.3 Ferramentas e tecnologias
- Python
- PuLP + Solver CBC
- Figma
- Streamlit

## Pendências identificadas no pré-projeto (marcadas como "[A ser desenvolvido]")
- 6.2.3 Implementação
- 6.2.4.2 Implementação em Streamlit
- 6.2.5 Validação e Análise dos Resultados
- 7.1.3 Programação Linear Inteira Mista (MILP) — teoria
- 7.1.5 Métodos de Solução (Simplex, Branch and Bound, Análise de Sensibilidade)
- 7.1.4 Programação de Metas — desenvolver exemplo
- Seções 7.2, 7.3 (parcial), 7.4 (parcial), 7.5 inteira
