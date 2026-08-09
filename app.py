"""
Interface Streamlit do modulo de Sistema de Apoio a Decisao (SAD) para
alocacao de analistas em projetos de assessoria em regime de horas.

Implementa em Streamlit o fluxo de telas prototipado no Figma (secao 6.2.4.1
do pre-projeto de TCC): cadastro de analistas, cadastro de projetos,
parametros e execucao da otimizacao (PuLP/CBC) e apresentacao dos resultados,
conforme secao 6.2.4.2 (Implementacao em Streamlit).

Execucao:
    streamlit run app.py
"""

import uuid

import pandas as pd
import streamlit as st

from optimization import (
    NIVEIS,
    TRAITS,
    TRAIT_LABELS,
    Analista,
    Projeto,
    resolver_modelo,
)

st.set_page_config(
    page_title="Alocacao Otima de Analistas",
    page_icon="\U0001F4CA",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Estilo (paleta reaproveitada do prototipo de alta fidelidade em Figma)
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
      :root {
        --bg: #FAFAF9; --surface: #FFFFFF; --border: #E7E5E4;
        --text: #292524; --text-muted: #78716C;
        --accent: #F97316; --accent-hover: #EA580C; --accent-tint: #FFF0E6;
        --danger: #DC2626; --ok: #16A34A;
      }
      .sad-kicker {
        font-size: 12px; font-weight: 700; letter-spacing: 0.08em;
        text-transform: uppercase; color: var(--accent-hover); margin-bottom: 2px;
      }
      .sad-subtitle { font-size: 14px; color: var(--text-muted); max-width: 90ch; }
      .sad-card-kicker {
        font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
        text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px;
      }
      div[data-testid="stMetricValue"] { color: var(--accent-hover); }
      .stButton>button[kind="primary"] { background-color: var(--accent); border-color: var(--accent); }
      .stButton>button[kind="primary"]:hover { background-color: var(--accent-hover); border-color: var(--accent-hover); }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Dados de exemplo (fictícios, conforme secao 6.1.3 - "Uso de Dados Ficticios
# e Justificativa": parametros calibrados para representar o problema real
# sem pertencer a uma organizacao especifica)
# ---------------------------------------------------------------------------

def _dados_exemplo_analistas():
    return [
        {
            "id": str(uuid.uuid4()), "nome": "Ana Souza", "senioridade": "Senior",
            "custo_hora": 140.0, "disponibilidade": 160.0, "ausente": False,
            "competencias": pd.DataFrame(
                [{"Habilidade": "Tributario", "Nivel (0-100)": 85},
                 {"Habilidade": "Auditoria", "Nivel (0-100)": 90}]
            ),
            "big5": {"COM": 80, "COL": 60, "ORG": 75, "ADA": 55, "EST": 70},
        },
        {
            "id": str(uuid.uuid4()), "nome": "Bruno Lima", "senioridade": "Pleno",
            "custo_hora": 95.0, "disponibilidade": 150.0, "ausente": False,
            "competencias": pd.DataFrame(
                [{"Habilidade": "SAP", "Nivel (0-100)": 70},
                 {"Habilidade": "Power BI", "Nivel (0-100)": 80}]
            ),
            "big5": {"COM": 65, "COL": 70, "ORG": 60, "ADA": 80, "EST": 50},
        },
        {
            "id": str(uuid.uuid4()), "nome": "Camila Rocha", "senioridade": "Senior",
            "custo_hora": 130.0, "disponibilidade": 150.0, "ausente": False,
            "competencias": pd.DataFrame(
                [{"Habilidade": "Auditoria", "Nivel (0-100)": 95},
                 {"Habilidade": "SAP", "Nivel (0-100)": 65}]
            ),
            "big5": {"COM": 75, "COL": 55, "ORG": 85, "ADA": 60, "EST": 80},
        },
    ]


def _dados_exemplo_projetos():
    return [
        {
            "id": str(uuid.uuid4()), "nome": "Consultoria Fiscal", "receita": 90000.0,
            "horas": 240.0, "max_analistas": 3, "nivel_min": "Pleno",
            "competencias": pd.DataFrame(
                [{"Habilidade": "Tributario", "Nivel minimo (0-100)": 80},
                 {"Habilidade": "Compliance", "Nivel minimo (0-100)": 70}]
            ),
            "big5_min": {"COM": 50, "COL": 0, "ORG": 50, "ADA": 0, "EST": 0},
        },
        {
            "id": str(uuid.uuid4()), "nome": "Auditoria Interna", "receita": 60000.0,
            "horas": 160.0, "max_analistas": 2, "nivel_min": "Senior",
            "competencias": pd.DataFrame(
                [{"Habilidade": "Auditoria", "Nivel minimo (0-100)": 90},
                 {"Habilidade": "SAP", "Nivel minimo (0-100)": 60}]
            ),
            "big5_min": {"COM": 0, "COL": 0, "ORG": 50, "ADA": 0, "EST": 50},
        },
        {
            "id": str(uuid.uuid4()), "nome": "Implantacao ERP", "receita": 140000.0,
            "horas": 400.0, "max_analistas": 4, "nivel_min": "Junior",
            "competencias": pd.DataFrame(
                [{"Habilidade": "SAP", "Nivel minimo (0-100)": 85},
                 {"Habilidade": "Power BI", "Nivel minimo (0-100)": 75}]
            ),
            "big5_min": {"COM": 0, "COL": 50, "ORG": 0, "ADA": 50, "EST": 0},
        },
    ]


if "analistas" not in st.session_state:
    st.session_state.analistas = _dados_exemplo_analistas()
if "projetos" not in st.session_state:
    st.session_state.projetos = _dados_exemplo_projetos()
if "h_min" not in st.session_state:
    st.session_state.h_min = 20
if "resultado" not in st.session_state:
    st.session_state.resultado = None


# ---------------------------------------------------------------------------
# Cabecalho
# ---------------------------------------------------------------------------

st.markdown('<div class="sad-kicker">Sistema de Apoio a Decisao &middot; MILP</div>', unsafe_allow_html=True)
st.title("Alocacao Otima de Analistas")
st.markdown(
    '<p class="sad-subtitle">Cadastre analistas e projetos, execute o modelo de '
    "otimizacao (Programacao Linear Inteira Mista) e visualize a alocacao que "
    "maximiza o lucro liquido.</p>",
    unsafe_allow_html=True,
)
st.divider()


# ---------------------------------------------------------------------------
# Secao 01 - Analistas
# ---------------------------------------------------------------------------

st.subheader(f"01 · Analistas ({len(st.session_state.analistas)} cadastrados)")

for idx, a in enumerate(st.session_state.analistas):
    with st.container(border=True):
        col_head, col_del = st.columns([10, 1])
        col_head.markdown(f'<div class="sad-card-kicker">Analista {idx + 1}</div>', unsafe_allow_html=True)
        if col_del.button("Remover", key=f"del_analista_{a['id']}", use_container_width=True):
            st.session_state.analistas = [x for x in st.session_state.analistas if x["id"] != a["id"]]
            st.rerun()

        a["nome"] = st.text_input("Nome", value=a["nome"], key=f"nome_{a['id']}", placeholder="Ex.: Ana Souza")

        c1, c2, c3 = st.columns(3)
        a["senioridade"] = c1.selectbox(
            "Senioridade", options=list(NIVEIS.keys()),
            index=list(NIVEIS.keys()).index(a["senioridade"]), key=f"nivel_{a['id']}",
            help="Nivel de experiencia (Si). Comparado ao minimo exigido pelo projeto (Sjmin) na Equacao 8.",
        )
        a["custo_hora"] = c2.number_input(
            "Custo/h (R$)", min_value=0.0, value=float(a["custo_hora"]), step=5.0, key=f"custo_{a['id']}",
            help="Custo por hora do analista (Ci), usado na funcao objetivo (Equacao 1).",
        )
        a["disponibilidade"] = c3.number_input(
            "Disp. (h/mes)", min_value=0.0, value=float(a["disponibilidade"]), step=5.0, key=f"disp_{a['id']}",
            help="Disponibilidade de horas (Di), limite da Equacao 2.",
        )
        a["ausente"] = st.checkbox(
            "Ausencia programada no periodo (Ai)", value=a["ausente"], key=f"ausente_{a['id']}",
            help="Se marcado, o analista nao pode ser vinculado a nenhum projeto (Equacao 10).",
        )

        st.caption("Proficiencia tecnica (SKILLik, escala 0-100)")
        a["competencias"] = st.data_editor(
            a["competencias"], num_rows="dynamic", key=f"skills_{a['id']}",
            use_container_width=True, hide_index=True,
        )

        st.caption("Perfil comportamental Big Five (0-100)")
        cols = st.columns(5)
        for i, trait in enumerate(TRAITS):
            a["big5"][trait] = cols[i].slider(
                trait, min_value=0, max_value=100, value=int(a["big5"].get(trait, 50)),
                key=f"big5_{trait}_{a['id']}", help=TRAIT_LABELS[trait],
            )

if st.button("+ Adicionar analista"):
    st.session_state.analistas.append(
        {
            "id": str(uuid.uuid4()), "nome": "", "senioridade": "Pleno",
            "custo_hora": 0.0, "disponibilidade": 0.0, "ausente": False,
            "competencias": pd.DataFrame(columns=["Habilidade", "Nivel (0-100)"]),
            "big5": {t: 50 for t in TRAITS},
        }
    )
    st.rerun()

st.divider()


# ---------------------------------------------------------------------------
# Secao 02 - Projetos
# ---------------------------------------------------------------------------

st.subheader(f"02 · Projetos ({len(st.session_state.projetos)} cadastrados)")

for idx, p in enumerate(st.session_state.projetos):
    with st.container(border=True):
        col_head, col_del = st.columns([10, 1])
        col_head.markdown(f'<div class="sad-card-kicker">Projeto {idx + 1}</div>', unsafe_allow_html=True)
        if col_del.button("Remover", key=f"del_projeto_{p['id']}", use_container_width=True):
            st.session_state.projetos = [x for x in st.session_state.projetos if x["id"] != p["id"]]
            st.rerun()

        p["nome"] = st.text_input(
            "Nome do projeto", value=p["nome"], key=f"pnome_{p['id']}", placeholder="Ex.: Consultoria Fiscal",
        )

        c1, c2, c3 = st.columns(3)
        p["receita"] = c1.number_input(
            "Receita esperada (R$)", min_value=0.0, value=float(p["receita"]), step=1000.0, key=f"receita_{p['id']}",
            help="Receita do projeto (Rj), usada na funcao objetivo (Equacao 1).",
        )
        p["horas"] = c2.number_input(
            "Horas contratadas", min_value=0.0, value=float(p["horas"]), step=10.0, key=f"horas_{p['id']}",
            help="Horas contratadas (Hj), limite da Equacao 3.",
        )
        p["max_analistas"] = c3.number_input(
            "N. max. analistas", min_value=1, value=int(p["max_analistas"]), step=1, key=f"maxan_{p['id']}",
            help="Numero maximo de analistas (Njmax), limite da Equacao 6. Todo projeto "
                 "aceito tem no minimo um analista responsavel (Equacao 7).",
        )

        p["nivel_min"] = st.selectbox(
            "Nivel tecnico minimo", options=list(NIVEIS.keys()),
            index=list(NIVEIS.keys()).index(p["nivel_min"]), key=f"pnivel_{p['id']}",
            help="Senioridade minima exigida (Sjmin), comparada na Equacao 8 (Junior < Pleno < Senior).",
        )

        st.caption("Competencias tecnicas exigidas (REQjk, escala 0-100; 0 = nao exigida)")
        p["competencias"] = st.data_editor(
            p["competencias"], num_rows="dynamic", key=f"pskills_{p['id']}",
            use_container_width=True, hide_index=True,
        )

        st.caption("Perfil comportamental minimo exigido (0-100; 0 = nao exigido) – restricoes analogas a Equacao 8")
        cols = st.columns(5)
        for i, trait in enumerate(TRAITS):
            p["big5_min"][trait] = cols[i].slider(
                trait, min_value=0, max_value=100, value=int(p["big5_min"].get(trait, 0)),
                key=f"pbig5_{trait}_{p['id']}", help=TRAIT_LABELS[trait],
            )

if st.button("+ Adicionar projeto"):
    st.session_state.projetos.append(
        {
            "id": str(uuid.uuid4()), "nome": "", "receita": 0.0, "horas": 0.0,
            "max_analistas": 1, "nivel_min": "Pleno",
            "competencias": pd.DataFrame(columns=["Habilidade", "Nivel minimo (0-100)"]),
            "big5_min": {t: 0 for t in TRAITS},
        }
    )
    st.rerun()

st.divider()


# ---------------------------------------------------------------------------
# Secao 03 - Parametros e execucao
# ---------------------------------------------------------------------------

st.subheader("03 · Parametros e execucao")

with st.container(border=True):
    st.session_state.h_min = st.number_input(
        "Horas minimas por alocacao (h_min)", min_value=0, value=int(st.session_state.h_min), step=5,
        help="Nenhum analista recebe menos que esse numero de horas em um projeto "
             "quando vinculado a ele - evita fragmentacoes pouco relevantes na "
             "pratica (restricao big-M, Equacao 5).",
    )

    def _analistas_validos():
        erros = []
        for a in st.session_state.analistas:
            if not a["nome"].strip():
                erros.append("Ha analistas sem nome.")
            if a["custo_hora"] <= 0:
                erros.append(f"Custo/h de '{a['nome'] or 'analista sem nome'}' deve ser maior que zero.")
            if a["disponibilidade"] <= 0:
                erros.append(f"Disponibilidade de '{a['nome'] or 'analista sem nome'}' deve ser maior que zero.")
        return erros

    def _projetos_validos():
        erros = []
        for p in st.session_state.projetos:
            if not p["nome"].strip():
                erros.append("Ha projetos sem nome.")
            if p["receita"] <= 0:
                erros.append(f"Receita de '{p['nome'] or 'projeto sem nome'}' deve ser maior que zero.")
            if p["horas"] <= 0:
                erros.append(f"Horas de '{p['nome'] or 'projeto sem nome'}' devem ser maiores que zero.")
        return erros

    erros = []
    if not st.session_state.analistas or not st.session_state.projetos:
        erros.append("Cadastre ao menos um projeto e um analista para executar o modelo.")
    erros += _analistas_validos()
    erros += _projetos_validos()

    if erros:
        for e in set(erros):
            st.error(e)

    if st.button("Executar otimizacao", type="primary", disabled=bool(erros)):
        analistas_modelo = [
            Analista(
                nome=a["nome"],
                senioridade=a["senioridade"],
                custo_hora=a["custo_hora"],
                disponibilidade=a["disponibilidade"],
                ausente=a["ausente"],
                competencias={
                    str(r["Habilidade"]): float(r["Nivel (0-100)"])
                    for _, r in a["competencias"].dropna().iterrows()
                    if str(r.get("Habilidade", "")).strip()
                },
                big5=dict(a["big5"]),
            )
            for a in st.session_state.analistas
        ]
        projetos_modelo = [
            Projeto(
                nome=p["nome"],
                receita=p["receita"],
                horas=p["horas"],
                nivel_min=p["nivel_min"],
                max_analistas=int(p["max_analistas"]),
                competencias_min={
                    str(r["Habilidade"]): float(r["Nivel minimo (0-100)"])
                    for _, r in p["competencias"].dropna().iterrows()
                    if str(r.get("Habilidade", "")).strip()
                },
                big5_min=dict(p["big5_min"]),
            )
            for p in st.session_state.projetos
        ]
        with st.spinner("Resolvendo o modelo MILP (PuLP/CBC)..."):
            st.session_state.resultado = resolver_modelo(
                analistas_modelo, projetos_modelo, st.session_state.h_min
            )

st.divider()


# ---------------------------------------------------------------------------
# Secao 04 - Resultado
# ---------------------------------------------------------------------------

resultado = st.session_state.resultado

if resultado is not None:
    st.subheader("04 · Resultado")

    if not resultado.viavel:
        st.error(f"O modelo nao encontrou solucao viavel (status do solver: {resultado.status}).")
    else:
        st.success("Solucao encontrada.")

        n_projetos = len(st.session_state.projetos)
        margem = (resultado.lucro_liquido / resultado.receita_total * 100) if resultado.receita_total else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Lucro liquido", f"R$ {resultado.lucro_liquido:,.2f}", f"{margem:.1f}% da receita")
        k2.metric("Receita total", f"R$ {resultado.receita_total:,.2f}")
        k3.metric("Custo total", f"R$ {resultado.custo_total:,.2f}")
        k4.metric("Projetos aceitos", f"{len(resultado.aceitos)} / {n_projetos}")

        st.markdown('<div class="sad-card-kicker">Distribuicao de horas por analista</div>', unsafe_allow_html=True)
        for r in resultado.resumo_analistas:
            st.write(f"**{r.nome}** — {r.horas_alocadas:.1f}h de {r.disponibilidade:.1f}h disponiveis")
            st.progress(r.utilizacao)

        st.markdown('<div class="sad-card-kicker">Alocacao detalhada</div>', unsafe_allow_html=True)
        if resultado.alocacoes:
            df = pd.DataFrame(
                [
                    {
                        "Analista": a.analista, "Nivel": a.nivel, "Projeto": a.projeto,
                        "Horas": a.horas, "Custo": f"R$ {a.custo:,.2f}",
                        "Receita gerada": f"R$ {a.receita:,.2f}",
                    }
                    for a in resultado.alocacoes
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhuma alocacao realizada.")

        st.markdown('<div class="sad-card-kicker">Projetos aceitos e recusados (y[j])</div>', unsafe_allow_html=True)
        for nome in resultado.aceitos:
            st.markdown(f"\U0001F7E2 **Aceito** — {nome}")
        for nome, motivo in resultado.recusados:
            st.markdown(f"⚪ **Recusado** — {nome}")
            st.caption(motivo)

    st.divider()

    # -----------------------------------------------------------------
    # Secao 05 - Exportacao do relatorio
    # -----------------------------------------------------------------

    st.subheader("05 · Exportacao do relatorio")

    def _montar_relatorio_txt() -> str:
        linhas = []
        linhas.append("RELATORIO DE ALOCACAO OTIMA DE ANALISTAS")
        linhas.append("Sistema de Apoio a Decisao - Programacao Linear Inteira Mista (PuLP/CBC)")
        linhas.append("=" * 60)
        linhas.append(f"Parametro h_min (horas minimas por alocacao): {st.session_state.h_min}h")
        linhas.append(
            f"Projetos cadastrados: {len(st.session_state.projetos)} | "
            f"Analistas cadastrados: {len(st.session_state.analistas)}"
        )
        linhas.append("")
        linhas.append("1. RESULTADO GERAL")
        linhas.append("-" * 60)
        if not resultado.viavel:
            linhas.append(f"Modelo infactivel (status: {resultado.status}).")
        else:
            linhas.append(f"Lucro liquido total: R$ {resultado.lucro_liquido:,.2f}")
            linhas.append(f"Receita total: R$ {resultado.receita_total:,.2f}")
            linhas.append(f"Custo total alocado: R$ {resultado.custo_total:,.2f}")
            linhas.append(f"Projetos aceitos: {len(resultado.aceitos)} de {len(st.session_state.projetos)}")
            linhas.append("")
            linhas.append("2. ALOCACAO DETALHADA (analista x projeto x horas)")
            linhas.append("-" * 60)
            if resultado.alocacoes:
                for a in resultado.alocacoes:
                    linhas.append(
                        f"- {a.analista} ({a.nivel}) -> {a.projeto}: {a.horas:.1f}h, "
                        f"custo R$ {a.custo:,.2f}, receita gerada R$ {a.receita:,.2f}"
                    )
            else:
                linhas.append("(nenhuma alocacao realizada)")
            linhas.append("")
            linhas.append("3. PROJETOS ACEITOS E RECUSADOS (variavel y[j])")
            linhas.append("-" * 60)
            for nome in resultado.aceitos:
                linhas.append(f"[ACEITO] {nome}")
            for nome, motivo in resultado.recusados:
                linhas.append(f"[RECUSADO] {nome} - motivo: {motivo}")
            linhas.append("")
            linhas.append("4. RESUMO POR ANALISTA (utilizacao da disponibilidade)")
            linhas.append("-" * 60)
            for r in resultado.resumo_analistas:
                linhas.append(
                    f"- {r.nome}: {r.horas_alocadas:.1f}h alocadas de {r.disponibilidade:.1f}h "
                    f"disponiveis ({r.utilizacao * 100:.1f}% de utilizacao)"
                )
        linhas.append("")
        linhas.append("5. NOTA METODOLOGICA")
        linhas.append("-" * 60)
        linhas.append(
            "Resultado obtido pela resolucao exata do modelo de Programacao Linear "
            "Inteira Mista (Equacoes 1 a 11) via solver CBC (branch-and-cut), "
            "atraves da biblioteca PuLP."
        )
        return "\n".join(linhas)

    with st.container(border=True):
        st.markdown('<div class="sad-card-kicker">Relatorio completo</div>', unsafe_allow_html=True)
        st.caption(
            "O relatorio reune os parametros do modelo, o resultado da otimizacao "
            "(lucro liquido, receita e custo), a alocacao detalhada de cada analista "
            "por projeto e a justificativa de aceitacao ou recusa de cada projeto "
            "(variavel y[j])."
        )
        st.download_button(
            "Baixar relatorio (.txt)",
            data=_montar_relatorio_txt(),
            file_name="relatorio-alocacao-analistas.txt",
            mime="text/plain",
        )
