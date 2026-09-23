# Interface do SAD (Streamlit) - roda com: streamlit run app.py
#
# Persistencia em SQLite (db.py, 7 tabelas). Navegacao por menu lateral
# (st.navigation/st.Page, com icones) e tema escuro configurado em
# .streamlit/config.toml (sem CSS solto no codigo). Cada edicao e' salva
# explicitamente (botao "Salvar"), nao mais a cada rerun.

import hashlib
import json
import os
from dataclasses import asdict

import pandas as pd
import streamlit as st

# Streamlit ja expoe st.secrets como variavel de ambiente automaticamente na
# maioria das versoes, mas isso e' feito aqui de forma explicita (antes do
# "import db", que le SUPABASE_DB_URL/TURSO_DATABASE_URL/TURSO_AUTH_TOKEN de
# os.environ na hora de abrir cada conexao) pra nao depender desse
# comportamento implicito - ver db.py::get_connection. Sem essas secrets
# configuradas, nada muda: db.py cai de volta pro arquivo SQLite local, como
# sempre foi. st.secrets lanca StreamlitSecretNotFoundError quando nao existe
# NENHUM secrets.toml (caso comum em dev local) - por isso o try/except em
# vez de "if _chave in st.secrets".
try:
    for _chave in ("SUPABASE_DB_URL", "DATABASE_URL", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
        if _chave in st.secrets and _chave not in os.environ:
            os.environ[_chave] = st.secrets[_chave]
except Exception:
    pass

import db
from optimization import (
    NIVEIS,
    NIVEIS_LABEL,
    TRAITS,
    TRAIT_LABELS,
    Analista,
    Projeto,
    resolver_modelo,
)

st.set_page_config(page_title="Alocação Ótima de Analistas", page_icon="📊", layout="wide")

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
        "prazo_semanas": row["prazo_semanas"],
        "big5_min": {"COM": row["com_min"], "COL": row["col_min"], "ORG": row["org_min"],
                      "ADA": row["ada_min"], "EST": row["est_min"]},
    }


if "resultado" not in st.session_state:
    st.session_state.resultado = None
if "h_min" not in st.session_state:
    st.session_state.h_min = 20
if "ultima_execucao_id" not in st.session_state:
    st.session_state.ultima_execucao_id = None


# =====================================================================
# Página · Cadastro de Analistas
# =====================================================================

def pagina_analistas():
    st.title("Cadastro de Analistas")

    with db.get_connection() as conn:
        analistas = [_analista_dict(r) for r in db.list_analistas(conn)]

    if analistas:
        st.dataframe(
            pd.DataFrame([
                {
                    "ID": a["id"], "Nome": a["nome"], "CPF": a["cpf"],
                    "Senioridade": NIVEIS_LABEL[a["senioridade"]],
                    "Custo/h (R$)": a["custo_hora"],
                    "Disponibilidade (h)": a["disponibilidade"],
                    "Ausente": "Sim" if a["ausente"] else "Não",
                }
                for a in analistas
            ]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Nenhum analista cadastrado.")

    st.subheader("Editar analista")
    opcoes = {a["id"]: f"{a['nome'] or 'Sem nome'} (id {a['id']})" for a in analistas}
    opcoes[None] = "+ Novo analista"
    id_sel = st.selectbox(
        "Selecionar", options=list(opcoes.keys()), format_func=lambda i: opcoes[i],
        key="sel_analista_edit",
    )
    analista_sel = next((a for a in analistas if a["id"] == id_sel), None)
    _form_analista(analista_sel)


def _form_analista(a):
    novo = a is None
    chave = "novo" if novo else a["id"]

    with st.container(border=True):
        c_nome, c_cpf = st.columns(2)
        nome = c_nome.text_input("Nome", value="" if novo else a["nome"], key=f"an_nome_{chave}")
        cpf = c_cpf.text_input(
            "CPF", value="" if novo else a["cpf"], placeholder="000.000.000-00", key=f"an_cpf_{chave}",
        )

        c1, c2, c3 = st.columns(3)
        senioridade = c1.selectbox(
            "Senioridade", options=list(NIVEIS.keys()), format_func=lambda k: NIVEIS_LABEL[k],
            index=0 if novo else list(NIVEIS.keys()).index(a["senioridade"]), key=f"an_nivel_{chave}",
        )
        custo_hora = c2.number_input(
            "Custo/h (R$)", min_value=0.0, value=0.0 if novo else float(a["custo_hora"]),
            step=5.0, key=f"an_custo_{chave}",
        )
        disponibilidade = c3.number_input(
            "Disponibilidade (h/mês)", min_value=0.0, max_value=float(db.TETO_HORAS_MENSAIS_CLT),
            value=0.0 if novo else float(a["disponibilidade"]), step=5.0, key=f"an_disp_{chave}",
            help=f"Teto fixo de {db.TETO_HORAS_MENSAIS_CLT}h/mês (jornada integral, art. 58 da CLT).",
        )
        ausente = st.checkbox(
            "Ausência programada no período", value=False if novo else a["ausente"], key=f"an_ausente_{chave}",
        )

        st.caption("Perfil comportamental")
        cols = st.columns(5)
        big5 = {}
        for i, trait in enumerate(TRAITS):
            big5[trait] = cols[i].slider(
                TRAIT_LABELS[trait], min_value=0, max_value=100,
                value=50 if novo else int(a["big5"].get(trait, 50)), key=f"an_big5_{trait}_{chave}",
            )

        col_salvar, col_remover = st.columns([1, 1])
        if col_salvar.button("Salvar", type="primary", key=f"an_salvar_{chave}", use_container_width=True):
            if not cpf.strip():
                st.error("Informe o CPF do analista.")
            elif not db.cpf_valido(cpf):
                st.error("CPF em formato inválido. Use 000.000.000-00.")
            elif not nome.strip():
                st.error("Informe o nome do analista.")
            else:
                dados = {
                    "nome": nome, "cpf": cpf.strip(), "senioridade": senioridade,
                    "custo_hora": custo_hora, "disponibilidade": disponibilidade, "ausente": int(ausente),
                    "com": big5["COM"], "col": big5["COL"], "org": big5["ORG"],
                    "ada": big5["ADA"], "est": big5["EST"],
                }
                try:
                    with db.get_connection() as conn:
                        if novo:
                            db.insert_analista(conn, dados)
                        else:
                            db.update_analista(conn, a["id"], dados)
                    st.success("Analista salvo.")
                    st.rerun()
                except db.IntegrityError:
                    st.error(f"CPF '{cpf}' já está cadastrado para outro analista.")

        if not novo and col_remover.button("Remover", key=f"an_remover_{chave}", use_container_width=True):
            with db.get_connection() as conn:
                db.delete_analista(conn, a["id"])
            st.success("Analista removido.")
            st.rerun()


# =====================================================================
# Página · Cadastro de Projetos
# =====================================================================

def pagina_projetos():
    st.title("Cadastro de Projetos")

    with db.get_connection() as conn:
        projetos = [_projeto_dict(r) for r in db.list_projetos(conn)]

    if projetos:
        st.dataframe(
            pd.DataFrame([
                {
                    "ID": p["id"], "Nome": p["nome"], "Receita (R$)": p["receita"], "Horas": p["horas"],
                    "Nível mínimo": NIVEIS_LABEL[p["nivel_min"]],
                    "Njmax": p["max_analistas"], "Njmin": p["min_analistas"],
                    "Prazo (semanas)": p["prazo_semanas"],
                }
                for p in projetos
            ]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Nenhum projeto cadastrado.")

    st.subheader("Editar projeto")
    opcoes = {p["id"]: f"{p['nome'] or 'Sem nome'} (id {p['id']})" for p in projetos}
    opcoes[None] = "+ Novo projeto"
    id_sel = st.selectbox(
        "Selecionar", options=list(opcoes.keys()), format_func=lambda i: opcoes[i],
        key="sel_projeto_edit",
    )
    projeto_sel = next((p for p in projetos if p["id"] == id_sel), None)
    _form_projeto(projeto_sel)


def _form_projeto(p):
    novo = p is None
    chave = "novo" if novo else p["id"]

    with st.container(border=True):
        nome = st.text_input("Nome do projeto", value="" if novo else p["nome"], key=f"pr_nome_{chave}")

        c1, c2, c3, c4, c5 = st.columns(5)
        receita = c1.number_input(
            "Receita esperada (R$)", min_value=0.0, value=0.0 if novo else float(p["receita"]),
            step=1000.0, key=f"pr_receita_{chave}",
        )
        horas = c2.number_input(
            "Horas contratadas", min_value=0.0, value=0.0 if novo else float(p["horas"]),
            step=10.0, key=f"pr_horas_{chave}",
        )
        max_analistas = c3.number_input(
            "Njmax", min_value=1, value=1 if novo else int(p["max_analistas"]), step=1, key=f"pr_maxan_{chave}",
        )
        min_analistas = c4.number_input(
            "Njmin", min_value=1, max_value=int(max_analistas),
            value=1 if novo else min(int(p["min_analistas"]), int(max_analistas)), step=1, key=f"pr_minan_{chave}",
        )
        prazo_semanas = c5.number_input(
            "Prazo (semanas)", min_value=1, value=4 if novo else int(p["prazo_semanas"]), step=1,
            key=f"pr_prazo_{chave}",
            help="Quando uma alocação confirmada deste projeto completa esse prazo (contado a "
                 "partir da confirmação), as horas do analista são liberadas automaticamente.",
        )

        nivel_min = st.selectbox(
            "Nível técnico mínimo", options=list(NIVEIS.keys()), format_func=lambda k: NIVEIS_LABEL[k],
            index=0 if novo else list(NIVEIS.keys()).index(p["nivel_min"]), key=f"pr_nivel_{chave}",
        )

        st.caption("Perfil comportamental mínimo exigido")
        cols = st.columns(5)
        big5_min = {}
        for i, trait in enumerate(TRAITS):
            big5_min[trait] = cols[i].slider(
                TRAIT_LABELS[trait], min_value=0, max_value=100,
                value=0 if novo else int(p["big5_min"].get(trait, 0)), key=f"pr_big5_{trait}_{chave}",
            )

        col_salvar, col_remover = st.columns([1, 1])
        if col_salvar.button("Salvar", type="primary", key=f"pr_salvar_{chave}", use_container_width=True):
            if not nome.strip():
                st.error("Informe o nome do projeto.")
            else:
                dados = {
                    "nome": nome, "receita": receita, "horas": horas, "nivel_min": nivel_min,
                    "max_analistas": int(max_analistas), "min_analistas": int(min_analistas),
                    "prazo_semanas": int(prazo_semanas),
                    "com_min": big5_min["COM"], "col_min": big5_min["COL"], "org_min": big5_min["ORG"],
                    "ada_min": big5_min["ADA"], "est_min": big5_min["EST"],
                }
                with db.get_connection() as conn:
                    if novo:
                        db.insert_projeto(conn, dados)
                    else:
                        db.update_projeto(conn, p["id"], dados)
                st.success("Projeto salvo.")
                st.rerun()

        if not novo and col_remover.button("Remover", key=f"pr_remover_{chave}", use_container_width=True):
            with db.get_connection() as conn:
                db.delete_projeto(conn, p["id"])
            st.success("Projeto removido.")
            st.rerun()


# =====================================================================
# Página · Cadastro de Habilidades Técnicas
# =====================================================================

def pagina_habilidades():
    st.title("Cadastro de Habilidades Técnicas")

    with db.get_connection() as conn:
        analistas = [_analista_dict(r) for r in db.list_analistas(conn)]
        projetos = [_projeto_dict(r) for r in db.list_projetos(conn)]
        habilidades = db.list_habilidades(conn)

    st.subheader("Catálogo")
    with st.container(border=True):
        if habilidades:
            for h in habilidades:
                hc1, hc2, hc3 = st.columns([6, 2, 1])
                novo_nome = hc1.text_input(
                    "Nome", value=h["nome"], key=f"hab_nome_{h['id_habilidade']}", label_visibility="collapsed",
                )
                if novo_nome != h["nome"] and hc2.button("Renomear", key=f"hab_ren_{h['id_habilidade']}"):
                    try:
                        with db.get_connection() as conn:
                            db.rename_habilidade(conn, h["id_habilidade"], novo_nome)
                        st.success("Habilidade renomeada.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                if hc3.button("Remover", key=f"hab_del_{h['id_habilidade']}"):
                    with db.get_connection() as conn:
                        db.delete_habilidade(conn, h["id_habilidade"])
                    st.success("Habilidade removida.")
                    st.rerun()
        else:
            st.info("Nenhuma habilidade cadastrada.")

        c_nova, c_add = st.columns([4, 1])
        nova_habilidade = c_nova.text_input("Nova habilidade", key="nova_habilidade", placeholder="Ex.: Python")
        if c_add.button("Adicionar", key="btn_add_habilidade", use_container_width=True):
            try:
                with db.get_connection() as conn:
                    db.add_habilidade(conn, nova_habilidade)
                st.success("Habilidade adicionada.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    aba_analistas, aba_projetos = st.tabs(["Proficiência dos analistas", "Exigência dos projetos"])

    with aba_analistas:
        if not habilidades or not analistas:
            st.info("Cadastre habilidades e analistas para atribuir proficiências.")
        else:
            nomes_analistas = [a["nome"] or f"Sem nome (id {a['id']})" for a in analistas]
            idx_sel = st.selectbox(
                "Analista", options=range(len(analistas)), format_func=lambda i: nomes_analistas[i],
                key="skill_analista_sel",
            )
            analista_sel = analistas[idx_sel]
            with db.get_connection() as conn:
                niveis = db.get_niveis_analista(conn, analista_sel["id"])
            with st.container(border=True):
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
        if not habilidades or not projetos:
            st.info("Cadastre habilidades e projetos para definir exigências.")
        else:
            nomes_projetos = [p["nome"] or f"Sem nome (id {p['id']})" for p in projetos]
            idx_sel = st.selectbox(
                "Projeto", options=range(len(projetos)), format_func=lambda i: nomes_projetos[i],
                key="req_projeto_sel",
            )
            projeto_sel = projetos[idx_sel]
            with db.get_connection() as conn:
                reqs = db.get_requisitos_projeto(conn, projeto_sel["id"])
            with st.container(border=True):
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
# Seção · Gerar nova alocação (dentro do Dashboard de Resultados)
# =====================================================================

def _secao_geracao():
    with db.get_connection() as conn:
        analistas = [_analista_dict(r) for r in db.list_analistas(conn)]
        projetos = [_projeto_dict(r) for r in db.list_projetos(conn)]
        # niveis_por_analista/reqs_por_projeto sao rechaveados de id_habilidade (int, chave
        # natural no banco) para nome (str, unico no catalogo - ver habilidades.nome UNIQUE):
        # e o nome que o motor de otimizacao usa como identificador de habilidade (K), entao
        # e' o nome que aparece pro gestor no diagnostico de recusa (_diagnosticar_recusa),
        # em vez do id numerico interno.
        nome_por_id_habilidade = {h["id_habilidade"]: h["nome"] for h in db.list_habilidades(conn)}
        niveis_por_analista = {
            a["id"]: {nome_por_id_habilidade[k]: v for k, v in db.get_niveis_analista(conn, a["id"]).items()}
            for a in analistas
        }
        reqs_por_projeto = {
            p["id"]: {nome_por_id_habilidade[k]: v for k, v in db.get_requisitos_projeto(conn, p["id"]).items()}
            for p in projetos
        }
        horas_comprometidas = {a["id"]: db.get_horas_comprometidas(conn, a["id"]) for a in analistas}
        projetos_ja_confirmados = db.list_projetos_ja_confirmados(conn)

    with st.container(border=True):
        st.session_state.h_min = st.number_input(
            "Horas mínimas por alocação (h_min)", min_value=0, value=int(st.session_state.h_min), step=5,
        )

        st.caption(
            "Projetos já confirmados vêm desmarcados por padrão - uma nova rodada, por "
            "padrão, decide só o que ainda está em aberto, sem reorganizar o que já foi "
            "confirmado. Marque manualmente se quiser reconsiderar um projeto confirmado."
        )
        c_a, c_p = st.columns(2)
        ids_analistas_sel = c_a.multiselect(
            "Analistas nesta rodada", options=[a["id"] for a in analistas],
            default=[a["id"] for a in analistas],
            format_func=lambda i: (
                f"{next(a['nome'] or 'Sem nome' for a in analistas if a['id'] == i)} (id {i})"
            ),
        )
        ids_projetos_sel = c_p.multiselect(
            "Projetos nesta rodada", options=[p["id"] for p in projetos],
            default=[p["id"] for p in projetos if p["id"] not in projetos_ja_confirmados],
            format_func=lambda i: (
                f"{next(p['nome'] or 'Sem nome' for p in projetos if p['id'] == i)} (id {i})"
                + (" (já confirmado)" if i in projetos_ja_confirmados else "")
            ),
        )

    analistas_sel = [a for a in analistas if a["id"] in ids_analistas_sel]
    projetos_sel = [p for p in projetos if p["id"] in ids_projetos_sel]

    if any(horas_comprometidas.get(a["id"], 0) > 0 for a in analistas_sel):
        st.subheader("Disponibilidade efetiva")
        st.dataframe(
            pd.DataFrame([
                {
                    "Analista": a["nome"],
                    "Nominal (h)": a["disponibilidade"],
                    "Comprometidas (h)": horas_comprometidas.get(a["id"], 0),
                    "Efetiva (h)": max(0.0, a["disponibilidade"] - horas_comprometidas.get(a["id"], 0)),
                }
                for a in analistas_sel
            ]),
            use_container_width=True, hide_index=True,
        )

    def _analistas_validos():
        erros = []
        for a in analistas_sel:
            if not a["nome"].strip():
                erros.append("Há analistas sem nome.")
            if not a["cpf"].strip() or not db.cpf_valido(a["cpf"]):
                erros.append(f"CPF de '{a['nome'] or 'analista sem nome'}' está ausente ou inválido.")
            if a["custo_hora"] <= 0:
                erros.append(f"Custo/h de '{a['nome'] or 'analista sem nome'}' deve ser maior que zero.")
            try:
                db.validar_disponibilidade(a["disponibilidade"])
            except ValueError as e:
                erros.append(str(e))
            if a["disponibilidade"] <= 0:
                erros.append(f"Disponibilidade de '{a['nome'] or 'analista sem nome'}' deve ser maior que zero.")
        return erros

    def _projetos_validos():
        erros = []
        for p in projetos_sel:
            if not p["nome"].strip():
                erros.append("Há projetos sem nome.")
            if p["receita"] <= 0:
                erros.append(f"Receita de '{p['nome'] or 'projeto sem nome'}' deve ser maior que zero.")
            if p["horas"] <= 0:
                erros.append(f"Horas de '{p['nome'] or 'projeto sem nome'}' devem ser maiores que zero.")
            if not (1 <= p["min_analistas"] <= p["max_analistas"]):
                erros.append(
                    f"Njmin de '{p['nome'] or 'projeto sem nome'}' deve satisfazer "
                    f"1 ≤ Njmin ({p['min_analistas']}) ≤ Njmax ({p['max_analistas']})."
                )
        return erros

    erros = []
    if not analistas_sel or not projetos_sel:
        erros.append("Selecione ao menos um projeto e um analista para executar o modelo.")
    erros += _analistas_validos()
    erros += _projetos_validos()

    for e in set(erros):
        st.error(e)

    analistas_modelo = [
        Analista(
            nome=a["nome"], senioridade=a["senioridade"], custo_hora=a["custo_hora"],
            disponibilidade=max(0.0, a["disponibilidade"] - horas_comprometidas.get(a["id"], 0)),
            ausente=a["ausente"], competencias=dict(niveis_por_analista.get(a["id"], {})), big5=dict(a["big5"]),
            id=a["id"],
        )
        for a in analistas_sel
    ] if not erros else []
    projetos_modelo = [
        Projeto(
            nome=p["nome"], receita=p["receita"], horas=p["horas"], nivel_min=p["nivel_min"],
            max_analistas=int(p["max_analistas"]), min_analistas=int(p["min_analistas"]),
            competencias_min=dict(reqs_por_projeto.get(p["id"], {})), big5_min=dict(p["big5_min"]),
            id=p["id"],
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
            st.info(f"Dados idênticos à última execução (#{ultima['id_execucao']}).")
        elif ultima is not None:
            st.warning(f"Dados alterados desde a última execução (#{ultima['id_execucao']}).")

    if st.button("Reprocessar / gerar prévia da alocação", type="primary", disabled=bool(erros)):
        with st.spinner("Resolvendo o modelo MILP (PuLP/CBC)..."):
            resultado = resolver_modelo(analistas_modelo, projetos_modelo, st.session_state.h_min)
        st.session_state.resultado = resultado

        with db.get_connection() as conn:
            id_execucao = db.salvar_execucao(
                conn, st.session_state.h_min, resultado, input_hash=input_hash,
            )
        st.session_state.ultima_execucao_id = id_execucao
        # Sobrescreve o valor guardado do selectbox de "Execucao" do Dashboard
        # (key="dashboard_execucao_sel") ANTES dele ser instanciado mais abaixo
        # no script: o parametro index= do st.selectbox so e' respeitado na
        # primeira vez que o widget e' criado - em reruns seguintes o widget
        # mantem o valor anterior por causa da key, entao sem isso o painel de
        # detalhe continuava mostrando a execucao antiga apos gerar uma nova.
        st.session_state["dashboard_execucao_sel"] = id_execucao
        st.success(f"Prévia #{id_execucao} gerada. Veja o histórico abaixo para confirmar.")


# =====================================================================
# Página · Dashboard de Resultados
# =====================================================================

def pagina_dashboard():
    st.title("Dashboard de Resultados")

    with st.expander("Gerar nova alocação"):
        _secao_geracao()

    with db.get_connection() as conn:
        execucoes = db.list_execucoes(conn)

    if not execucoes:
        st.info("Nenhuma execução registrada ainda. Gere uma prévia acima.")
        return

    st.dataframe(
        pd.DataFrame([
            {
                "ID": e["id_execucao"], "Data": e["executado_em"], "Situação": e["situacao"],
                "Lucro líquido (R$)": e["lucro_liquido"], "Receita (R$)": e["receita_total"],
            }
            for e in execucoes
        ]),
        use_container_width=True, hide_index=True,
    )

    st.subheader("Detalhe da execução")
    opcoes_ids = [e["id_execucao"] for e in execucoes]
    default_id = st.session_state.ultima_execucao_id if st.session_state.ultima_execucao_id in opcoes_ids else opcoes_ids[0]
    id_execucao_sel = st.selectbox(
        "Execução", options=opcoes_ids, index=opcoes_ids.index(default_id),
        format_func=lambda i: f"#{i}", key="dashboard_execucao_sel",
    )

    with db.get_connection() as conn:
        execucao = db.get_execucao(conn, id_execucao_sel)
        alocacoes_db = db.list_alocacoes_execucao(conn, id_execucao_sel)

    with st.container(border=True):
        if execucao["situacao"] == db.SITUACAO_CONFIRMADA:
            col_status, col_limpar, col_encerrar = st.columns([3, 1, 1])
        else:
            col_status, col_encerrar = st.columns([4, 1])
            col_limpar = None
        col_status.markdown(f"**Situação:** {execucao['situacao']}  ·  **Status do solver:** {execucao['status']}")
        if execucao["situacao"] == db.SITUACAO_CANDIDATA:
            if col_encerrar.button("Escolher esta alocação", type="primary", key="btn_confirmar", use_container_width=True):
                with db.get_connection() as conn:
                    db.set_situacao_execucao(conn, id_execucao_sel, db.SITUACAO_CONFIRMADA)
                st.success("Alocação confirmada.")
                st.rerun()
        elif execucao["situacao"] == db.SITUACAO_CONFIRMADA:
            if col_limpar.button("Limpar alocação escolhida", key="btn_limpar", use_container_width=True):
                with db.get_connection() as conn:
                    db.set_situacao_execucao(conn, id_execucao_sel, db.SITUACAO_CANDIDATA)
                st.success("Confirmação desfeita. A execução voltou a ser uma prévia e as horas foram liberadas.")
                st.rerun()
            if col_encerrar.button("Encerrar alocação", key="btn_encerrar", use_container_width=True):
                with db.get_connection() as conn:
                    db.set_situacao_execucao(conn, id_execucao_sel, db.SITUACAO_ENCERRADA)
                st.success("Alocação encerrada. As horas dela foram liberadas.")
                st.rerun()
        else:
            col_encerrar.info("Encerrada")

    if not execucao["viavel"]:
        st.error(f"Execução inviável (status do solver: {execucao['status']}).")
        if execucao["tempo_processamento_s"] is not None:
            st.caption(f"Tempo de processamento CBC (s): {execucao['tempo_processamento_s']:.3f}")
        return

    margem = (execucao["lucro_liquido"] / execucao["receita_total"] * 100) if execucao["receita_total"] else 0.0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Lucro líquido", f"R$ {execucao['lucro_liquido']:,.2f}", f"{margem:.1f}% da receita")
    k2.metric("Receita total", f"R$ {execucao['receita_total']:,.2f}")
    k3.metric("Custo total", f"R$ {execucao['custo_total']:,.2f}")
    k4.metric("Projetos aceitos", f"{len({a['projeto_nome'] for a in alocacoes_db})}")

    k5, k6 = st.columns(2)
    taxa_ocupacao = execucao["taxa_ocupacao_equipe"]
    tempo_cbc = execucao["tempo_processamento_s"]
    k5.metric("Taxa de Ocupação da Equipe (%)", f"{taxa_ocupacao:.1f}%" if taxa_ocupacao is not None else "—")
    k6.metric("Tempo de Processamento CBC (s)", f"{tempo_cbc:.3f}" if tempo_cbc is not None else "—")

    resultado_sessao = st.session_state.resultado
    tem_detalhe_sessao = resultado_sessao is not None and st.session_state.ultima_execucao_id == id_execucao_sel

    if tem_detalhe_sessao:
        st.subheader("Distribuição de horas por analista")
        st.dataframe(
            pd.DataFrame([
                {"Analista": r.nome, "Horas alocadas": r.horas_alocadas, "Disponíveis (rodada)": r.disponibilidade,
                 "Utilização": r.utilizacao * 100}
                for r in resultado_sessao.resumo_analistas
            ]),
            use_container_width=True, hide_index=True,
            column_config={
                "Utilização": st.column_config.ProgressColumn(
                    "Utilização", min_value=0, max_value=100, format="%.0f%%",
                ),
            },
        )

    def _rotulo_ativa(a):
        if execucao["situacao"] == db.SITUACAO_CANDIDATA:
            return "— (prévia não confirmada)"
        if execucao["situacao"] == db.SITUACAO_ENCERRADA:
            return "Não (execução encerrada)"
        return "Sim" if a["ativa"] else "Não (prazo do projeto encerrado)"

    st.subheader("Alocação detalhada")
    if alocacoes_db:
        st.dataframe(
            pd.DataFrame([
                {
                    "Analista": a["analista_nome"], "Projeto": a["projeto_nome"],
                    "Horas": a["horas"], "Custo (R$)": a["custo"], "Receita gerada (R$)": a["receita"],
                    "Conta na disponibilidade": _rotulo_ativa(a),
                }
                for a in alocacoes_db
            ]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Nenhuma alocação realizada.")

    st.subheader("Projetos aceitos e recusados")
    if tem_detalhe_sessao:
        for nome in resultado_sessao.aceitos:
            st.success(f"Aceito — {nome}")
        for nome, motivo in resultado_sessao.recusados:
            st.warning(f"Recusado — {nome}: {motivo}")
    else:
        for nome in sorted({a["projeto_nome"] for a in alocacoes_db}):
            st.success(f"Aceito — {nome}")
        st.caption("Motivos de recusa só ficam disponíveis para a execução mais recente da sessão.")

    st.subheader("Exportação do relatório")

    def _montar_relatorio_txt() -> str:
        tempo_cbc = execucao["tempo_processamento_s"]
        tempo_cbc_fmt = f"{tempo_cbc:.3f}s" if tempo_cbc is not None else "—"
        linhas = [
            "RELATÓRIO DE ALOCAÇÃO ÓTIMA DE ANALISTAS",
            "Sistema de Apoio à Decisão - Programação Linear Inteira Mista (PuLP/CBC)",
            "=" * 60,
            f"Execução #{execucao['id_execucao']} - {execucao['executado_em']}",
            f"Situação: {execucao['situacao']}",
            f"Parâmetro h_min: {execucao['h_min']}h",
            f"Tempo de processamento CBC: {tempo_cbc_fmt}",
            "",
            "1. RESULTADO GERAL", "-" * 60,
        ]
        if not execucao["viavel"]:
            linhas.append(f"Modelo inviável (status: {execucao['status']}).")
        else:
            taxa_ocupacao = execucao["taxa_ocupacao_equipe"]
            taxa_ocupacao_fmt = f"{taxa_ocupacao:.1f}%" if taxa_ocupacao is not None else "—"
            linhas += [
                f"Lucro líquido total: R$ {execucao['lucro_liquido']:,.2f}",
                f"Receita total: R$ {execucao['receita_total']:,.2f}",
                f"Custo total alocado: R$ {execucao['custo_total']:,.2f}",
                f"Taxa de ocupação da equipe: {taxa_ocupacao_fmt}",
                "", "2. ALOCAÇÃO DETALHADA", "-" * 60,
            ]
            if alocacoes_db:
                for a in alocacoes_db:
                    linhas.append(
                        f"- {a['analista_nome']} -> {a['projeto_nome']}: {a['horas']:.1f}h, "
                        f"custo R$ {a['custo']:,.2f}, receita gerada R$ {a['receita']:,.2f}"
                    )
            else:
                linhas.append("(nenhuma alocação realizada)")
            linhas += ["", "3. PROJETOS ACEITOS E RECUSADOS", "-" * 60]
            if tem_detalhe_sessao:
                for nome in resultado_sessao.aceitos:
                    linhas.append(f"- Aceito — {nome}")
                for nome, motivo in resultado_sessao.recusados:
                    linhas.append(f"- Recusado — {nome}: {motivo}")
            else:
                for nome in sorted({a["projeto_nome"] for a in alocacoes_db}):
                    linhas.append(f"- Aceito — {nome}")
                linhas.append(
                    "(motivos de recusa não disponíveis: só ficam registrados na "
                    "sessão em que a execução foi gerada)"
                )
        linhas += [
            "", "4. NOTA METODOLÓGICA", "-" * 60,
            "Resultado obtido pela resolução exata do modelo de Programação Linear "
            "Inteira Mista via solver CBC (branch-and-cut), através da biblioteca PuLP. "
            "Disponibilidade de cada analista desconta horas já comprometidas em "
            "execuções confirmadas (soma cumulativa, liberada só ao encerrar uma execução).",
        ]
        return "\n".join(linhas)

    st.download_button(
        "Baixar relatório (.txt)", data=_montar_relatorio_txt(),
        file_name=f"relatorio-execucao-{execucao['id_execucao']}.txt", mime="text/plain",
    )


# =====================================================================
# Navegação
# =====================================================================

pg = st.navigation([
    st.Page(pagina_analistas, title="Cadastro de Analistas", icon=":material/person:"),
    st.Page(pagina_projetos, title="Cadastro de Projetos", icon=":material/folder:"),
    st.Page(pagina_habilidades, title="Cadastro de Habilidades Técnicas", icon=":material/star:"),
    st.Page(pagina_dashboard, title="Dashboard de Resultados", icon=":material/bar_chart:"),
])
pg.run()
