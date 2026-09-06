# Painel Geral — TCC

**Título:** Sistema para Alocação de Analistas em Projetos de Assessoria em Regime de Horas: uma Abordagem por Programação Linear Inteira Mista (MILP) com Foco na Maximização do Lucro Líquido

**Autores:** José Rodrigues de França, Julia Alves de Brito
**Orientador:** Prof. Eduardo Henrique Marques Ferreira
**Instituição:** UEMG — Sistemas de Informação, Unidade Passos
**Ano:** 2026

## Pergunta de pesquisa
Como um modelo de Programação Linear Inteira Mista (MILP) pode otimizar a alocação de recursos baseado na *Skill-Based Resource Allocation*, considerando custos, senioridade, competências comportamentais e competências técnicas dos analistas, de modo a maximizar o lucro líquido da organização?

## Objetivo geral
Desenvolver um sistema de apoio à decisão (SAD) para otimizar a alocação de analistas em projetos de assessoria em regime de horas, maximizando o lucro líquido da organização.

## Navegação rápida
- [[00-Kanban]] — quadro de tarefas por fase
- [[01-Literatura/README|Literatura]] — livros, artigos e sites de referência
- [[02-Metodologia/README|Metodologia]] — classificação da pesquisa e etapas
- [[03-Modelo-Matematico/README|Modelo Matemático]] — variáveis, parâmetros, função objetivo e restrições
- [[04-Implementacao/README|Implementação]] — Python/PuLP, Figma, Streamlit
- [[05-Reunioes/README|Reuniões]] — atas com orientador e dupla
- [[06-Recursos-e-Anexos/Cronograma|Cronograma]] — cronograma completo do TCC

## Ferramentas e tecnologias
- Python + PuLP (modelagem MILP) + Solver CBC
- Figma (prototipação de interface)
- Streamlit (interface web)
- SQLite (persistência de cadastros e histórico de execuções)

## Código no repositório
- [`optimization.py`](../optimization.py) — modelo MILP (Equações 1-11 + ajustes documentados no README)
- [`db.py`](../db.py) — persistência SQLite (schema, CRUD, seed de dados de exemplo)
- [`app.py`](../app.py) — interface Streamlit (7 telas: cadastro, execução, resultados, exportação)
