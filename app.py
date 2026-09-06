# Interface do SAD (Streamlit) - roda com: streamlit run app.py
#
# Persistencia em SQLite (db.py, 7 tabelas: analistas, projetos, habilidades,
# analista_habilidade, projeto_habilidade_requerida, execucoes, alocacoes).
# Cada edicao de campo grava direto no banco (sem botao "salvar" separado) -
# o script inteiro roda de novo a cada interacao, e os dados sao sempre lidos
# do banco no topo do script, entao a fonte da verdade e' sempre o SQLite.

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
        "id": row["id_analista"], "nome": row["nome"], "senioridade": row["senioridade"],
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


if "resultado" not in st.session_state:
    st.session_state.resultado = None
if "h_min" not in st.session_state:
    st.session_state.h_min = 20


# cabecalho
st.markdown('<div class="sad-kicker">Sistema de Apoio a Decisao &middot; MILP</div>', unsafe_allow_html=True)
st.title("Alocacao Otima de Analistas")
st.markdown(
    '<p class="sad-subtitle">Cadastre analistas e projetos, execute o modelo de '
    "otimizacao (Programacao Linear Inteira Mista) e visualize a alocacao que "
    "maximiza o lucro liquido.</p>",
    unsafe_allow_html=True,
)
st.divider()


# ===== 01 · Analistas =====

with db.get_connection() as conn:
    analistas = [_analista_dict(r) for r in db.list_analistas(conn)]

st.subheader(f"01 · Analistas ({len(analistas)} cadastrados)")

for idx, a in enumerate(analistas):
    with st.container(border=True):
        col_head, col_del = st.columns([10, 1])
        col_head.markdown(f'<div class="sad-card-kicker">Analista {idx + 1}</div>', unsafe_allow_html=True)
        if col_del.button("Remover", key=f"del_analista_{a['id']}", use_container_width=True):
            with db.get_connection() as conn:
                db.delete_analista(conn, a["id"])
            st.rerun()

        nome = st.text_input("Nome", value=a["nome"], key=f"nome_{a['id']}", placeholder="Ex.: Ana Souza")

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
            "Disp. (h/mes)", min_value=0.0, value=float(a["disponibilidade"]), step=5.0, key=f"disp_{a['id']}",
            help="Disponibilidade de horas (Di), limite da Equacao 2.",
        )
        ausente = st.checkbox(
            "Ausencia programada no periodo (Ai)", value=a["ausente"], key=f"ausente_{a['id']}",
            help="Se marcado, o analista nao pode ser vinculado a nenhum projeto (Equacao 10).",
        )

        st.caption(
            "Perfil comportamental Big Five (0-100). Competencias tecnicas sao "
            "cadastradas na tela **02 · Habilidades tecnicas dos analistas**, abaixo."
        )
        cols = st.columns(5)
        big5 = dict(a["big5"])
        for i, trait in enumerate(TRAITS):
            big5[trait] = cols[i].slider(
                trait, min_value=0, max_value=100, value=int(a["big5"].get(trait, 50)),
                key=f"big5_{trait}_{a['id']}", help=TRAIT_LABELS[trait],
            )

        with db.get_connection() as conn:
            db.update_analista(conn, a["id"], {
                "nome": nome, "senioridade": senioridade, "custo_hora": custo_hora,
                "disponibilidade": disponibilidade, "ausente": int(ausente),
                "com": big5["COM"], "col": big5["COL"], "org": big5["ORG"],
                "ada": big5["ADA"], "est": big5["EST"],
            })

if st.button("+ Adicionar analista"):
    with db.get_connection() as conn:
        db.insert_analista(conn, {
            "nome": "", "senioridade": "Pleno", "custo_hora": 0.0, "disponibilidade": 0.0,
            "ausente": 0, "com": 50, "col": 50, "org": 50, "ada": 50, "est": 50,
        })
    st.rerun()

st.divider()


# ===== 02 · Habilidades tecnicas dos analistas =====

st.subheader("02 · Habilidades tecnicas dos analistas")
st.caption(
    "Gerencie o catalogo global de habilidades tecnicas e o nivel de proficiencia "
    "(SKILLik, 0-100) de cada analista em cada habilidade."
)

with st.container(border=True):
    st.markdown('<div class="sad-card-kicker">Catalogo de habilidades</div>', unsafe_allow_html=True)
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

if habilidades and analistas:
    with st.container(border=True):
        st.markdown('<div class="sad-card-kicker">Proficiencia por analista</div>', unsafe_allow_html=True)
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
elif not habilidades:
    st.caption("Cadastre ao menos uma habilidade no catalogo para atribuir proficiencias.")
else:
    st.caption("Cadastre ao menos um analista para atribuir proficiencias.")

st.divider()


# ===== 03 · Projetos =====

with db.get_connection() as conn:
    projetos = [_projeto_dict(r) for r in db.list_projetos(conn)]

st.subheader(f"03 · Projetos ({len(projetos)} cadastrados)")

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
            "Competencias tecnicas exigidas (REQjk) sao cadastradas na tela "
            "**04 · Habilidades tecnicas exigidas pelos projetos**, abaixo."
        )
        st.caption("Perfil comportamental minimo exigido (0-100; 0 = nao exigido) – restricoes analogas a Equacao 8")
        cols = st.columns(5)
        big5_min = dict(p["big5_min"])
        for i, trait in enumerate(TRAITS):
            big5_min[trait] = cols[i].slider(
                trait, min_value=0, max_value=100, value=int(p["big5_min"].get(trait, 0)),
                key=f"pbig5_{trait}_{p['id']}", help=TRAIT_LABELS[trait],
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

st.divider()


# ===== 04 · Habilidades tecnicas exigidas pelos projetos =====

st.subheader("04 · Habilidades tecnicas exigidas pelos projetos")
st.caption(
    "Defina, para cada projeto, o nivel minimo exigido (REQjk, 0-100) em cada "
    "habilidade do catalogo. Uma habilidade com REQjk = 0 nao entra na restricao "
    "de cobertura (Equacao 9) - equivale a 'nao exigida'."
)

with db.get_connection() as conn:
    habilidades = db.list_habilidades(conn)

if not habilidades:
    st.caption("Cadastre ao menos uma habilidade na tela 02 para definir exigencias.")
elif not projetos:
    st.caption("Cadastre ao menos um projeto para definir exigencias.")
else:
    with st.container(border=True):
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

st.divider()


# ===== 05 · Parametros e execucao =====

st.subheader("05 · Parametros e execucao")

with st.container(border=True):
    st.session_state.h_min = st.number_input(
        "Horas minimas por alocacao (h_min)", min_value=0, value=int(st.session_state.h_min), step=5,
        help="Nenhum analista recebe menos que esse numero de horas em um projeto "
             "quando vinculado a ele - evita fragmentacoes pouco relevantes na "
             "pratica (restricao big-M, Equacao 5).",
    )

    def _analistas_validos():
        erros = []
        for a in analistas:
            if not a["nome"].strip():
                erros.append("Ha analistas sem nome.")
            if a["custo_hora"] <= 0:
                erros.append(f"Custo/h de '{a['nome'] or 'analista sem nome'}' deve ser maior que zero.")
            if a["disponibilidade"] <= 0:
                erros.append(f"Disponibilidade de '{a['nome'] or 'analista sem nome'}' deve ser maior que zero.")
        return erros

    def _projetos_validos():
        erros = []
        for p in projetos:
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
    if not analistas or not projetos:
        erros.append("Cadastre ao menos um projeto e um analista para executar o modelo.")
    erros += _analistas_validos()
    erros += _projetos_validos()

    if erros:
        for e in set(erros):
            st.error(e)

    if st.button("Executar otimizacao", type="primary", disabled=bool(erros)):
        with db.get_connection() as conn:
            niveis_por_analista = {a["id"]: db.get_niveis_analista(conn, a["id"]) for a in analistas}
            reqs_por_projeto = {p["id"]: db.get_requisitos_projeto(conn, p["id"]) for p in projetos}

        analistas_modelo = [
            Analista(
                nome=a["nome"], senioridade=a["senioridade"], custo_hora=a["custo_hora"],
                disponibilidade=a["disponibilidade"], ausente=a["ausente"],
                competencias=dict(niveis_por_analista[a["id"]]), big5=dict(a["big5"]),
            )
            for a in analistas
        ]
        projetos_modelo = [
            Projeto(
                nome=p["nome"], receita=p["receita"], horas=p["horas"], nivel_min=p["nivel_min"],
                max_analistas=int(p["max_analistas"]), min_analistas=int(p["min_analistas"]),
                competencias_min=dict(reqs_por_projeto[p["id"]]), big5_min=dict(p["big5_min"]),
            )
            for p in projetos
        ]
        with st.spinner("Resolvendo o modelo MILP (PuLP/CBC)..."):
            resultado = resolver_modelo(analistas_modelo, projetos_modelo, st.session_state.h_min)
        st.session_state.resultado = resultado

        with db.get_connection() as conn:
            id_por_nome_analista = {a["nome"]: a["id"] for a in analistas}
            id_por_nome_projeto = {p["nome"]: p["id"] for p in projetos}
            db.salvar_execucao(conn, st.session_state.h_min, resultado, id_por_nome_analista, id_por_nome_projeto)

st.divider()


# ===== 06 · Resultado =====

resultado = st.session_state.resultado

if resultado is not None:
    st.subheader("06 · Resultado")

    if not resultado.viavel:
        st.error(f"O modelo nao encontrou solucao viavel (status do solver: {resultado.status}).")
    else:
        st.success("Solucao encontrada.")

        n_projetos = len(projetos)
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
            import pandas as pd
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

    # ===== 07 · Exportacao do relatorio =====

    st.subheader("07 · Exportacao do relatorio")

    def _montar_relatorio_txt() -> str:
        linhas = []
        linhas.append("RELATORIO DE ALOCACAO OTIMA DE ANALISTAS")
        linhas.append("Sistema de Apoio a Decisao - Programacao Linear Inteira Mista (PuLP/CBC)")
        linhas.append("=" * 60)
        linhas.append(f"Parametro h_min (horas minimas por alocacao): {st.session_state.h_min}h")
        linhas.append(
            f"Projetos cadastrados: {len(projetos)} | "
            f"Analistas cadastrados: {len(analistas)}"
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
            linhas.append(f"Projetos aceitos: {len(resultado.aceitos)} de {len(projetos)}")
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
            "Inteira Mista (Equacoes 1 a 11, com os ajustes documentados no README: "
            "piso de horas contratadas, Njmin generalizado e cobertura conjunta de "
            "habilidades tecnicas) via solver CBC (branch-and-cut), atraves da "
            "biblioteca PuLP."
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
