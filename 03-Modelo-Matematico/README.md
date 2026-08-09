# Modelo Matemático (MILP)

Transcrito da seção 6.2.1–6.2.2 do Pré-Projeto. Ver implementação real em [`alocacao_analistas (1).py`](../alocacao_analistas%20(1).py).

## Conjuntos
- **I** = {1, ..., n} — analistas disponíveis
- **J** = {1, ..., m} — projetos candidatos
- **K** = {1, ..., p} — habilidades técnicas

## Variáveis de decisão
| Variável | Tipo | Papel | Domínio |
|---|---|---|---|
| x_ij | Decisão | Horas do analista i alocadas ao projeto j | Real ≥ 0 |
| y_j | Decisão | Se o projeto j será aceito | Binária {0,1} |
| z_ij | Auxiliar | Se o analista i participa do projeto j | Binária {0,1} |

## Parâmetros dos analistas
S_i (senioridade), C_i (custo/hora), D_i (disponibilidade), A_i (ausência programada), COM_i, COL_i, ORG_i, ADA_i, EST_i (competências comportamentais), SKILL_ik (habilidade técnica k)

## Parâmetros dos projetos
R_j (receita), H_j (horas contratadas), S_j^min, COM_j^min, COL_j^min, ORG_j^min, ADA_j^min, EST_j^min (mínimos comportamentais), N_j^max (máx. analistas), REQ_jk (nível mínimo da habilidade k)

## Parâmetros gerais
- M — big-M, vínculo entre x_ij e z_ij
- h_min — horas mínimas por alocação (evita fragmentação)

## Função objetivo (Equação 1)
Maximizar Z = Σ(j∈J) R_j·y_j − Σ(i∈I) Σ(j∈J) C_i·x_ij

## Restrições
1. **Disponibilidade:** Σ(j) x_ij ≤ D_i, ∀i
2. **Horas contratadas:** Σ(i) x_ij ≤ H_j·y_j, ∀j
3. **Vínculo x-z (limite superior):** x_ij ≤ M·z_ij, ∀i,j
4. **Horas mínimas por alocação:** x_ij ≥ h_min·z_ij, ∀i,j
5. **Máx. analistas por projeto:** Σ(i) z_ij ≤ N_j^max, ∀j
6. **Ao menos um analista se aceito:** Σ(i) z_ij ≥ y_j, ∀j
7. **Senioridade mínima:** S_i ≥ S_j^min·z_ij, ∀i,j
8. Restrições análogas para COM, COL, ORG, ADA, EST (competências comportamentais mínimas)
9. **Habilidades técnicas:** SKILL_ik ≥ REQ_jk·z_ij, ∀i,j,k
10. **Ausência programada:** z_ij ≤ 1 − A_i, ∀i,j
11. **Não negatividade:** x_ij ≥ 0, ∀i,j

## Premissas do modelo
- Um analista pode participar de múltiplos projetos.
- Um projeto pode ser recusado.
- Um projeto pode ter múltiplos analistas, respeitando N_j^max.
- Todo projeto aceito tem ao menos um analista responsável.
- Horas alocadas não ultrapassam horas contratadas.
- Alocação respeita mínimo de horas (h_min).
- Competências são fornecidas pelo gestor e permanecem constantes durante a execução do projeto.

## Matriz de competências comportamentais (Big Five → competências do sistema)
| Competência no sistema | Dimensão Big Five | Descrição |
|---|---|---|
| Comunicação e Relacionamento | Extroversão | Comunicação, interação, influência |
| Colaboração | Amabilidade | Cooperação, empatia, trabalho em equipe |
| Organização e Planejamento | Conscienciosidade | Disciplina, responsabilidade, foco em resultados |
| Adaptabilidade e Inovação | Abertura à Experiência | Flexibilidade, criatividade, adaptação |
| Estabilidade Emocional | Neuroticismo (invertido) | Controle emocional sob pressão |

Referência: [[../01-Literatura/Goldberg-1990-Big-Five-Factor-Structure|Goldberg (1990)]]
