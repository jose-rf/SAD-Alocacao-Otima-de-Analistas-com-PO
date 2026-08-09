"""
Modelo de Programacao Linear Inteira Mista (MILP) para alocacao de analistas
em projetos de assessoria em regime de horas.

Implementa exatamente a formulacao apresentada na secao 6.2.2 do pre-projeto
de TCC "Sistema para Alocacao de Analistas em Projetos de Assessoria em
Regime de Horas: uma abordagem por Programacao Linear Inteira Mista (MILP)
com foco na maximizacao do lucro liquido" (Franca; Brito, UEMG, 2026).

Conjuntos (secao 6.2.2.2):
    I = analistas disponiveis
    J = projetos candidatos a aceitacao
    K = habilidades tecnicas consideradas na alocacao

Variaveis de decisao (secao 6.2.2.3 / Tabela 6.2.1.1):
    x[i, j] : horas do analista i alocadas ao projeto j (continua, >= 0)
    y[j]    : projeto j aceito (1) ou recusado (0) (binaria)
    z[i, j] : analista i vinculado ao projeto j (1) ou nao (0) (binaria)

Funcao objetivo (Equacao 1):
    Maximizar Z = sum_j Rj * y[j]  -  sum_i sum_j Ci * x[i, j]

Restricoes (Equacoes 2 a 11), na integra conforme secao 6.2.2.5:
    (2)  sum_j x[i, j] <= Di                         para todo i
    (3)  sum_i x[i, j] <= Hj * y[j]                   para todo j
    (4)  x[i, j] <= M * z[i, j]                       para todo i, j
    (5)  x[i, j] >= h_min * z[i, j]                   para todo i, j
    (6)  sum_i z[i, j] <= Njmax                       para todo j
    (7)  sum_i z[i, j] >= y[j]                        para todo j
    (8)  Si >= Sjmin * z[i, j]                        para todo i, j
         (e restricoes analogas para COM, COL, ORG, ADA, EST)
    (9)  SKILLik >= REQjk * z[i, j]                   para todo i, j, k
    (10) z[i, j] <= 1 - Ai                            para todo i, j
    (11) x[i, j] >= 0                                 para todo i, j

Unica generalizacao explicita em relacao ao artigo: a Equacao 7 e' parametrizada
por um numero minimo de analistas por projeto (min_analistas, campo presente no
prototipo de interface, secao 6.2.4.1). Com min_analistas = 1 (valor padrao) a
restricao volta a ser identica a Equacao 7 do artigo (sum_i z[i,j] >= y[j]).

O big-M (secao 6.2.1.5) e' calculado automaticamente como o maior valor entre
as horas contratadas dos projetos e a disponibilidade dos analistas, de modo a
ser "suficientemente grande" sem enfraquecer a formulacao (nenhuma alocacao
individual pode superar nem as horas contratadas do projeto - Equacao 3 - nem
a disponibilidade do analista - Equacao 2).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pulp

# ---------------------------------------------------------------------------
# Constantes do modelo (secao 6.2.1.4 - Matriz de Competencias Comportamentais,
# baseada no modelo conceitual Big Five / Goldberg, 1990)
# ---------------------------------------------------------------------------

NIVEIS: Dict[str, int] = {"Junior": 1, "Pleno": 2, "Senior": 3}
NIVEIS_LABEL: Dict[str, str] = {"Junior": "Junior", "Pleno": "Pleno", "Senior": "Senior"}

TRAITS: Tuple[str, ...] = ("COM", "COL", "ORG", "ADA", "EST")
TRAIT_LABELS: Dict[str, str] = {
    "COM": "Comunicacao",
    "COL": "Colaboracao",
    "ORG": "Organizacao",
    "ADA": "Adaptabilidade",
    "EST": "Estabilidade Emocional",
}


# ---------------------------------------------------------------------------
# Entidades de entrada (parametros do modelo - secao 6.2.1.2 e 6.2.1.3)
# ---------------------------------------------------------------------------

@dataclass
class Analista:
    nome: str
    senioridade: str                       # Si (Junior/Pleno/Senior)
    custo_hora: float                      # Ci
    disponibilidade: float                 # Di
    ausente: bool = False                  # Ai (auxilio programada)
    competencias: Dict[str, float] = field(default_factory=dict)   # SKILLik
    big5: Dict[str, float] = field(
        default_factory=lambda: {t: 50.0 for t in TRAITS}
    )                                       # COMi, COLi, ORGi, ADAi, ESTi


@dataclass
class Projeto:
    nome: str
    receita: float                         # Rj
    horas: float                           # Hj
    nivel_min: str                         # Sjmin (Junior/Pleno/Senior)
    max_analistas: int                     # Njmax
    min_analistas: int = 1                 # generalizacao da Equacao 7
    competencias_min: Dict[str, float] = field(default_factory=dict)  # REQjk
    big5_min: Dict[str, float] = field(
        default_factory=lambda: {t: 0.0 for t in TRAITS}
    )                                       # COMjmin, COLjmin, ORGjmin, ADAjmin, ESTjmin


# ---------------------------------------------------------------------------
# Saida do modelo
# ---------------------------------------------------------------------------

@dataclass
class Alocacao:
    analista: str
    nivel: str
    projeto: str
    horas: float
    custo: float
    receita: float


@dataclass
class ResumoAnalista:
    nome: str
    disponibilidade: float
    horas_alocadas: float

    @property
    def utilizacao(self) -> float:
        if self.disponibilidade <= 0:
            return 0.0
        return min(self.horas_alocadas / self.disponibilidade, 1.0)


@dataclass
class ResultadoOtimizacao:
    status: str
    viavel: bool
    lucro_liquido: float
    receita_total: float
    custo_total: float
    alocacoes: List[Alocacao]
    aceitos: List[str]
    recusados: List[Tuple[str, str]]        # (nome_projeto, motivo)
    resumo_analistas: List[ResumoAnalista]


# ---------------------------------------------------------------------------
# Construcao e resolucao do modelo MILP
# ---------------------------------------------------------------------------

def _calcular_big_m(analistas: List[Analista], projetos: List[Projeto]) -> float:
    """Big-M (secao 6.2.1.5): suficientemente grande para nao restringir x[i,j]
    alem do que as Equacoes 2 e 3 ja restringem."""
    candidatos = [p.horas for p in projetos] + [a.disponibilidade for a in analistas]
    candidatos = [c for c in candidatos if c and c > 0]
    return max(candidatos) if candidatos else 1.0


def resolver_modelo(
    analistas: List[Analista],
    projetos: List[Projeto],
    h_min: float,
) -> ResultadoOtimizacao:
    """Monta e resolve o modelo MILP (Equacoes 1 a 11) com PuLP/CBC."""

    I = list(range(len(analistas)))
    J = list(range(len(projetos)))
    K = sorted({k for p in projetos for k, v in p.competencias_min.items() if v > 0})

    M = _calcular_big_m(analistas, projetos)

    prob = pulp.LpProblem("Alocacao_Analistas_MILP", pulp.LpMaximize)

    x = {
        (i, j): pulp.LpVariable(f"x_{i}_{j}", lowBound=0, cat="Continuous")
        for i in I for j in J
    }
    y = {j: pulp.LpVariable(f"y_{j}", cat="Binary") for j in J}
    z = {(i, j): pulp.LpVariable(f"z_{i}_{j}", cat="Binary") for i in I for j in J}

    # Equacao 1 - Funcao objetivo: maximizar o lucro liquido
    prob += (
        pulp.lpSum(projetos[j].receita * y[j] for j in J)
        - pulp.lpSum(analistas[i].custo_hora * x[i, j] for i in I for j in J)
    ), "Lucro_Liquido"

    # Equacao 2 - Disponibilidade de horas de cada analista
    for i in I:
        prob += (
            pulp.lpSum(x[i, j] for j in J) <= analistas[i].disponibilidade,
            f"disponibilidade_{i}",
        )

    # Equacao 3 - Horas alocadas a um projeto vs. horas contratadas
    for j in J:
        prob += (
            pulp.lpSum(x[i, j] for i in I) <= projetos[j].horas * y[j],
            f"demanda_{j}",
        )

    # Equacao 4 - Vinculo entre x[i,j] e z[i,j] via big-M
    for i in I:
        for j in J:
            prob += x[i, j] <= M * z[i, j], f"vinculo_M_{i}_{j}"

    # Equacao 5 - Horas minimas por alocacao (h_min)
    for i in I:
        for j in J:
            prob += x[i, j] >= h_min * z[i, j], f"horas_min_{i}_{j}"

    # Equacao 6 - Numero maximo de analistas por projeto (Njmax)
    for j in J:
        prob += (
            pulp.lpSum(z[i, j] for i in I) <= projetos[j].max_analistas,
            f"max_analistas_{j}",
        )

    # Equacao 7 (generalizada por min_analistas; min_analistas=1 == artigo)
    for j in J:
        prob += (
            pulp.lpSum(z[i, j] for i in I) >= projetos[j].min_analistas * y[j],
            f"min_analistas_{j}",
        )

    # Equacao 8 - Senioridade minima exigida pelo projeto
    for i in I:
        for j in J:
            prob += (
                NIVEIS[analistas[i].senioridade]
                >= NIVEIS[projetos[j].nivel_min] * z[i, j],
                f"senioridade_{i}_{j}",
            )

    # Equacao 8 (restricoes analogas) - competencias comportamentais Big Five
    for trait in TRAITS:
        for i in I:
            for j in J:
                minimo = projetos[j].big5_min.get(trait, 0.0)
                if minimo > 0:
                    valor = analistas[i].big5.get(trait, 0.0)
                    prob += valor >= minimo * z[i, j], f"{trait}_{i}_{j}"

    # Equacao 9 - Habilidades tecnicas (SKILLik >= REQjk * z[i,j])
    for k in K:
        for i in I:
            for j in J:
                req = projetos[j].competencias_min.get(k, 0.0)
                if req > 0:
                    nivel = analistas[i].competencias.get(k, 0.0)
                    prob += nivel >= req * z[i, j], f"skill_{k}_{i}_{j}"

    # Equacao 10 - Ausencia programada impede alocacao
    for i in I:
        for j in J:
            prob += z[i, j] <= (0 if analistas[i].ausente else 1), f"ausencia_{i}_{j}"

    # Equacao 11 - Nao negatividade de x[i,j] ja garantida por lowBound=0

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    status = pulp.LpStatus[prob.status]
    viavel = status == "Optimal"

    if not viavel:
        return ResultadoOtimizacao(
            status=status,
            viavel=False,
            lucro_liquido=0.0,
            receita_total=0.0,
            custo_total=0.0,
            alocacoes=[],
            aceitos=[],
            recusados=[(p.nome, "modelo infactivel: nao existe combinacao de "
                                 "alocacoes que satisfaca simultaneamente todas "
                                 "as restricoes.") for p in projetos],
            resumo_analistas=[],
        )

    alocacoes: List[Alocacao] = []
    for i in I:
        for j in J:
            horas = x[i, j].value() or 0.0
            if horas > 1e-6:
                custo = horas * analistas[i].custo_hora
                taxa = projetos[j].horas and (projetos[j].receita / projetos[j].horas)
                receita_gerada = horas * (taxa or 0.0)
                alocacoes.append(
                    Alocacao(
                        analista=analistas[i].nome,
                        nivel=analistas[i].senioridade,
                        projeto=projetos[j].nome,
                        horas=round(horas, 2),
                        custo=round(custo, 2),
                        receita=round(receita_gerada, 2),
                    )
                )

    aceitos_idx = [j for j in J if (y[j].value() or 0) > 0.5]
    aceitos = [projetos[j].nome for j in aceitos_idx]

    recusados: List[Tuple[str, str]] = []
    for j in J:
        if j not in aceitos_idx:
            recusados.append((projetos[j].nome, _diagnosticar_recusa(projetos[j], analistas, h_min)))

    horas_por_analista = {i: 0.0 for i in I}
    for i in I:
        for j in J:
            horas_por_analista[i] += x[i, j].value() or 0.0

    resumo_analistas = [
        ResumoAnalista(
            nome=analistas[i].nome,
            disponibilidade=analistas[i].disponibilidade,
            horas_alocadas=round(horas_por_analista[i], 2),
        )
        for i in I
    ]

    receita_total = sum(projetos[j].receita for j in aceitos_idx)
    custo_total = sum(a.custo for a in alocacoes)
    lucro_liquido = pulp.value(prob.objective) or 0.0

    return ResultadoOtimizacao(
        status=status,
        viavel=True,
        lucro_liquido=round(lucro_liquido, 2),
        receita_total=round(receita_total, 2),
        custo_total=round(custo_total, 2),
        alocacoes=alocacoes,
        aceitos=aceitos,
        recusados=recusados,
        resumo_analistas=resumo_analistas,
    )


def _diagnosticar_recusa(projeto: Projeto, analistas: List[Analista], h_min: float) -> str:
    """Nota explicativa (fora do modelo formal) sobre a provavel causa da
    recusa de um projeto pelo solver, usada apenas para apresentar o
    resultado ao gestor na tela de resultados (secao 6.2.4.1, Figura 4)."""

    elegiveis = []
    for a in analistas:
        if a.ausente:
            continue
        if NIVEIS[a.senioridade] < NIVEIS[projeto.nivel_min]:
            continue
        if any(
            a.big5.get(t, 0.0) < minimo
            for t, minimo in projeto.big5_min.items()
            if minimo > 0
        ):
            continue
        if any(
            a.competencias.get(k, 0.0) < minimo
            for k, minimo in projeto.competencias_min.items()
            if minimo > 0
        ):
            continue
        if a.disponibilidade < h_min:
            continue
        elegiveis.append(a)

    if not elegiveis:
        return ("nenhum analista atende simultaneamente a senioridade minima, as "
                "competencias tecnicas e o perfil comportamental exigidos pelo projeto.")
    if len(elegiveis) < projeto.min_analistas:
        return (f"apenas {len(elegiveis)} analista(s) elegivel(is), abaixo do minimo "
                f"de {projeto.min_analistas} exigido pelo projeto.")
    capacidade = sum(a.disponibilidade for a in elegiveis)
    if capacidade < projeto.horas:
        return ("a capacidade agregada de horas dos analistas elegiveis e menor que "
                "as horas contratadas do projeto.")
    return ("projeto nao selecionado pelo modelo por nao contribuir para a "
            "maximizacao do lucro liquido diante da disponibilidade de horas "
            "dos analistas nesse cenario (trade-off de otimizacao).")
