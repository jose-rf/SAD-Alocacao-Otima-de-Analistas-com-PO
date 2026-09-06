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
- [x] Menu lateral (5 páginas) + CPF + teto de disponibilidade por calendário
- [x] Fluxo candidata/confirmada de persistência de horas comprometidas
- [x] Seleção de subconjunto de analistas/projetos por rodada de otimização
- [ ] Capturas de tela das telas de habilidades técnicas para as Figuras do TCC

## Fase 4 - Validação

- [ ] Testes, validação e análise de sensibilidade
- [ ] Análise de sensibilidade e cenários excepcionais

## Fase 6 - Atualização do texto do TCC (pendente, pós-implementação)

- [ ] 6.2.2.6 — nova premissa: disponibilidade efetiva (Di − horas comprometidas)
- [ ] 6.2.3 — critério real do teto de Di (calendário do período de referência)
- [ ] 6.2.4.1/6.2.4.2 — menu lateral e telas de habilidades como reais (não mais placeholder)
- [ ] 6.2.6 — campos `cpf` e `situacao`/`periodo_referencia` em `execucoes`
- [ ] Diagramas UML de 6.2.7 — atributo `cpf`, situação de execução, casos de uso "escolher/confirmar alocação" e "reprocessar alocação"

## Fase 5 - Escrita e Defesa

- [ ] Escrita dos capítulos de resultados
- [ ] Revisão e formatação ABNT
- [ ] Apresentação à Banca

%% kanban:settings
```
{"kanban-plugin":"board","list-collapse":[false,false,false,false,false]}
```
%%
