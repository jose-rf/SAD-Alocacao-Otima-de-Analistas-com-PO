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
- Cada edição de campo na interface grava direto no banco (sem botão "salvar" separado)

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
Status: **implementado** ([`app.py`](../app.py), seção 6.2.4.2 do pré-projeto). Fluxo de 7 telas:
1. Analistas (cadastro geral)
2. Habilidades técnicas dos analistas (tela dedicada, catálogo + SKILL_ik)
3. Projetos (cadastro geral, incluindo N_j^max e N_j^min)
4. Habilidades técnicas exigidas pelos projetos (tela dedicada, REQ_jk)
5. Parâmetros e execução (h_min, roda o solver)
6. Resultado (lucro líquido, alocação detalhada, aceitos/recusados)
7. Exportação do relatório (.txt)

## Validação e análise de sensibilidade
Status: a ser desenvolvido (seção 6.2.5 do pré-projeto). Planejar cenários excepcionais: ausência de analistas, recusa de projetos, conflitos de disponibilidade.
