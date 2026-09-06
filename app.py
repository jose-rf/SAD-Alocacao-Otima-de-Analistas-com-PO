# Interface do SAD (Streamlit) - roda com: streamlit run app.py
#
# Persistencia em SQLite (db.py, 7 tabelas: analistas, projetos, habilidades,
# analista_habilidade, projeto_habilidade_requerida, execucoes, alocacoes).
# Cada edicao de campo grava direto no banco (sem botao "salvar" separado) -
# o script inteiro roda de novo a cada interacao, e os dados sao sempre lidos
# do banco no topo do script, entao a fonte da verdade e' sempre o SQLite.
#
# Navegacao por menu lateral (5 paginas) + fluxo candidata->confirmada de
# execucoes (ver db.py e README) para persistir horas ja comprometidas por
# analista entre execucoes, dentro do mesmo periodo de referencia (mes/ano).

import calendar
import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import date

import pandas as pd
import streamlit as st

import db
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

# paleta usada no protótipo do Figma
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

db.init_db()
with db.get_connection() as _conn:
    db.seed_dados_exemplo(_conn)


# ── Helpers de leitura (linha SQLite -> dict de trabalho) ───────────────────

def _analista_dict(row):
    return {
        "id": row["id_analista"], "nome": row["nome"], "cpf": row["cpf"],
        "senioridade": row["senioridade"],
        "custo_hora": row["custo_hora"], "disponibilidade": row["disponibilidade"],
        "ausente": bool(row["ausente"]),
        "big5": {"COM": row["com"], "COL": row["col"], "ORG": row["org"],
                  "ADA": row["ada"], "EST": row["est"]},
    }


def _projeto_dict(row):
    return {
        "id": row["id_projeto"], "nome": row["nome"], "receita": row["receita"],
        "horas": row["horas"], "nivel_min": row["nivel_min"],
        "max_analistas": row["max_analistas"], "min_analistas": row["min_analistas"],
        "big5_min": {"COM": row["com_min"], "COL": row["col_min"], "ORG": row["org_min"],
                      "ADA": row["ada_min"], "EST": row["est_min"]},
    }


MESES = ["Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho", "Julho",
          "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

if "resultado" not in st.session_state:
    st.session_state.resultado = None
if "h_min" not in st.session_state:
    st.session_state.h_min = 20
if "ultima_execucao_id" not in st.session_state:
    st.session_state.ultima_execucao_id = None
if "periodo_mes" not in st.session_state:
    st.session_state.periodo_mes = date.today().month
if "periodo_ano" not in st.session_state:
    st.session_state.periodo_ano = date.today().year


# ===== Sidebar: periodo de referencia + navegacao =====

st.sidebar.markdown("### Periodo de referencia")
st.sidebar.caption(
    "Usado para o teto de disponibilidade por calendario e para calcular "
    "quantas horas de cada analista ja estao comprometidas em execucoes "
    "confirmadas neste periodo."
)
c_mes, c_ano = st.sidebar.columns(2)
st.session_state.periodo_mes = c_mes.selectbox(
    "Mes", options=list(range(1, 13)), format_func=lambda m: MESES[m - 1],
    index=st.session_state.periodo_mes - 1, key="sel_periodo_mes",
)
st.session_state.periodo_ano = c_ano.number_input(
    "Ano", min_value=2000, max_value=2100, value=int(st.session_state.periodo_ano),
    step=1, key="sel_periodo_ano",
)
periodo_mes = st.session_state.periodo_mes
periodo_ano = st.session_state.periodo_ano
periodo_referencia = f"{periodo_ano:04d}-{periodo_mes:02d}"
dias_no_mes = calendar.monthrange(periodo_ano, periodo_mes)[1]
teto_horas_calendario = dias_no_mes * 24

st.sidebar.divider()

PAGINAS = [
    "Cadastro de Analistas",
    "Cadastro de Projetos",
    "Cadastro de Habilidades Tecnicas",
    "Geracao da Alocacao",
    "Dashboard de Resultados",
]
pagina = st.sidebar.radio("Navegacao", PAGINAS, key="pagina_atual")


# cabecalho
st.markdown('<div class="sad-kicker">Sistema de Apoio a Decisao &middot; MILP</div>', unsafe_allow_html=True)
st.title("Alocacao Otima de Analistas")
st.markdown(
    '<p class="sad-subtitle">Cadastre analistas e projetos, execute o modelo de '
    "otimizacao (Programacao Linear Inteira Mista) e visualize a alocacao que "
    "maximiza o lucro liquido.</p>",
    unsafe_allow_html=True,
)
st.caption(f"Pagina atual: **{pagina}**  ·  Periodo de referencia: **{MESES[periodo_mes - 1]}/{periodo_ano}**")
st.divider()


# =====================================================================
# Pagina 1 · Cadastro de Analistas
# =====================================================================

if pagina == "Cadastro de Analistas":
    with db.get_connection() as conn:
        analistas = [_analista_dict(r) for r in db.list_analistas(conn)]

    st.subheader(f"Analistas ({len(analistas)} cadastrados)")

    for idx, a in enumerate(analistas):
        with st.container(border=True):
            col_head, col_del = st.columns([10, 1])
            col_head.markdown(f'<div class="sad-card-kicker">Analista {idx + 1}</div>', unsafe_allow_html=True)
            if col_del.button("Remover", key=f"del_analista_{a['id']}", use_container_width=True):
                with db.get_connection() as conn:
                    db.delete_analista(conn, a["id"])
                st.rerun()

            c_nome, c_cpf = st.columns(2)
            nome = c_nome.text_input("Nome", value=a["nome"], key=f"nome_{a['id']}", placeholder="Ex.: Ana Souza")
            cpf = c_cpf.text_input(
                "CPF", value=a["cpf"], key=f"cpf_{a['id']}", placeholder="000.000.000-00",
                help="Chave do analista. Formato 000.000.000-00, unico no cadastro.",
            )
            cpf_ok = (not cpf.strip()) or db.cpf_valido(cpf)
            if not cpf_ok:
                st.error("CPF em formato invalido. Use 000.000.000-00.")

            c1, c2, c3 = st.columns(3)
            senioridade = c1.selectbox(
                "Senioridade", options=list(NIVEIS.keys()),
                index=list(NIVEIS.keys()).index(a["senioridade"]), key=f"nivel_{a['id']}",
                help="Nivel de experiencia (Si). Comparado ao minimo exigido pelo projeto (Sjmin) na Equacao 8.",
            )
            custo_hora = c2.number_input(
                "Custo/h (R$)", min_value=0.0, value=float(a["custo_hora"]), step=5.0, key=f"custo_{a['id']}",
                help="Custo por hora do analista (Ci), usado na funcao objetivo (Equacao 1).",
            )
            disponibilidade = c3.number_input(
                "Disp. (h/mes)", min_value=0.0, max_value=float(teto_horas_calendario),
                value=min(float(a["disponibilidade"]), float(teto_horas_calendario)), step=5.0, key=f"disp_{a['id']}",
                help=(
                    f"Disponibilidade de horas (Di), limite da Equacao 2. Teto calculado pelo "
                    f"calendario do periodo de referencia ({MESES[periodo_mes - 1]}/{periodo_ano}): "
                    f"{dias_no_mes} dias x 24h = {teto_horas_calendario:.0f}h. Esse teto e' "
                    f"fisicamente possivel, mas folgado para um regime de trabalho real - "
                    f"para um teto mais realista de jornada CLT mensal, considere usar algo "
                    f"em torno de 220h/mes como referencia pratica."
                ),
            )
            ausente = st.checkbox(
                "Ausencia programada no periodo (Ai)", value=a["ausente"], key=f"ausente_{a['id']}",
                help="Se marcado, o analista nao pode ser vinculado a nenhum projeto (Equacao 10).",
            )

            st.caption(
                "Perfil comportamental Big Five (0-100). Competencias tecnicas sao "
                "cadastradas na pagina **Cadastro de Habilidades Tecnicas**."
            )
            cols = st.columns(5)
            big5 = dict(a["big5"])
            for i, trait in enumerate(TRAITS):
                big5[trait] = cols[i].slider(
                    TRAIT_LABELS[trait], min_value=0, max_value=100, value=int(a["big5"].get(trait, 50)),
                    key=f"big5_{trait}_{a['id']}", help=f"Sigla interna: {trait}",
                )

            if cpf_ok:
                try:
                    with db.get_connection() as conn:
                        db.update_analista(conn, a["id"], {
                            "nome": nome, "cpf": cpf.strip(),
                            "senioridade": senioridade, "custo_hora": custo_hora,
                            "disponibilidade": disponibilidade, "ausente": int(ausente),
                            "com": big5["COM"], "col": big5["COL"], "org": big5["ORG"],
                            "ada": big5["ADA"], "est": big5["EST"],
                        })
                except sqlite3.IntegrityError:
                    st.error(f"CPF '{cpf}' ja esta cadastrado para outro analista.")

    if st.button("+ Adicionar analista"):
        with db.get_connection() as conn:
            db.insert_analista(conn, {
                "nome": "", "cpf": "", "senioridade": "Pleno", "custo_hora": 0.0, "disponibilidade": 0.0,
                "ausente": 0, "com": 50, "col": 50, "org": 50, "ada": 50, "est": 50,
            })
        st.rerun()


# =====================================================================
# Pagina 2 · Cadastro de Projetos
# =====================================================================

elif pagina == "Cadastro de Projetos":
    with db.get_connection() as conn:
        projetos = [_projeto_dict(r) for r in db.list_projetos(conn)]

    st.subheader(f"Projetos ({len(projetos)} cadastrados)")

    for idx, p in enumerate(projetos):
        with st.container(border=True):
            col_head, col_del = st.columns([10, 1])
            col_head.markdown(f'<div class="sad-card-kicker">Projeto {idx + 1}</div>', unsafe_allow_html=True)
            if col_del.button("Remover", key=f"del_projeto_{p['id']}", use_container_width=True):
                with db.get_connection() as conn:
                    db.delete_projeto(conn, p["id"])
                st.rerun()

            nome = st.text_input(
                "Nome do projeto", value=p["nome"], key=f"pnome_{p['id']}", placeholder="Ex.: Consultoria Fiscal",
            )

            c1, c2, c3, c4 = st.columns(4)
            receita = c1.number_input(
                "Receita esperada (R$)", min_value=0.0, value=float(p["receita"]), step=1000.0, key=f"receita_{p['id']}",
                help="Receita do projeto (Rj), usada na funcao objetivo (Equacao 1).",
            )
            horas = c2.number_input(
                "Horas contratadas", min_value=0.0, value=float(p["horas"]), step=10.0, key=f"horas_{p['id']}",
                help="Horas contratadas (Hj). Com o projeto aceito (yj=1), a equipe deve "
                     "entregar exatamente Hj horas - nem mais, nem menos (Equacao 3).",
            )
            max_analistas = c3.number_input(
                "N. max. analistas (Njmax)", min_value=1, value=int(p["max_analistas"]), step=1, key=f"maxan_{p['id']}",
                help="Numero maximo de analistas vinculados ao projeto (Equacao 6).",
            )
            min_analistas = c4.number_input(
                "N. min. analistas (Njmin)", min_value=1, max_value=int(max_analistas),
                value=min(int(p["min_analistas"]), int(max_analistas)), step=1, key=f"minan_{p['id']}",
                help="Numero minimo de analistas vinculados quando o projeto e' aceito "
                     "(Equacao 7 generalizada). Default = 1.",
            )

            nivel_min = st.selectbox(
                "Nivel tecnico minimo", options=list(NIVEIS.keys()),
                index=list(NIVEIS.keys()).index(p["nivel_min"]), key=f"pnivel_{p['id']}",
                help="Senioridade minima exigida (Sjmin), comparada na Equacao 8 (Junior < Pleno < Senior).",
            )

            st.caption(
                "Competencias tecnicas exigidas (REQjk) sao cadastradas na pagina "
                "**Cadastro de Habilidades Tecnicas**."
            )
            st.caption("Perfil comportamental minimo exigido (0-100; 0 = nao exigido) – restricoes analogas a Equacao 8")
            cols = st.columns(5)
            big5_min = dict(p["big5_min"])
            for i, trait in enumerate(TRAITS):
                big5_min[trait] = cols[i].slider(
                    TRAIT_LABELS[trait], min_value=0, max_value=100, value=int(p["big5_min"].get(trait, 0)),
                    key=f"pbig5_{trait}_{p['id']}", help=f"Sigla interna: {trait}",
                )

            with db.get_connection() as conn:
                db.update_projeto(conn, p["id"], {
                    "nome": nome, "receita": receita, "horas": horas, "nivel_min": nivel_min,
                    "max_analistas": int(max_analistas), "min_analistas": int(min_analistas),
                    "com_min": big5_min["COM"], "col_min": big5_min["COL"], "org_min": big5_min["ORG"],
                    "ada_min": big5_min["ADA"], "est_min": big5_min["EST"],
                })

    if st.button("+ Adicionar projeto"):
        with db.get_connection() as conn:
            db.insert_projeto(conn, {
                "nome": "", "receita": 0.0, "horas": 0.0, "nivel_min": "Pleno",
                "max_analistas": 1, "min_analistas": 1,
                "com_min": 0, "col_min": 0, "org_min": 0, "ada_min": 0, "est_min": 0,
            })
        st.rerun()


# =====================================================================
# Pagina 3 · Cadastro de Habilidades Tecnicas
# =====================================================================

elif pagina == "Cadastro de Habilidades Tecnicas":
    with db.get_connection() as conn:
        analistas = [_analista_dict(r) for r in db.list_analistas(conn)]
        projetos = [_projeto_dict(r) for r in db.list_projetos(conn)]

    st.subheader("Catalogo de habilidades tecnicas")
    st.caption(
        "Catalogo global de habilidades tecnicas, reutilizado tanto na "
        "proficiencia dos analistas (SKILLik) quanto nas exigencias dos "
        "projetos (REQjk)."
    )

    with st.container(border=True):
        with db.get_connection() as conn:
            habilidades = db.list_habilidades(conn)

        if habilidades:
            for h in habilidades:
                hc1, hc2, hc3 = st.columns([6, 2, 1])
                novo_nome = hc1.text_input(
                    "Nome da habilidade", value=h["nome"], key=f"hab_nome_{h['id_habilidade']}",
                    label_visibility="collapsed",
                )
                if novo_nome != h["nome"] and hc2.button("Renomear", key=f"hab_ren_{h['id_habilidade']}"):
                    try:
                        with db.get_connection() as conn:
                            db.rename_habilidade(conn, h["id_habilidade"], novo_nome)
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                if hc3.button("✕", key=f"hab_del_{h['id_habilidade']}", help="Remover habilidade do catalogo"):
                    with db.get_connection() as conn:
                        db.delete_habilidade(conn, h["id_habilidade"])
                    st.rerun()
        else:
            st.caption("Nenhuma habilidade cadastrada ainda.")

        nova_habilidade = st.text_input("+ Nova habilidade", key="nova_habilidade", placeholder="Ex.: Python")
        if st.button("Adicionar ao catalogo", key="btn_add_habilidade"):
            try:
                with db.get_connection() as conn:
                    db.add_habilidade(conn, nova_habilidade)
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    aba_analistas, aba_projetos = st.tabs([
        "Proficiencia dos analistas (SKILLik)",
        "Exigencia dos projetos (REQjk)",
    ])

    with aba_analistas:
        if not habilidades:
            st.caption("Cadastre ao menos uma habilidade no catalogo para atribuir proficiencias.")
        elif not analistas:
            st.caption("Cadastre ao menos um analista para atribuir proficiencias.")
        else:
            nomes_analistas = [a["nome"] or f"(sem nome, id {a['id']})" for a in analistas]
            idx_sel = st.selectbox(
                "Analista", options=range(len(analistas)),
                format_func=lambda i: nomes_analistas[i], key="skill_analista_sel",
            )
            analista_sel = analistas[idx_sel]
            with db.get_connection() as conn:
                niveis = db.get_niveis_analista(conn, analista_sel["id"])
            for h in habilidades:
                nivel_atual = niveis.get(h["id_habilidade"], 0)
                nivel = st.slider(
                    h["nome"], min_value=0, max_value=100, value=int(nivel_atual),
                    key=f"skill_{analista_sel['id']}_{h['id_habilidade']}",
                )
                if nivel != nivel_atual:
                    with db.get_connection() as conn:
                        db.set_nivel_analista(conn, analista_sel["id"], h["id_habilidade"], nivel)

    with aba_projetos:
        if not habilidades:
            st.caption("Cadastre ao menos uma habilidade no catalogo para definir exigencias.")
        elif not projetos:
            st.caption("Cadastre ao menos um projeto para definir exigencias.")
        else:
            st.caption(
                "Uma habilidade com REQjk = 0 nao entra na restricao de cobertura "
                "(Equacao 9) - equivale a 'nao exigida'."
            )
            nomes_projetos = [p["nome"] or f"(sem nome, id {p['id']})" for p in projetos]
            idx_sel = st.selectbox(
                "Projeto", options=range(len(projetos)),
                format_func=lambda i: nomes_projetos[i], key="req_projeto_sel",
            )
            projeto_sel = projetos[idx_sel]
            with db.get_connection() as conn:
                reqs = db.get_requisitos_projeto(conn, projeto_sel["id"])
            for h in habilidades:
                req_atual = reqs.get(h["id_habilidade"], 0)
                req = st.slider(
                    h["nome"], min_value=0, max_value=100, value=int(req_atual),
                    key=f"req_{projeto_sel['id']}_{h['id_habilidade']}",
                )
                if req != req_atual:
                    with db.get_connection() as conn:
                        db.set_requisito_projeto(conn, projeto_sel["id"], h["id_habilidade"], req)


# =====================================================================
# Pagina 4 · Geracao da Alocacao
# =====================================================================

elif pagina == "Geracao da Alocacao":
    with db.get_connection() as conn:
        analistas = [_analista_dict(r) for r in db.list_analistas(conn)]
        projetos = [_projeto_dict(r) for r in db.list_projetos(conn)]
        niveis_por_analista = {a["id"]: db.get_niveis_analista(conn, a["id"]) for a in analistas}
        reqs_por_projeto = {p["id"]: db.get_requisitos_projeto(conn, p["id"]) for p in projetos}
        horas_comprometidas = {
            a["id"]: db.get_horas_comprometidas(conn, a["id"], periodo_referencia) for a in analistas
        }

    st.subheader("Parametros e selecao do escopo da rodada")

    with st.container(border=True):
        st.session_state.h_min = st.number_input(
            "Horas minimas por alocacao (h_min)", min_value=0, value=int(st.session_state.h_min), step=5,
            help="Nenhum analista recebe menos que esse numero de horas em um projeto "
                 "quando vinculado a ele - evita fragmentacoes pouco relevantes na "
                 "pratica (restricao big-M, Equacao 5).",
        )

        st.caption(
            "Selecione o subconjunto de analistas e projetos considerados nesta "
            "rodada de otimizacao (por default, todo o cadastro)."
        )
        c_a, c_p = st.columns(2)
        ids_analistas_sel = c_a.multiselect(
            "Analistas nesta rodada", options=[a["id"] for a in analistas],
            default=[a["id"] for a in analistas],
            format_func=lambda i: next(a["nome"] or f"(id {i})" for a in analistas if a["id"] == i),
        )
        ids_projetos_sel = c_p.multiselect(
            "Projetos nesta rodada", options=[p["id"] for p in projetos],
            default=[p["id"] for p in projetos],
            format_func=lambda i: next(p["nome"] or f"(id {i})" for p in projetos if p["id"] == i),
        )

        analistas_sel = [a for a in analistas if a["id"] in ids_analistas_sel]
        projetos_sel = [p for p in projetos if p["id"] in ids_projetos_sel]

        if any(horas_comprometidas.get(a["id"], 0) > 0 for a in analistas_sel):
            st.markdown('<div class="sad-card-kicker">Disponibilidade efetiva neste periodo</div>', unsafe_allow_html=True)
            for a in analistas_sel:
                comprometidas = horas_comprometidas.get(a["id"], 0)
                if comprometidas > 0:
                    efetiva = max(0.0, a["disponibilidade"] - comprometidas)
                    st.caption(
                        f"**{a['nome']}**: {a['disponibilidade']:.1f}h nominal − "
                        f"{comprometidas:.1f}h ja' comprometidas em execucoes confirmadas "
                        f"de {MESES[periodo_mes - 1]}/{periodo_ano} = {efetiva:.1f}h efetivas nesta rodada."
                    )

        def _analistas_validos():
            erros = []
            for a in analistas_sel:
                if not a["nome"].strip():
                    erros.append("Ha analistas sem nome.")
                if not a["cpf"].strip() or not db.cpf_valido(a["cpf"]):
                    erros.append(f"CPF de '{a['nome'] or 'analista sem nome'}' esta ausente ou invalido.")
                if a["custo_hora"] <= 0:
                    erros.append(f"Custo/h de '{a['nome'] or 'analista sem nome'}' deve ser maior que zero.")
                if a["disponibilidade"] <= 0:
                    erros.append(f"Disponibilidade de '{a['nome'] or 'analista sem nome'}' deve ser maior que zero.")
            return erros

        def _projetos_validos():
            erros = []
            for p in projetos_sel:
                if not p["nome"].strip():
                    erros.append("Ha projetos sem nome.")
                if p["receita"] <= 0:
                    erros.append(f"Receita de '{p['nome'] or 'projeto sem nome'}' deve ser maior que zero.")
                if p["horas"] <= 0:
                    erros.append(f"Horas de '{p['nome'] or 'projeto sem nome'}' devem ser maiores que zero.")
                if not (1 <= p["min_analistas"] <= p["max_analistas"]):
                    erros.append(
                        f"Njmin de '{p['nome'] or 'projeto sem nome'}' deve satisfazer "
                        f"1 <= Njmin ({p['min_analistas']}) <= Njmax ({p['max_analistas']})."
                    )
            return erros

        erros = []
        if not analistas_sel or not projetos_sel:
            erros.append("Selecione ao menos um projeto e um analista para executar o modelo.")
        erros += _analistas_validos()
        erros += _projetos_validos()

        if erros:
            for e in set(erros):
                st.error(e)

        analistas_modelo = [
            Analista(
                nome=a["nome"], senioridade=a["senioridade"], custo_hora=a["custo_hora"],
                disponibilidade=max(0.0, a["disponibilidade"] - horas_comprometidas.get(a["id"], 0)),
                ausente=a["ausente"], competencias=dict(niveis_por_analista.get(a["id"], {})), big5=dict(a["big5"]),
            )
            for a in analistas_sel
        ] if not erros else []
        projetos_modelo = [
            Projeto(
                nome=p["nome"], receita=p["receita"], horas=p["horas"], nivel_min=p["nivel_min"],
                max_analistas=int(p["max_analistas"]), min_analistas=int(p["min_analistas"]),
                competencias_min=dict(reqs_por_projeto.get(p["id"], {})), big5_min=dict(p["big5_min"]),
            )
            for p in projetos_sel
        ] if not erros else []

        input_hash = None
        if not erros:
            payload = {
                "analistas": [asdict(a) for a in analistas_modelo],
                "projetos": [asdict(p) for p in projetos_modelo],
                "h_min": st.session_state.h_min,
            }
            input_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

            with db.get_connection() as conn:
                ultima = db.get_ultima_execucao(conn)
            if ultima is not None and ultima["input_hash"] == input_hash:
                st.info(
                    "Os dados desta rodada sao identicos aos da ultima execucao "
                    f"(#{ultima['id_execucao']}, {ultima['executado_em']}). Reprocessar vai gerar "
                    "os mesmos resultados."
                )
            elif ultima is not None:
                st.warning(
                    f"Os dados mudaram desde a ultima execucao (#{ultima['id_execucao']}, "
                    f"{ultima['executado_em']}). Recomenda-se reprocessar para atualizar a previa."
                )

        if st.button("Reprocessar / gerar previa da alocacao", type="primary", disabled=bool(erros)):
            with st.spinner("Resolvendo o modelo MILP (PuLP/CBC)..."):
                resultado = resolver_modelo(analistas_modelo, projetos_modelo, st.session_state.h_min)
            st.session_state.resultado = resultado

            with db.get_connection() as conn:
                id_por_nome_analista = {a["nome"]: a["id"] for a in analistas_sel}
                id_por_nome_projeto = {p["nome"]: p["id"] for p in projetos_sel}
                id_execucao = db.salvar_execucao(
                    conn, st.session_state.h_min, resultado, id_por_nome_analista, id_por_nome_projeto,
                    periodo_referencia=periodo_referencia, input_hash=input_hash,
                )
            st.session_state.ultima_execucao_id = id_execucao
            st.success(
                f"Previa #{id_execucao} gerada. Va para **Dashboard de Resultados** para "
                "visualizar e, se for o caso, confirmar esta alocacao."
            )


# =====================================================================
# Pagina 5 · Dashboard de Resultados
# =====================================================================

elif pagina == "Dashboard de Resultados":
    with db.get_connection() as conn:
        execucoes = db.list_execucoes(conn)

    if not execucoes:
        st.info("Nenhuma execucao registrada ainda. Gere uma previa na pagina **Geracao da Alocacao**.")
    else:
        st.subheader("Historico de execucoes")
        opcoes_ids = [e["id_execucao"] for e in execucoes]
        default_id = st.session_state.ultima_execucao_id if st.session_state.ultima_execucao_id in opcoes_ids else opcoes_ids[0]

        def _rotulo_execucao(id_exec):
            e = next(e for e in execucoes if e["id_execucao"] == id_exec)
            lucro = f"R$ {e['lucro_liquido']:,.2f}" if e["lucro_liquido"] is not None else "inviavel"
            periodo = e["periodo_referencia"] or "sem periodo"
            return f"#{e['id_execucao']} · {e['executado_em']} · {periodo} · {e['situacao']} · {lucro}"

        id_execucao_sel = st.selectbox(
            "Execucao", options=opcoes_ids, index=opcoes_ids.index(default_id),
            format_func=_rotulo_execucao, key="dashboard_execucao_sel",
        )

        with db.get_connection() as conn:
            execucao = db.get_execucao(conn, id_execucao_sel)
            alocacoes_db = db.list_alocacoes_execucao(conn, id_execucao_sel)

        st.divider()

        col_status, col_confirmar = st.columns([4, 1])
        col_status.markdown(
            f"**Situacao:** {execucao['situacao']}  ·  **Periodo de referencia:** "
            f"{execucao['periodo_referencia'] or '—'}  ·  **Status do solver:** {execucao['status']}"
        )
        if execucao["situacao"] != db.SITUACAO_CONFIRMADA:
            if col_confirmar.button("Escolher esta alocacao", type="primary", key="btn_confirmar_execucao"):
                with db.get_connection() as conn:
                    db.set_situacao_execucao(conn, id_execucao_sel, db.SITUACAO_CONFIRMADA)
                st.rerun()
        else:
            col_confirmar.success("Confirmada")

        if not execucao["viavel"]:
            st.error(f"Esta execucao nao encontrou solucao viavel (status do solver: {execucao['status']}).")
        else:
            n_projetos = len({a["projeto_nome"] for a in alocacoes_db}) or None
            margem = (execucao["lucro_liquido"] / execucao["receita_total"] * 100) if execucao["receita_total"] else 0.0

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Lucro liquido", f"R$ {execucao['lucro_liquido']:,.2f}", f"{margem:.1f}% da receita")
            k2.metric("Receita total", f"R$ {execucao['receita_total']:,.2f}")
            k3.metric("Custo total", f"R$ {execucao['custo_total']:,.2f}")
            k4.metric("Projetos aceitos", f"{len({a['projeto_nome'] for a in alocacoes_db})}")

            resultado_sessao = st.session_state.resultado
            tem_detalhe_sessao = (
                resultado_sessao is not None and st.session_state.ultima_execucao_id == id_execucao_sel
            )

            if tem_detalhe_sessao:
                st.markdown('<div class="sad-card-kicker">Distribuicao de horas por analista</div>', unsafe_allow_html=True)
                for r in resultado_sessao.resumo_analistas:
                    st.write(f"**{r.nome}** — {r.horas_alocadas:.1f}h de {r.disponibilidade:.1f}h disponiveis (nesta rodada)")
                    st.progress(r.utilizacao)

            st.markdown('<div class="sad-card-kicker">Alocacao detalhada</div>', unsafe_allow_html=True)
            if alocacoes_db:
                df = pd.DataFrame([
                    {
                        "Analista": a["analista_nome"], "Projeto": a["projeto_nome"],
                        "Horas": a["horas"], "Custo": f"R$ {a['custo']:,.2f}",
                        "Receita gerada": f"R$ {a['receita']:,.2f}",
                    }
                    for a in alocacoes_db
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.caption("Nenhuma alocacao realizada.")

            st.markdown('<div class="sad-card-kicker">Projetos aceitos e recusados (y[j])</div>', unsafe_allow_html=True)
            if tem_detalhe_sessao:
                for nome in resultado_sessao.aceitos:
                    st.markdown(f"\U0001F7E2 **Aceito** — {nome}")
                for nome, motivo in resultado_sessao.recusados:
                    st.markdown(f"⚪ **Recusado** — {nome}")
                    st.caption(motivo)
            else:
                aceitos_hist = sorted({a["projeto_nome"] for a in alocacoes_db})
                for nome in aceitos_hist:
                    st.markdown(f"\U0001F7E2 **Aceito** — {nome}")
                st.caption(
                    "Motivos de recusa por projeto so' ficam disponiveis para a execucao "
                    "mais recente gerada nesta sessao (nao sao persistidos no banco)."
                )

        st.divider()

        # ===== Exportacao do relatorio =====

        st.subheader("Exportacao do relatorio")

        def _montar_relatorio_txt() -> str:
            linhas = []
            linhas.append("RELATORIO DE ALOCACAO OTIMA DE ANALISTAS")
            linhas.append("Sistema de Apoio a Decisao - Programacao Linear Inteira Mista (PuLP/CBC)")
            linhas.append("=" * 60)
            linhas.append(f"Execucao #{execucao['id_execucao']} - {execucao['executado_em']}")
            linhas.append(f"Situacao: {execucao['situacao']} | Periodo de referencia: {execucao['periodo_referencia'] or '—'}")
            linhas.append(f"Parametro h_min (horas minimas por alocacao): {execucao['h_min']}h")
            linhas.append("")
            linhas.append("1. RESULTADO GERAL")
            linhas.append("-" * 60)
            if not execucao["viavel"]:
                linhas.append(f"Modelo infactivel (status: {execucao['status']}).")
            else:
                linhas.append(f"Lucro liquido total: R$ {execucao['lucro_liquido']:,.2f}")
                linhas.append(f"Receita total: R$ {execucao['receita_total']:,.2f}")
                linhas.append(f"Custo total alocado: R$ {execucao['custo_total']:,.2f}")
                linhas.append("")
                linhas.append("2. ALOCACAO DETALHADA (analista x projeto x horas)")
                linhas.append("-" * 60)
                if alocacoes_db:
                    for a in alocacoes_db:
                        linhas.append(
                            f"- {a['analista_nome']} -> {a['projeto_nome']}: {a['horas']:.1f}h, "
                            f"custo R$ {a['custo']:,.2f}, receita gerada R$ {a['receita']:,.2f}"
                        )
                else:
                    linhas.append("(nenhuma alocacao realizada)")
            linhas.append("")
            linhas.append("3. NOTA METODOLOGICA")
            linhas.append("-" * 60)
            linhas.append(
                "Resultado obtido pela resolucao exata do modelo de Programacao Linear "
                "Inteira Mista (Equacoes 1 a 11, com os ajustes documentados no README: "
                "piso de horas contratadas, Njmin generalizado e cobertura conjunta de "
                "habilidades tecnicas) via solver CBC (branch-and-cut), atraves da "
                "biblioteca PuLP. Disponibilidade de cada analista considera horas ja "
                "comprometidas em execucoes confirmadas no mesmo periodo de referencia."
            )
            return "\n".join(linhas)

        with st.container(border=True):
            st.markdown('<div class="sad-card-kicker">Relatorio completo</div>', unsafe_allow_html=True)
            st.caption(
                "O relatorio reune os parametros da execucao selecionada, o resultado "
                "da otimizacao (lucro liquido, receita e custo) e a alocacao detalhada "
                "de cada analista por projeto."
            )
            st.download_button(
                "Baixar relatorio (.txt)",
                data=_montar_relatorio_txt(),
                file_name=f"relatorio-alocacao-execucao-{execucao['id_execucao']}.txt",
                mime="text/plain",
            )
