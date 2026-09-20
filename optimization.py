# Modelo MILP (Programacao Linear Inteira Mista) da alocacao de analistas.
# Base: Equacoes 1 a 11 da secao 6.2.2 do pre-projeto de TCC, resolvidas com
# PuLP/CBC. Tres ajustes explicitos em relacao ao artigo (documentados aqui
# e no README, todos lineares, sem variaveis novas):
#
#   - Eq. 3 ganhou uma restricao simetrica de piso: projeto aceito passa a
#     exigir Sum_i x[i,j] == Hj (nao so <= Hj), evitando que o lucro
#     reconheca a receita cheia sem entregar as horas contratadas.
#   - Eq. 7 foi generalizada por um parametro Njmin (minimo de analistas por
#     projeto, default 1). Com Njmin=1 a restricao volta a ser identica ao
#     artigo.
#   - Eq. 9 deixou de exigir que cada analista vinculado cubra sozinho todas
#     as habilidades tecnicas exigidas; agora basta que, para cada
#     habilidade exigida, ao menos um analista da equipe a atenda (cobertura
#     conjunta). E' um relaxamento estrito do espaco viavel anterior: toda
#     solucao antes viavel continua viavel, entao o lucro otimo nunca piora.
#
# Conjuntos:
#   I = analistas
#   J = projetos
#   K = habilidades tecnicas exigidas por algum projeto (REQjk > 0)
#
# Variaveis:
#   x[i,j] -> horas do analista i no projeto j (continua)
#   y[j]   -> projeto j aceito ou nao (binaria)
#   z[i,j] -> analista i vinculado ao projeto j (binaria)

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pulp

NIVEIS: Dict[str, int] = {"Junior": 1, "Pleno": 2, "Senior": 3}
# Chaves internas ("Junior"/"Senior") ficam sem acento de proposito - sao
# identificadores armazenados no banco. NIVEIS_LABEL e' so' pra exibicao.
NIVEIS_LABEL: Dict[str, str] = {"Junior": "Júnior", "Pleno": "Pleno", "Senior": "Sênior"}

# competencias comportamentais baseadas no Big Five (Goldberg, 1990)
TRAITS: Tuple[str, ...] = ("COM", "COL", "ORG", "ADA", "EST")
TRAIT_LABELS: Dict[str, str] = {
    "COM": "Comunicação",
    "COL": "Colaboração",
    "ORG": "Organização",
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
    id: Optional[int] = None               # id_analista no banco (so' pra' religar o
                                            # resultado ao registro certo - nome nao e' unico)


@dataclass
class Projeto:
    nome: str
    receita: float                         # Rj
    horas: float                           # Hj
    nivel_min: str                         # Sjmin
    max_analistas: int                     # Njmax
    min_analistas: int = 1                 # Njmin (default = 1, ver topo do arquivo)
    competencias_min: Dict[str, float] = field(default_factory=dict)  # REQjk
    big5_min: Dict[str, float] = field(
        default_factory=lambda: {t: 0.0 for t in TRAITS}
    )
    id: Optional[int] = None               # id_projeto no banco (mesma razao acima)


@dataclass
class Alocacao:
    analista: str
    nivel: str
    projeto: str
    horas: float
    custo: float
    receita: float
    id_analista: Optional[int] = None      # id no banco (so' pra' religar o resultado
    id_projeto: Optional[int] = None       # ao registro certo - nome nao e' unico)


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
    tempo_processamento_s: float = 0.0      # tempo de resolucao do solver CBC, em segundos
    taxa_ocupacao_equipe: float = 0.0       # soma(horas_alocadas)/soma(disponibilidade) * 100, entre os analistas da rodada


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
            f"demanda_teto_{j}",
        )

    # Eq 3 (piso, NOVA) - projeto aceito entrega de fato as horas contratadas,
    # nao so' evita ultrapassa-las. Combinada com a de cima: y[j]=1 forca
    # Sum_i x[i,j] == Hj; y[j]=0 forca Sum_i x[i,j] == 0.
    for j in J:
        prob += (
            pulp.lpSum(x[i, j] for i in I) >= projetos[j].horas * y[j],
            f"demanda_piso_{j}",
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

    # Eq 7 (generalizada por Njmin) - projeto aceito precisa ter pelo menos
    # Njmin analistas vinculados; Njmin=1 (default) reproduz o artigo.
    for j in J:
        prob += (
            pulp.lpSum(z[i, j] for i in I) >= projetos[j].min_analistas * y[j],
            f"min_analistas_{j}",
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

    # Eq 9 (cobertura conjunta) - para cada habilidade tecnica exigida pelo
    # projeto, basta que AO MENOS UM analista vinculado a atenda - nao
    # precisa ser o mesmo analista para todas as habilidades exigidas.
    # I_jk (analistas aptos) e' pre-computado a partir dos dados de entrada,
    # entao a restricao continua linear em z[i,j]. Se I_jk for vazio para
    # alguma habilidade exigida por j, lpSum(...) = 0 e a propria restricao
    # forca y[j] = 0 (projeto inviavel), sem tratamento especial.
    for j in J:
        for k in K:
            req = projetos[j].competencias_min.get(k, 0.0)
            if req <= 0:
                continue
            I_jk = [i for i in I if analistas[i].competencias.get(k, 0.0) >= req]
            prob += (
                pulp.lpSum(z[i, j] for i in I_jk) >= y[j],
                f"cobertura_habilidade_{j}_{k}",
            )

    # Eq 10 - analista ausente nao pode ser alocado
    for i in I:
        for j in J:
            prob += z[i, j] <= (0 if analistas[i].ausente else 1), f"ausencia_{i}_{j}"

    # Eq 11 - x[i,j] >= 0 ja garantido pelo lowBound la em cima

    t0 = time.perf_counter()
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    tempo_processamento_s = time.perf_counter() - t0
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
            tempo_processamento_s=round(tempo_processamento_s, 3),
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
                        id_analista=analistas[i].id,
                        id_projeto=projetos[j].id,
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

    # Taxa de ocupacao da equipe: soma das horas alocadas sobre soma da
    # disponibilidade de TODOS os analistas que participaram da rodada (nao
    # so' os que efetivamente receberam horas) - mede o quanto da capacidade
    # disponivel da equipe selecionada o modelo conseguiu aproveitar.
    disp_total = sum(r.disponibilidade for r in resumo_analistas)
    horas_total = sum(r.horas_alocadas for r in resumo_analistas)
    taxa_ocupacao_equipe = (horas_total / disp_total * 100) if disp_total > 0 else 0.0

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
        tempo_processamento_s=round(tempo_processamento_s, 3),
        taxa_ocupacao_equipe=round(taxa_ocupacao_equipe, 2),
    )


def _custo_minimo_estimado(
    elegiveis: List[Analista], horas_necessarias: float, njmin: int, njmax: int, h_min: float
) -> Optional[float]:
    # Heuristica gulosa (nao faz parte do modelo MILP, so' do diagnostico de
    # recusa): estima o custo da equipe mais barata possivel pra' cobrir
    # horas_necessarias, usando os analistas elegiveis de menor custo/hora
    # primeiro, ate' Njmax deles. E' uma aproximacao (nao reproduz o
    # branch-and-cut do solver), mas serve pra' distinguir "esse projeto e'
    # deficitario mesmo com a equipe mais barata" de "havia equipe lucrativa
    # disponivel, so' que as horas foram usadas em outro projeto".
    candidatos = sorted(elegiveis, key=lambda a: a.custo_hora)[:njmax]
    if len(candidatos) < njmin:
        return None
    custo = 0.0
    restante = horas_necessarias
    for a in candidatos:
        if restante <= 0:
            break
        horas = min(a.disponibilidade, restante)
        custo += horas * a.custo_hora
        restante -= horas
    if restante > 1e-6:
        return None
    return custo


def _diagnosticar_recusa(projeto: Projeto, analistas: List[Analista], h_min: float) -> str:
    # isso aqui e so pra mostrar um motivo pro usuario na tela de resultado,
    # nao faz parte do modelo (nao entra em nenhuma restricao do solver).
    # Habilidades tecnicas sao cobertura de EQUIPE (Eq 9): um analista e'
    # "elegivel" pra time sem precisar cobrir sozinho todas as habilidades.
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
        if a.disponibilidade < h_min:
            continue
        elegiveis.append(a)

    if not elegiveis:
        return ("nenhum analista atende simultaneamente a senioridade minima, o "
                "perfil comportamental exigidos pelo projeto e a disponibilidade "
                "minima (h_min).")

    faltando = [
        k for k, minimo in projeto.competencias_min.items()
        if minimo > 0 and not any(a.competencias.get(k, 0.0) >= minimo for a in elegiveis)
    ]
    if faltando:
        return ("nenhum analista elegivel (apto em senioridade, perfil "
                "comportamental e disponibilidade) atende ao nivel minimo exigido "
                "para a(s) habilidade(s) tecnica(s): " + ", ".join(map(str, faltando)) + ".")

    capacidade = sum(a.disponibilidade for a in elegiveis)
    if capacidade < projeto.horas:
        return ("a capacidade agregada de horas dos analistas elegiveis e menor que "
                "as horas contratadas do projeto.")
    if len(elegiveis) < projeto.min_analistas:
        return (f"apenas {len(elegiveis)} analista(s) elegivel(is), abaixo do minimo "
                f"de {projeto.min_analistas} exigido pelo projeto (Njmin).")

    # Distingue "o projeto e' deficitario mesmo com a equipe mais barata
    # possivel" (recusado mesmo sem nenhum outro projeto disputando horas) de
    # "havia equipe lucrativa disponivel, mas as horas foram usadas em outro
    # projeto que rende mais" (recusa por trade-off de fato).
    custo_estimado = _custo_minimo_estimado(
        elegiveis, projeto.horas, projeto.min_analistas, projeto.max_analistas, h_min
    )
    if custo_estimado is not None and custo_estimado > projeto.receita:
        return (
            f"mesmo com a equipe mais barata possivel entre os analistas elegiveis, "
            f"o custo estimado (R$ {custo_estimado:,.2f}) supera a receita do projeto "
            f"(R$ {projeto.receita:,.2f}) - aceitar reduziria o lucro liquido, entao o "
            f"modelo recusa mesmo sem nenhum outro projeto disputando essas horas."
        )
    return (
        "havia equipe elegivel e o projeto seria lucrativo isoladamente, mas as horas "
        "disponiveis dos analistas foram direcionadas a outros projetos aceitos que "
        "rendem mais lucro liquido por hora nesse cenario (trade-off de otimizacao)."
    )
