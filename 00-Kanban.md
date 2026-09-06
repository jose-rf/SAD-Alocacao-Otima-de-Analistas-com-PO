---
kanban-plugin: board
---

## Fase 1 - Pré-Projeto e Prototipação

- [x] Finalização do Pré-Projeto
- [x] Criação do protótipo de interface no Figma
- [ ] Início do referencial teórico

## Fase 2 - Modelagem

- [x] Definição do cenário fictício
- [x] Definição do modelo MILP (variáveis, restrições, função objetivo)
- [ ] Finalização do referencial teórico

## Fase 3 - Implementação

- [x] Implementação do modelo em Python/PuLP
- [x] Criação da interface Streamlit
- [x] Persistência SQLite (cadastros + histórico de execuções)
- [x] Menu lateral (4 páginas, ícones via st.navigation) + CPF — "Geração da Alocação" virou expansor dentro do Dashboard
- [x] Teto de disponibilidade fixo (220h/mês, CLT) — sem cálculo por calendário
- [x] Fluxo candidata/confirmada/encerrada de persistência de horas comprometidas (cumulativo)
- [x] Seleção de subconjunto de analistas/projetos por rodada de otimização
- [x] Redesign visual (tema único via .streamlit/config.toml, tabelas de listagem, cards)
- [x] Prazo do projeto (prazo_semanas) + liberação automática de horas comprometidas ao expirar
- [ ] Capturas de tela das telas de habilidades técnicas para as Figuras do TCC

## Fase 4 - Validação

- [ ] Testes, validação e análise de sensibilidade
- [ ] Análise de sensibilidade e cenários excepcionais

## Fase 6 - Atualização do texto do TCC (pendente, pós-implementação)

- [ ] 6.2.2.6 — nova premissa: disponibilidade efetiva (Di − horas comprometidas, liberada ao expirar o prazo do projeto ou ao encerrar manualmente)
- [ ] 6.2.3 — critério real do teto de Di (constante fixa 220h/mês CLT, não calendário)
- [ ] 6.2.4.1/6.2.4.2 — menu lateral (4 páginas) e telas de habilidades como reais (não mais placeholder)
- [ ] 6.2.6 — campos `cpf`, `prazo_semanas` (projetos), `situacao`/`confirmado_em` (execuções)
- [ ] Diagramas UML de 6.2.7 — atributos `cpf` e `prazo_semanas`, situação de execução, casos de uso "escolher/confirmar alocação", "reprocessar alocação" e "encerrar alocação"
- [ ] Seção de limitações/trabalhos futuros — citar o trade-off de reprodutibilidade da expiração automática por prazo (resultado do solver passa a depender da data da consulta)

## Fase 5 - Escrita e Defesa

- [ ] Escrita dos capítulos de resultados
- [ ] Revisão e formatação ABNT
- [ ] Apresentação à Banca

%% kanban:settings
```
{"kanban-plugin":"board","list-collapse":[false,false,false,false,false]}
```
%%
