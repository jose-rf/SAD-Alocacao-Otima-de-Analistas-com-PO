# Modelo Matemático (MILP)

Transcrito da seção 6.2.1–6.2.2 do Pré-Projeto. Ver implementação real em
[`optimization.py`](../optimization.py). O código tem três ajustes explícitos
em relação ao texto do pré-projeto (piso de horas, `Njmin` e cobertura
conjunta de habilidades técnicas) — ver seção **Ajustes em relação ao
pré-projeto**, abaixo, e a documentação completa em [`README.md`](../README.md#fidelidade-ao-pre-projeto-e-ajustes-explicitos).

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
R_j (receita), H_j (horas contratadas), S_j^min, COM_j^min, COL_j^min, ORG_j^min, ADA_j^min, EST_j^min (mínimos comportamentais), N_j^max (máx. analistas), N_j^min (mín. analistas, default 1 — ver ajustes abaixo), REQ_jk (nível mínimo da habilidade k)

## Parâmetros gerais
- M — big-M, vínculo entre x_ij e z_ij
- h_min — horas mínimas por alocação (evita fragmentação)

## Função objetivo (Equação 1)
Maximizar Z = Σ(j∈J) R_j·y_j − Σ(i∈I) Σ(j∈J) C_i·x_ij

## Restrições
1. **Disponibilidade:** Σ(j) x_ij ≤ D_i, ∀i
2. **Horas contratadas (teto + piso):** Σ(i) x_ij ≤ H_j·y_j **e** Σ(i) x_ij ≥ H_j·y_j, ∀j — a restrição de piso é um ajuste em relação ao pré-projeto (ver abaixo)
3. **Vínculo x-z (limite superior):** x_ij ≤ M·z_ij, ∀i,j
4. **Horas mínimas por alocação:** x_ij ≥ h_min·z_ij, ∀i,j
5. **Máx. analistas por projeto:** Σ(i) z_ij ≤ N_j^max, ∀j
6. **Mín. analistas se aceito (N_j^min):** Σ(i) z_ij ≥ N_j^min·y_j, ∀j — generalização do "ao menos um analista" do pré-projeto (N_j^min = 1 reproduz o texto original)
7. **Senioridade mínima:** S_i ≥ S_j^min·z_ij, ∀i,j
8. Restrições análogas para COM, COL, ORG, ADA, EST (competências comportamentais mínimas), exigidas individualmente por analista
9. **Cobertura conjunta de habilidades técnicas:** para cada habilidade k com REQ_jk > 0, Σ(i ∈ I_jk) z_ij ≥ y_j, onde I_jk = {i : SKILL_ik ≥ REQ_jk} — não é mais exigido que um único analista cubra sozinho todas as habilidades (ver ajustes abaixo)
10. **Ausência programada:** z_ij ≤ 1 − A_i, ∀i,j
11. **Não negatividade:** x_ij ≥ 0, ∀i,j

## Ajustes em relação ao pré-projeto

Três ajustes explícitos e documentados, todos lineares, sem variáveis novas
(detalhamento completo no [`README.md`](../README.md#fidelidade-ao-pre-projeto-e-ajustes-explicitos) do código):

1. **Piso de horas contratadas** — evita que o modelo aceite um projeto,
   reconheça a receita cheia R_j e aloque menos horas que H_j.
2. **N_j^min** — generaliza "ao menos um analista responsável" para um
   mínimo configurável por projeto (default 1, com validação
   1 ≤ N_j^min ≤ N_j^max no cadastro).
3. **Cobertura conjunta de habilidades técnicas** — relaxamento estrito do
   espaço de soluções viáveis anterior (toda solução antes viável continua
   viável), então o lucro ótimo nunca piora. Senioridade e competências
   comportamentais continuam exigidas individualmente.

**Premissa nova de dados (não uma equação do MILP em si, registrada em
06/09/2026 — pendente de redação formal na seção 6.2.2.6 do TCC):** o `D_i`
usado na Equação 2 numa rodada de otimização é a disponibilidade **efetiva**,
não a nominal cadastrada — `D_i_efetivo = D_i − Σ(horas em TODAS as
execuções com situação = CONFIRMADA)`, soma cumulativa (sem segmentação por
período/mês), calculada dinamicamente (ver
[`README.md`](../README.md#persistencia-de-horas-comprometidas-entre-execucoes-candidata--confirmada--encerrada)).
Isso não muda a formulação da Equação 2 — só o valor de `D_i` que entra
nela. As horas só voltam a ficar livres quando o gestor encerra
explicitamente uma execução confirmada (ação registrada em 06/09/2026).

## Premissas do modelo
- Um analista pode participar de múltiplos projetos.
- Um projeto pode ser recusado.
- Um projeto pode ter múltiplos analistas, respeitando N_j^max.
- Todo projeto aceito tem ao menos um analista responsável.
- Horas alocadas não ultrapassam horas contratadas.
- Alocação respeita mínimo de horas (h_min).
- Cada rodada de otimização pode considerar um subconjunto de analistas e
  projetos, não necessariamente todo o cadastro (seleção feita pelo gestor).
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
