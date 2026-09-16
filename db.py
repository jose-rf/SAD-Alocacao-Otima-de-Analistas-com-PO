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
# existia. O fluxo candidata -> confirmada -> encerrada (disponibilidade
# efetiva = Di - horas em execucoes CONFIRMADAS, calculada dinamicamente, sem
# coluna redundante) usa um campo proprio, `situacao`, pra nao colidir com o
# status do solver. As horas comprometidas sao cumulativas (somam todas as
# execucoes confirmadas do analista, sem segmentar por periodo/mes) - so'
# diminuem quando o gestor encerra explicitamente uma alocacao confirmada,
# liberando aquelas horas para as proximas rodadas. `periodo_referencia`
# (coluna legada, sempre NULL a partir desta versao) deixou de ser usada.

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
SITUACAO_ENCERRADA = "encerrada"

# Teto de disponibilidade mensal: 44h semanais (art. 58 CLT), convencao
# padrao de RH para jornada integral. Constante fixa - nao depende do
# calendario do mes.
TETO_HORAS_MENSAIS_CLT = 220


def validar_disponibilidade(horas_informadas: float) -> float:
    if horas_informadas > TETO_HORAS_MENSAIS_CLT:
        raise ValueError(
            f"Disponibilidade nao pode ultrapassar {TETO_HORAS_MENSAIS_CLT}h/mes (teto CLT)."
        )
    return horas_informadas

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
    prazo_semanas   INTEGER NOT NULL DEFAULT 4,
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
    input_hash          TEXT,
    confirmado_em       TEXT
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

    cols_projetos = _column_names(conn, "projetos")
    if "prazo_semanas" not in cols_projetos:
        conn.execute("ALTER TABLE projetos ADD COLUMN prazo_semanas INTEGER NOT NULL DEFAULT 4")

    cols_execucoes = _column_names(conn, "execucoes")
    if "situacao" not in cols_execucoes:
        conn.execute(f"ALTER TABLE execucoes ADD COLUMN situacao TEXT NOT NULL DEFAULT '{SITUACAO_CANDIDATA}'")
    if "periodo_referencia" not in cols_execucoes:
        conn.execute("ALTER TABLE execucoes ADD COLUMN periodo_referencia TEXT")
    if "input_hash" not in cols_execucoes:
        conn.execute("ALTER TABLE execucoes ADD COLUMN input_hash TEXT")
    if "confirmado_em" not in cols_execucoes:
        conn.execute("ALTER TABLE execucoes ADD COLUMN confirmado_em TEXT")


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
    dados = {"prazo_semanas": 4, **dados}
    cur = conn.execute(
        """INSERT INTO projetos
           (nome, receita, horas, nivel_min, max_analistas, min_analistas, prazo_semanas,
            com_min, col_min, org_min, ada_min, est_min)
           VALUES (:nome, :receita, :horas, :nivel_min, :max_analistas, :min_analistas, :prazo_semanas,
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
             prazo_semanas = :prazo_semanas,
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
            None,
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
                a.id_analista,
                a.id_projeto,
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
    if situacao == SITUACAO_CONFIRMADA:
        # confirmado_em e' o marco a partir do qual o prazo (prazo_semanas)
        # de cada projeto da execucao passa a contar (ver
        # _EXPIRACAO_SQL). So' e' gravado na transicao pra CONFIRMADA -
        # o botao que dispara essa transicao so aparece uma vez por
        # execucao, entao nunca e' sobrescrito.
        conn.execute(
            "UPDATE execucoes SET situacao = ?, confirmado_em = ? WHERE id_execucao = ?",
            (situacao, datetime.utcnow().isoformat(timespec="seconds"), id_execucao),
        )
    else:
        conn.execute(
            "UPDATE execucoes SET situacao = ? WHERE id_execucao = ?", (situacao, id_execucao)
        )


# Expressao SQL reutilizada: 1 se a alocacao ainda conta como hora
# comprometida, 0 se ja' passou do prazo do projeto (prazo_semanas contado a
# partir de execucoes.confirmado_em) ou se a execucao nao esta' confirmada.
# Prazo automatico por data (registrado em 06/09/2026): projetos tem fim, e
# uma vez o prazo estourado as horas do analista voltam a ficar livres sem
# precisar de acao manual do gestor. Compara em UTC (confirmado_em e'
# gravado com datetime.utcnow()) pra' bater com datetime('now') do SQLite.
# Se o projeto foi excluido do cadastro (p.id_projeto IS NULL), mantem
# contando por seguranca (nao da pra saber o prazo original).
_EXPIRACAO_SQL = """
    CASE
        WHEN e.situacao != 'confirmada' THEN 0
        WHEN e.confirmado_em IS NULL THEN 1
        WHEN p.id_projeto IS NULL THEN 1
        WHEN datetime(e.confirmado_em, '+' || (p.prazo_semanas * 7) || ' days') > datetime('now') THEN 1
        ELSE 0
    END
"""


def list_alocacoes_execucao(conn: sqlite3.Connection, id_execucao: int) -> List[sqlite3.Row]:
    return conn.execute(
        f"""SELECT al.*, ({_EXPIRACAO_SQL}) AS ativa
            FROM alocacoes al
            JOIN execucoes e ON al.id_execucao = e.id_execucao
            LEFT JOIN projetos p ON al.id_projeto = p.id_projeto
            WHERE al.id_execucao = ?
            ORDER BY al.id_alocacao""",
        (id_execucao,),
    ).fetchall()


def get_horas_comprometidas(conn: sqlite3.Connection, id_analista: int) -> float:
    # Soma cumulativa das horas do analista em execucoes CONFIRMADAS cujo
    # prazo do projeto ainda nao passou (Di_efetivo = Di - horas
    # comprometidas). Uma execucao ENCERRADA manualmente, ou cujo prazo ja'
    # expirou automaticamente, nao entra nessa soma. Calculado sob demanda a
    # partir de alocacoes+execucoes+projetos, sem coluna redundante (mesma
    # logica de normalizacao da secao 7.4.5 do TCC).
    row = conn.execute(
        f"""SELECT COALESCE(SUM(al.horas), 0) AS total
            FROM alocacoes al
            JOIN execucoes e ON al.id_execucao = e.id_execucao
            LEFT JOIN projetos p ON al.id_projeto = p.id_projeto
            WHERE al.id_analista = ? AND ({_EXPIRACAO_SQL}) = 1""",
        (id_analista,),
    ).fetchone()
    return row["total"] or 0.0


def list_projetos_ja_confirmados(conn: sqlite3.Connection) -> set:
    # Projetos com pelo menos uma alocacao numa execucao CONFIRMADA. Usado
    # so' pra' definir a selecao PADRAO de uma nova rodada de otimizacao
    # (pagina "Geracao da Alocacao" no Dashboard): por padrao, um projeto
    # que ja' foi confirmado nao entra de novo, pra' nao reorganizar decisoes
    # ja' tomadas so' porque o gestor quer alocar um projeto novo. O gestor
    # ainda pode marcar manualmente um projeto confirmado se quiser
    # reconsiderar (ex.: projeto encerrado e quer recomecar).
    rows = conn.execute(
        """SELECT DISTINCT al.id_projeto
           FROM alocacoes al
           JOIN execucoes e ON al.id_execucao = e.id_execucao
           WHERE e.situacao = ? AND al.id_projeto IS NOT NULL""",
        (SITUACAO_CONFIRMADA,),
    ).fetchall()
    return {r["id_projeto"] for r in rows}


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
             max_analistas=3, min_analistas=1, prazo_semanas=8,
             com_min=50, col_min=0, org_min=50, ada_min=0, est_min=0,
             reqs={"Tributario": 80, "Compliance": 70}),
        dict(nome="Auditoria Interna", receita=60000.0, horas=160.0, nivel_min="Senior",
             max_analistas=2, min_analistas=1, prazo_semanas=6,
             com_min=0, col_min=0, org_min=50, ada_min=0, est_min=50,
             reqs={"Auditoria": 90, "SAP": 60}),
        dict(nome="Implantacao ERP", receita=140000.0, horas=400.0, nivel_min="Junior",
             max_analistas=4, min_analistas=2, prazo_semanas=16,
             com_min=0, col_min=50, org_min=0, ada_min=50, est_min=0,
             reqs={"SAP": 85, "Power BI": 75}),
    ]
    for p in projetos:
        reqs = p.pop("reqs")
        id_projeto = insert_projeto(conn, p)
        for nome_skill, nivel in reqs.items():
            set_requisito_projeto(conn, id_projeto, ids_habilidade[nome_skill], nivel)
