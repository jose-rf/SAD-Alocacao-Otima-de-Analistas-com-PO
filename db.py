# Persistencia SQLite do SAD de alocacao de analistas.
#
# Sete tabelas:
#   analistas, projetos                          - cadastros principais
#   habilidades                                   - catalogo global de competencias tecnicas
#   analista_habilidade, projeto_habilidade_requerida  - tabelas associativas (chave composta)
#   execucoes, alocacoes                          - historico de execucoes do modelo MILP
#
# Big Five (COM/COL/ORG/ADA/EST) fica como colunas nas proprias tabelas
# analistas/projetos por ser um perfil de tamanho fixo (5 dimensoes), nao um
# catalogo aberto como as habilidades tecnicas.
#
# `execucoes.status` guarda o status do SOLVER (Optimal/Infeasible/...) e ja
# existia. O fluxo candidata -> confirmada (secao 7.4.5 do TCC: disponibilidade
# efetiva = Di - horas em execucoes confirmadas, calculada dinamicamente, sem
# coluna redundante) usa um campo proprio, `situacao`, pra nao colidir com o
# status do solver. `periodo_referencia` (formato 'YYYY-MM') e' o mes/ano ao
# qual uma execucao confirmada se refere, usado tanto pro teto de disponibilidade
# por calendario quanto pro calculo de horas ja comprometidas nesse periodo.

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from optimization import TRAITS, ResultadoOtimizacao

DB_PATH = Path(__file__).parent / "alocacao.db"

SITUACAO_CANDIDATA = "candidata"
SITUACAO_CONFIRMADA = "confirmada"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analistas (
    id_analista     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL,
    cpf             TEXT NOT NULL DEFAULT '',
    senioridade     TEXT NOT NULL,
    custo_hora      REAL NOT NULL,
    disponibilidade REAL NOT NULL,
    ausente         INTEGER NOT NULL DEFAULT 0,
    com             REAL NOT NULL DEFAULT 50,
    col             REAL NOT NULL DEFAULT 50,
    org             REAL NOT NULL DEFAULT 50,
    ada             REAL NOT NULL DEFAULT 50,
    est             REAL NOT NULL DEFAULT 50
);

-- CPF e' chave do analista (unica quando preenchido), mas a UNIQUE fica num
-- indice parcial (nao inline na coluna): uma linha nova criada pelo botao
-- "+ Adicionar analista" comeca com cpf='' ate' o gestor preencher, e um
-- UNIQUE inline rejeitaria a segunda linha em branco.
CREATE UNIQUE INDEX IF NOT EXISTS idx_analistas_cpf ON analistas(cpf) WHERE cpf != '';

CREATE TABLE IF NOT EXISTS projetos (
    id_projeto      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL,
    receita         REAL NOT NULL,
    horas           REAL NOT NULL,
    nivel_min       TEXT NOT NULL,
    max_analistas   INTEGER NOT NULL DEFAULT 1,
    min_analistas   INTEGER NOT NULL DEFAULT 1,
    com_min         REAL NOT NULL DEFAULT 0,
    col_min         REAL NOT NULL DEFAULT 0,
    org_min         REAL NOT NULL DEFAULT 0,
    ada_min         REAL NOT NULL DEFAULT 0,
    est_min         REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS habilidades (
    id_habilidade   INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS analista_habilidade (
    id_analista     INTEGER NOT NULL REFERENCES analistas(id_analista) ON DELETE CASCADE,
    id_habilidade   INTEGER NOT NULL REFERENCES habilidades(id_habilidade) ON DELETE CASCADE,
    nivel           REAL NOT NULL,
    PRIMARY KEY (id_analista, id_habilidade)
);

CREATE TABLE IF NOT EXISTS projeto_habilidade_requerida (
    id_projeto      INTEGER NOT NULL REFERENCES projetos(id_projeto) ON DELETE CASCADE,
    id_habilidade   INTEGER NOT NULL REFERENCES habilidades(id_habilidade) ON DELETE CASCADE,
    nivel_minimo    REAL NOT NULL,
    PRIMARY KEY (id_projeto, id_habilidade)
);

CREATE TABLE IF NOT EXISTS execucoes (
    id_execucao         INTEGER PRIMARY KEY AUTOINCREMENT,
    executado_em        TEXT NOT NULL,
    h_min               REAL NOT NULL,
    status              TEXT NOT NULL,
    viavel              INTEGER NOT NULL,
    lucro_liquido       REAL,
    receita_total       REAL,
    custo_total         REAL,
    situacao            TEXT NOT NULL DEFAULT 'candidata',
    periodo_referencia  TEXT,
    input_hash          TEXT
);

CREATE TABLE IF NOT EXISTS alocacoes (
    id_alocacao     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_execucao     INTEGER NOT NULL REFERENCES execucoes(id_execucao) ON DELETE CASCADE,
    id_analista     INTEGER REFERENCES analistas(id_analista) ON DELETE SET NULL,
    id_projeto      INTEGER REFERENCES projetos(id_projeto) ON DELETE SET NULL,
    analista_nome   TEXT NOT NULL,
    projeto_nome    TEXT NOT NULL,
    horas           REAL NOT NULL,
    custo           REAL NOT NULL,
    receita         REAL NOT NULL
);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> set:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn: sqlite3.Connection) -> None:
    # ALTER TABLE ... ADD COLUMN pra bancos criados antes destes campos
    # existirem (CREATE TABLE IF NOT EXISTS nao adiciona coluna em tabela ja
    # existente). Idempotente: cada ALTER so' roda se a coluna ainda nao existe.
    cols_analistas = _column_names(conn, "analistas")
    if "cpf" not in cols_analistas:
        conn.execute("ALTER TABLE analistas ADD COLUMN cpf TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_analistas_cpf ON analistas(cpf) WHERE cpf != ''")

    cols_execucoes = _column_names(conn, "execucoes")
    if "situacao" not in cols_execucoes:
        conn.execute(f"ALTER TABLE execucoes ADD COLUMN situacao TEXT NOT NULL DEFAULT '{SITUACAO_CANDIDATA}'")
    if "periodo_referencia" not in cols_execucoes:
        conn.execute("ALTER TABLE execucoes ADD COLUMN periodo_referencia TEXT")
    if "input_hash" not in cols_execucoes:
        conn.execute("ALTER TABLE execucoes ADD COLUMN input_hash TEXT")


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)


# ── Habilidades (catalogo global) ────────────────────────────────────────────

def normalizar_nome_habilidade(nome: str) -> str:
    return " ".join(nome.strip().split())


def list_habilidades(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT * FROM habilidades ORDER BY nome").fetchall()


def add_habilidade(conn: sqlite3.Connection, nome: str) -> int:
    nome = normalizar_nome_habilidade(nome)
    if not nome:
        raise ValueError("Nome da habilidade nao pode ser vazio.")
    existente = conn.execute(
        "SELECT id_habilidade FROM habilidades WHERE nome = ? COLLATE NOCASE", (nome,)
    ).fetchone()
    if existente:
        raise ValueError(f"Ja existe uma habilidade chamada '{nome}' no catalogo.")
    cur = conn.execute("INSERT INTO habilidades (nome) VALUES (?)", (nome,))
    return cur.lastrowid


def rename_habilidade(conn: sqlite3.Connection, id_habilidade: int, novo_nome: str) -> None:
    novo_nome = normalizar_nome_habilidade(novo_nome)
    if not novo_nome:
        raise ValueError("Nome da habilidade nao pode ser vazio.")
    existente = conn.execute(
        "SELECT id_habilidade FROM habilidades WHERE nome = ? COLLATE NOCASE AND id_habilidade != ?",
        (novo_nome, id_habilidade),
    ).fetchone()
    if existente:
        raise ValueError(f"Ja existe uma habilidade chamada '{novo_nome}' no catalogo.")
    conn.execute("UPDATE habilidades SET nome = ? WHERE id_habilidade = ?", (novo_nome, id_habilidade))


def delete_habilidade(conn: sqlite3.Connection, id_habilidade: int) -> None:
    conn.execute("DELETE FROM habilidades WHERE id_habilidade = ?", (id_habilidade,))


# ── Analistas ─────────────────────────────────────────────────────────────────

def list_analistas(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT * FROM analistas ORDER BY id_analista").fetchall()


CPF_REGEX = r"^\d{3}\.\d{3}\.\d{3}-\d{2}$"


def cpf_valido(cpf: str) -> bool:
    return bool(re.match(CPF_REGEX, cpf.strip()))


def insert_analista(conn: sqlite3.Connection, dados: dict) -> int:
    dados = {"cpf": "", **dados}
    cur = conn.execute(
        """INSERT INTO analistas
           (nome, cpf, senioridade, custo_hora, disponibilidade, ausente, com, col, org, ada, est)
           VALUES (:nome, :cpf, :senioridade, :custo_hora, :disponibilidade, :ausente,
                   :com, :col, :org, :ada, :est)""",
        dados,
    )
    return cur.lastrowid


def update_analista(conn: sqlite3.Connection, id_analista: int, dados: dict) -> None:
    dados = {**dados, "id_analista": id_analista}
    conn.execute(
        """UPDATE analistas SET
             nome = :nome, cpf = :cpf, senioridade = :senioridade, custo_hora = :custo_hora,
             disponibilidade = :disponibilidade, ausente = :ausente,
             com = :com, col = :col, org = :org, ada = :ada, est = :est
           WHERE id_analista = :id_analista""",
        dados,
    )


def delete_analista(conn: sqlite3.Connection, id_analista: int) -> None:
    conn.execute("DELETE FROM analistas WHERE id_analista = ?", (id_analista,))


def get_niveis_analista(conn: sqlite3.Connection, id_analista: int) -> Dict[int, float]:
    rows = conn.execute(
        "SELECT id_habilidade, nivel FROM analista_habilidade WHERE id_analista = ?",
        (id_analista,),
    ).fetchall()
    return {r["id_habilidade"]: r["nivel"] for r in rows}


def set_nivel_analista(conn: sqlite3.Connection, id_analista: int, id_habilidade: int, nivel: float) -> None:
    conn.execute(
        """INSERT INTO analista_habilidade (id_analista, id_habilidade, nivel)
           VALUES (?, ?, ?)
           ON CONFLICT(id_analista, id_habilidade) DO UPDATE SET nivel = excluded.nivel""",
        (id_analista, id_habilidade, nivel),
    )


# ── Projetos ──────────────────────────────────────────────────────────────────

def list_projetos(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT * FROM projetos ORDER BY id_projeto").fetchall()


def insert_projeto(conn: sqlite3.Connection, dados: dict) -> int:
    cur = conn.execute(
        """INSERT INTO projetos
           (nome, receita, horas, nivel_min, max_analistas, min_analistas,
            com_min, col_min, org_min, ada_min, est_min)
           VALUES (:nome, :receita, :horas, :nivel_min, :max_analistas, :min_analistas,
                   :com_min, :col_min, :org_min, :ada_min, :est_min)""",
        dados,
    )
    return cur.lastrowid


def update_projeto(conn: sqlite3.Connection, id_projeto: int, dados: dict) -> None:
    dados = {**dados, "id_projeto": id_projeto}
    conn.execute(
        """UPDATE projetos SET
             nome = :nome, receita = :receita, horas = :horas, nivel_min = :nivel_min,
             max_analistas = :max_analistas, min_analistas = :min_analistas,
             com_min = :com_min, col_min = :col_min, org_min = :org_min,
             ada_min = :ada_min, est_min = :est_min
           WHERE id_projeto = :id_projeto""",
        dados,
    )


def delete_projeto(conn: sqlite3.Connection, id_projeto: int) -> None:
    conn.execute("DELETE FROM projetos WHERE id_projeto = ?", (id_projeto,))


def get_requisitos_projeto(conn: sqlite3.Connection, id_projeto: int) -> Dict[int, float]:
    rows = conn.execute(
        "SELECT id_habilidade, nivel_minimo FROM projeto_habilidade_requerida WHERE id_projeto = ?",
        (id_projeto,),
    ).fetchall()
    return {r["id_habilidade"]: r["nivel_minimo"] for r in rows}


def set_requisito_projeto(conn: sqlite3.Connection, id_projeto: int, id_habilidade: int, nivel_minimo: float) -> None:
    conn.execute(
        """INSERT INTO projeto_habilidade_requerida (id_projeto, id_habilidade, nivel_minimo)
           VALUES (?, ?, ?)
           ON CONFLICT(id_projeto, id_habilidade) DO UPDATE SET nivel_minimo = excluded.nivel_minimo""",
        (id_projeto, id_habilidade, nivel_minimo),
    )


# ── Execucoes / alocacoes (historico) ───────────────────────────────────────

def salvar_execucao(
    conn: sqlite3.Connection,
    h_min: float,
    resultado: "ResultadoOtimizacao",
    id_por_nome_analista: Dict[str, int],
    id_por_nome_projeto: Dict[str, int],
    periodo_referencia: Optional[str] = None,
    input_hash: Optional[str] = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO execucoes
           (executado_em, h_min, status, viavel, lucro_liquido, receita_total, custo_total,
            situacao, periodo_referencia, input_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(timespec="seconds"),
            h_min,
            resultado.status,
            int(resultado.viavel),
            resultado.lucro_liquido if resultado.viavel else None,
            resultado.receita_total if resultado.viavel else None,
            resultado.custo_total if resultado.viavel else None,
            SITUACAO_CANDIDATA,
            periodo_referencia,
            input_hash,
        ),
    )
    id_execucao = cur.lastrowid
    for a in resultado.alocacoes:
        conn.execute(
            """INSERT INTO alocacoes
               (id_execucao, id_analista, id_projeto, analista_nome, projeto_nome, horas, custo, receita)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id_execucao,
                id_por_nome_analista.get(a.analista),
                id_por_nome_projeto.get(a.projeto),
                a.analista,
                a.projeto,
                a.horas,
                a.custo,
                a.receita,
            ),
        )
    return id_execucao


def list_execucoes(conn: sqlite3.Connection, limit: int = 20) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM execucoes ORDER BY id_execucao DESC LIMIT ?", (limit,)
    ).fetchall()


def get_execucao(conn: sqlite3.Connection, id_execucao: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM execucoes WHERE id_execucao = ?", (id_execucao,)
    ).fetchone()


def get_ultima_execucao(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM execucoes ORDER BY id_execucao DESC LIMIT 1"
    ).fetchone()


def set_situacao_execucao(conn: sqlite3.Connection, id_execucao: int, situacao: str) -> None:
    conn.execute(
        "UPDATE execucoes SET situacao = ? WHERE id_execucao = ?", (situacao, id_execucao)
    )


def list_alocacoes_execucao(conn: sqlite3.Connection, id_execucao: int) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM alocacoes WHERE id_execucao = ? ORDER BY id_alocacao", (id_execucao,)
    ).fetchall()


def get_horas_comprometidas(conn: sqlite3.Connection, id_analista: int, periodo_referencia: str) -> float:
    # Soma as horas do analista em execucoes ja' CONFIRMADAS no mesmo periodo
    # de referencia (Equacao 2 efetiva: Di_efetivo = Di - horas comprometidas).
    # Calculado sob demanda a partir de alocacoes+execucoes, sem coluna
    # redundante (mesma logica de normalizacao da secao 7.4.5 do TCC).
    row = conn.execute(
        """SELECT COALESCE(SUM(al.horas), 0) AS total
           FROM alocacoes al
           JOIN execucoes e ON al.id_execucao = e.id_execucao
           WHERE al.id_analista = ? AND e.situacao = ? AND e.periodo_referencia = ?""",
        (id_analista, SITUACAO_CONFIRMADA, periodo_referencia),
    ).fetchone()
    return row["total"] or 0.0


# ── Dados de exemplo (seed inicial, so' roda se o banco estiver vazio) ──────

def seed_dados_exemplo(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) AS n FROM analistas").fetchone()["n"] > 0:
        return

    habilidades_nomes = ["Tributario", "Auditoria", "SAP", "Power BI", "Compliance"]
    ids_habilidade = {nome: add_habilidade(conn, nome) for nome in habilidades_nomes}

    analistas = [
        dict(nome="Ana Souza", cpf="111.111.111-11", senioridade="Senior", custo_hora=140.0, disponibilidade=160.0,
             ausente=0, com=80, col=60, org=75, ada=55, est=70,
             skills={"Tributario": 85, "Auditoria": 90}),
        dict(nome="Bruno Lima", cpf="222.222.222-22", senioridade="Pleno", custo_hora=95.0, disponibilidade=150.0,
             ausente=0, com=65, col=70, org=60, ada=80, est=50,
             skills={"SAP": 70, "Power BI": 80}),
        dict(nome="Camila Rocha", cpf="333.333.333-33", senioridade="Senior", custo_hora=130.0, disponibilidade=150.0,
             ausente=0, com=75, col=55, org=85, ada=60, est=80,
             skills={"Auditoria": 95, "SAP": 65}),
    ]
    for a in analistas:
        skills = a.pop("skills")
        id_analista = insert_analista(conn, a)
        for nome_skill, nivel in skills.items():
            set_nivel_analista(conn, id_analista, ids_habilidade[nome_skill], nivel)

    projetos = [
        dict(nome="Consultoria Fiscal", receita=90000.0, horas=240.0, nivel_min="Pleno",
             max_analistas=3, min_analistas=1, com_min=50, col_min=0, org_min=50, ada_min=0, est_min=0,
             reqs={"Tributario": 80, "Compliance": 70}),
        dict(nome="Auditoria Interna", receita=60000.0, horas=160.0, nivel_min="Senior",
             max_analistas=2, min_analistas=1, com_min=0, col_min=0, org_min=50, ada_min=0, est_min=50,
             reqs={"Auditoria": 90, "SAP": 60}),
        dict(nome="Implantacao ERP", receita=140000.0, horas=400.0, nivel_min="Junior",
             max_analistas=4, min_analistas=2, com_min=0, col_min=50, org_min=0, ada_min=50, est_min=0,
             reqs={"SAP": 85, "Power BI": 75}),
    ]
    for p in projetos:
        reqs = p.pop("reqs")
        id_projeto = insert_projeto(conn, p)
        for nome_skill, nivel in reqs.items():
            set_requisito_projeto(conn, id_projeto, ids_habilidade[nome_skill], nivel)
