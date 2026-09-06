# Implementação

## Python + PuLP + CBC
- Código atual do modelo: [`optimization.py`](../optimization.py)
- Solver: CBC (padrão do PuLP) — ver [[../01-Literatura/Forrest-Lougee-Heimer-2005-CBC-User-Guide]]
- Biblioteca: PuLP — ver [[../01-Literatura/Mitchell-OSullivan-Dunning-2011-PuLP-Toolkit]]

## Persistência (SQLite)
- Código: [`db.py`](../db.py) — 7 tabelas (`analistas`, `projetos`, `habilidades`,
  `analista_habilidade`, `projeto_habilidade_requerida`, `execucoes`, `alocacoes`)
- Banco local `alocacao.db`, criado automaticamente na primeira execução
  (git-ignored — não versionado)
- Cada edição é salva explicitamente (botão "Salvar" em cada formulário)
- `analistas.cpf` — chave do analista, validação de formato (`000.000.000-00`)
  e índice `UNIQUE` parcial (ignora vazio, permite a linha em branco recém-criada)
- `analistas.disponibilidade` — teto fixo `TETO_HORAS_MENSAIS_CLT = 220`
  (44h semanais, art. 58 CLT), sem cálculo por calendário
- `execucoes.situacao` (`candidata`/`confirmada`/`encerrada`) + `input_hash` —
  suportam o fluxo de persistência de horas comprometidas entre execuções
  (soma cumulativa, sem segmentação por período; só diminui ao encerrar uma
  execução confirmada) — ver seção dedicada no
  [README.md](../README.md#persistencia-de-horas-comprometidas-entre-execucoes-candidata--confirmada--encerrada)

**Pendente de atualização no texto do pré-projeto** (seções 6.2.2.6, 6.2.3,
6.2.6, diagramas UML 6.2.7): campo `cpf`, critério real do teto de `Di`
(constante fixa CLT, não calendário), situação de `execucoes` (incluindo
`encerrada`) e o caso de uso "encerrar alocação". Registrado em 06/09/2026
após revisão ao vivo do protótipo publicado — implementar no código
primeiro, atualizar o texto depois.

## Figma (prototipação)
Telas planejadas (seção 6.2.4.1 do pré-projeto), todas implementadas em Streamlit:
- [x] Tela Principal (cadastro de analistas e projetos)
- [x] Tela de Resultados
- [x] Pop-Up Cadastro de Projetos
- [x] Pop-Up Cadastro de Analistas
- [x] Pop-Up Cadastro de Habilidades Técnicas
- [x] Pop-Up Cadastro de Escala de Habilidade Comportamental

Duas telas adicionais foram implementadas **sem mockup prévio no Figma**
(mantendo a mesma linguagem visual das telas de cadastro — sliders 0-100,
mesmo padrão do perfil Big Five). Capturas de tela reais dessas telas ainda
precisam ser geradas para documentar as novas Figuras no TCC:
- [ ] Figura — Habilidades técnicas dos analistas (catálogo global + proficiência SKILL_ik)
- [ ] Figura — Habilidades técnicas exigidas pelos projetos (REQ_jk)

## Streamlit (interface web)
Status: **implementado** ([`app.py`](../app.py), seção 6.2.4.2 do pré-projeto,
atualizada em 06/09/2026 para menu lateral com ícones via `st.navigation`/
`st.Page` — texto do pré-projeto ainda descreve fluxo de rolagem contínua e
precisa ser revisado). Tema escuro consolidado em `.streamlit/config.toml`
(uma única cor de destaque, sem CSS solto no código). Menu lateral com 5
páginas (sem seletor de período — removido em 06/09/2026):
1. **Cadastro de Analistas** — tabela de listagem + formulário de edição
   individual: nome, CPF, senioridade, custo/hora, disponibilidade (teto
   fixo de 220h/mês, CLT, sem cálculo por calendário), ausência programada,
   Big Five (labels por extenso)
2. **Cadastro de Projetos** — tabela de listagem + formulário de edição
   individual: nome, receita, horas, N_j^max, N_j^min, nível técnico
   mínimo, Big Five mínimo
3. **Cadastro de Habilidades Técnicas** — catálogo global + abas de
   proficiência dos analistas (SKILL_ik) e exigência dos projetos (REQ_jk)
4. **Geração da Alocação** — h_min, seleção de subconjunto de
   analistas/projetos, disponibilidade efetiva (soma cumulativa de horas
   confirmadas, sem período), comparação de hash com a última execução,
   botão "Reprocessar / gerar prévia"
5. **Dashboard de Resultados** — tabela com histórico de execuções, KPIs,
   alocação detalhada, botão "Escolher esta alocação" (confirma) ou
   "Encerrar alocação" (libera as horas), exportação (.txt)

## Validação e análise de sensibilidade
Status: a ser desenvolvido (seção 6.2.5 do pré-projeto). Planejar cenários excepcionais: ausência de analistas, recusa de projetos, conflitos de disponibilidade.
