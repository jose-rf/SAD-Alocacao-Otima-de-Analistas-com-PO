# Modelo MILP (Programacao Linear Inteira Mista) da alocacao de analistas.
# Equacoes 1 a 11 conforme secao 6.2.2 do pre-projeto de TCC. Resolvido com
# PuLP usando o solver CBC.
#
# Conjuntos:
#   I = analistas
#   J = projetos
#   K = habilidades tecnicas
#
# Variaveis:
#   x[i,j] -> horas do analista i no projeto j (continua)
#   y[j]   -> projeto j aceito ou nao (binaria)
#   z[i,j] -> analista i vinculado ao projeto j (binaria)

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pulp

NIVEIS: Dict[str, int] = {"Junior": 1, "Pleno": 2, "Senior": 3}
NIVEIS_LABEL: Dict[str, str] = {"Junior": "Junior", "Pleno": "Pleno", "Senior": "Senior"}

# competencias comportamentais baseadas no Big Five (Goldberg, 1990)
TRAITS: Tuple[str, ...] = ("COM", "COL", "ORG", "ADA", "EST")
TRAIT_LABELS: Dict[str, str] = {
    "COM": "Comunicacao",
    "COL": "Colaboracao",
    "ORG": "Organizacao",
    "ADA": "Adaptabilidade",
    "EST": "Estabilidade Emocional",
}


@dataclass
class Analista:
    nome: str
    senioridade: str                       # Si
    custo_hora: float                      # Ci
    disponibilidade: float                 # Di
    ausente: bool = False                  # Ai
    competencias: Dict[str, float] = field(default_factory=dict)   # SKILLik
    big5: Dict[str, float] = field(
        default_factory=lambda: {t: 50.0 for t in TRAITS}
    )


@dataclass
class Projeto:
    nome: str
    receita: float                         # Rj
    horas: float                           # Hj
    nivel_min: str                         # Sjmin
    max_analistas: int                     # Njmax
    competencias_min: Dict[str, float] = field(default_factory=dict)  # REQjk
    big5_min: Dict[str, float] = field(
        default_factory=lambda: {t: 0.0 for t in TRAITS}
    )


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


def _calcular_big_m(analistas: List[Analista], projetos: List[Projeto]) -> float:
    # M so precisa ser maior que qualquer x[i,j] possivel; o maior valor
    # entre horas contratadas e disponibilidade ja serve pra isso
    candidatos = [p.horas for p in projetos] + [a.disponibilidade for a in analistas]
    candidatos = [c for c in candidatos if c and c > 0]
    return max(candidatos) if candidatos else 1.0


def resolver_modelo(
    analistas: List[Analista],
    projetos: List[Projeto],
    h_min: float,
) -> ResultadoOtimizacao:
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

    # Eq 1 - funcao objetivo: lucro liquido = receita dos projetos aceitos - custo da mao de obra
    prob += (
        pulp.lpSum(projetos[j].receita * y[j] for j in J)
        - pulp.lpSum(analistas[i].custo_hora * x[i, j] for i in I for j in J)
    ), "Lucro_Liquido"

    # Eq 2 - disponibilidade do analista
    for i in I:
        prob += (
            pulp.lpSum(x[i, j] for j in J) <= analistas[i].disponibilidade,
            f"disponibilidade_{i}",
        )

    # Eq 3 - horas alocadas nao passam das horas contratadas (so vale se o projeto foi aceito)
    for j in J:
        prob += (
            pulp.lpSum(x[i, j] for i in I) <= projetos[j].horas * y[j],
            f"demanda_{j}",
        )

    # Eq 4 - liga x e z (se z=0, x tem que ser 0)
    for i in I:
        for j in J:
            prob += x[i, j] <= M * z[i, j], f"vinculo_M_{i}_{j}"

    # Eq 5 - se o analista foi vinculado, tem que cumprir pelo menos h_min horas
    for i in I:
        for j in J:
            prob += x[i, j] >= h_min * z[i, j], f"horas_min_{i}_{j}"

    # Eq 6 - numero maximo de analistas por projeto
    for j in J:
        prob += (
            pulp.lpSum(z[i, j] for i in I) <= projetos[j].max_analistas,
            f"max_analistas_{j}",
        )

    # Eq 7 - projeto aceito precisa ter pelo menos um analista
    for j in J:
        prob += (
            pulp.lpSum(z[i, j] for i in I) >= y[j],
            f"min_um_analista_{j}",
        )

    # Eq 8 - senioridade minima
    for i in I:
        for j in J:
            prob += (
                NIVEIS[analistas[i].senioridade]
                >= NIVEIS[projetos[j].nivel_min] * z[i, j],
                f"senioridade_{i}_{j}",
            )

    # Eq 8 (analogas) - competencias comportamentais. so entra restricao quando
    # o projeto exige um minimo > 0 pra aquela dimensao (senao seria sempre verdade)
    for trait in TRAITS:
        for i in I:
            for j in J:
                minimo = projetos[j].big5_min.get(trait, 0.0)
                if minimo > 0:
                    valor = analistas[i].big5.get(trait, 0.0)
                    prob += valor >= minimo * z[i, j], f"{trait}_{i}_{j}"

    # Eq 9 - habilidades tecnicas exigidas pelo projeto
    for k in K:
        for i in I:
            for j in J:
                req = projetos[j].competencias_min.get(k, 0.0)
                if req > 0:
                    nivel = analistas[i].competencias.get(k, 0.0)
                    prob += nivel >= req * z[i, j], f"skill_{k}_{i}_{j}"

    # Eq 10 - analista ausente nao pode ser alocado
    for i in I:
        for j in J:
            prob += z[i, j] <= (0 if analistas[i].ausente else 1), f"ausencia_{i}_{j}"

    # Eq 11 - x[i,j] >= 0 ja garantido pelo lowBound la em cima

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
    # isso aqui e so pra mostrar um motivo pro usuario na tela de resultado,
    # nao faz parte do modelo (nao entra em nenhuma restricao do solver)
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
    capacidade = sum(a.disponibilidade for a in elegiveis)
    if capacidade < projeto.horas:
        return ("a capacidade agregada de horas dos analistas elegiveis e menor que "
                "as horas contratadas do projeto.")
    return ("projeto nao selecionado pelo modelo por nao contribuir para a "
            "maximizacao do lucro liquido diante da disponibilidade de horas "
            "dos analistas nesse cenario (trade-off de otimizacao).")
