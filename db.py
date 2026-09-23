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

import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

try:
    import libsql_client
except ImportError:
    libsql_client = None

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

from optimization import TRAITS, ResultadoOtimizacao

DB_PATH = Path(__file__).parent / "alocacao.db"

# Persistencia remota opcional (Postgres/Supabase ou Turso/libSQL) - contorna
# a limitacao do Streamlit Community Cloud de nao ter disco persistente (o
# container e' recriado do zero a cada rebuild/reboot, apagando qualquer
# arquivo local como o alocacao.db). Prioridade: SUPABASE_DB_URL/DATABASE_URL
# (Postgres) > TURSO_DATABASE_URL+TURSO_AUTH_TOKEN (libSQL) > arquivo SQLite
# local (comportamento de sempre, usado quando nada disso esta' configurado -
# nao quebra nenhum uso local/de teste existente). Essas variaveis vem de
# os.environ, que tanto env vars comuns quanto st.secrets do Streamlit
# preenchem (ver bridge no topo do app.py).
#
# IntegrityError abaixo unifica a excecao de violacao de UNIQUE (ex.: CPF
# duplicado) entre os tres backends, ja que sqlite3.IntegrityError,
# psycopg2.IntegrityError e libsql_client.LibsqlError sao classes
# completamente diferentes - o resto do codigo (app.py) captura
# db.IntegrityError em vez de uma classe especifica de driver.
_erros_integridade = [sqlite3.IntegrityError]
if psycopg2 is not None:
    _erros_integridade.append(psycopg2.IntegrityError)
if libsql_client is not None:
    _erros_integridade.append(libsql_client.LibsqlError)
IntegrityError = tuple(_erros_integridade)

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
    id_analista         INTEGER NOT NULL REFERENCES analistas(id_analista) ON DELETE CASCADE,
    id_habilidade       INTEGER NOT NULL REFERENCES habilidades(id_habilidade) ON DELETE CASCADE,
    nivel_proficiencia  REAL NOT NULL,
    PRIMARY KEY (id_analista, id_habilidade)
);

CREATE TABLE IF NOT EXISTS projeto_habilidade_requerida (
    id_projeto      INTEGER NOT NULL REFERENCES projetos(id_projeto) ON DELETE CASCADE,
    id_habilidade   INTEGER NOT NULL REFERENCES habilidades(id_habilidade) ON DELETE CASCADE,
    nivel_exigido   REAL NOT NULL,
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
    situacao              TEXT NOT NULL DEFAULT 'candidata',
    periodo_referencia    TEXT,
    input_hash            TEXT,
    data_confirmacao      TEXT,
    tempo_processamento_s REAL,
    taxa_ocupacao_equipe  REAL
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

-- Flag persistente de "os dados de exemplo ja foram carregados alguma vez".
-- Existe so' pra' impedir que seed_dados_exemplo() rode de novo quando o
-- gestor esvazia o cadastro de proposito (ex.: apaga todos os analistas pra
-- comecar do zero) - sem essa marca, o sistema nao teria como distinguir
-- "banco realmente vazio pela primeira vez" de "gestor esvaziou de proposito",
-- e recolocava os dados de exemplo sozinho a cada rerun (comportamento
-- indesejado reportado pelo gestor em 20/09/2026).
CREATE TABLE IF NOT EXISTS app_meta (
    chave   TEXT PRIMARY KEY,
    valor   TEXT NOT NULL
);
"""

# Mesmo schema, dialeto Postgres (Supabase): SERIAL no lugar de
# INTEGER...AUTOINCREMENT, e' sem "COLLATE NOCASE" (Postgres nao tem - o
# unico uso, o catalogo de habilidades, vira indice funcional sobre
# LOWER(nome) em vez de UNIQUE inline). O resto (tipos REAL/TEXT/INTEGER,
# REFERENCES...ON DELETE, indice parcial com WHERE, PRIMARY KEY composta)
# e' identico nos dois bancos.
_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS analistas (
    id_analista     SERIAL PRIMARY KEY,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_analistas_cpf ON analistas(cpf) WHERE cpf != '';

CREATE TABLE IF NOT EXISTS projetos (
    id_projeto      SERIAL PRIMARY KEY,
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
    id_habilidade   SERIAL PRIMARY KEY,
    nome            TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_habilidades_nome_ci ON habilidades (LOWER(nome));

CREATE TABLE IF NOT EXISTS analista_habilidade (
    id_analista         INTEGER NOT NULL REFERENCES analistas(id_analista) ON DELETE CASCADE,
    id_habilidade       INTEGER NOT NULL REFERENCES habilidades(id_habilidade) ON DELETE CASCADE,
    nivel_proficiencia  REAL NOT NULL,
    PRIMARY KEY (id_analista, id_habilidade)
);

CREATE TABLE IF NOT EXISTS projeto_habilidade_requerida (
    id_projeto      INTEGER NOT NULL REFERENCES projetos(id_projeto) ON DELETE CASCADE,
    id_habilidade   INTEGER NOT NULL REFERENCES habilidades(id_habilidade) ON DELETE CASCADE,
    nivel_exigido   REAL NOT NULL,
    PRIMARY KEY (id_projeto, id_habilidade)
);

CREATE TABLE IF NOT EXISTS execucoes (
    id_execucao           SERIAL PRIMARY KEY,
    executado_em          TEXT NOT NULL,
    h_min                 REAL NOT NULL,
    status                TEXT NOT NULL,
    viavel                INTEGER NOT NULL,
    lucro_liquido         REAL,
    receita_total         REAL,
    custo_total           REAL,
    situacao              TEXT NOT NULL DEFAULT 'candidata',
    periodo_referencia    TEXT,
    input_hash            TEXT,
    data_confirmacao      TEXT,
    tempo_processamento_s REAL,
    taxa_ocupacao_equipe  REAL
);

CREATE TABLE IF NOT EXISTS alocacoes (
    id_alocacao     SERIAL PRIMARY KEY,
    id_execucao     INTEGER NOT NULL REFERENCES execucoes(id_execucao) ON DELETE CASCADE,
    id_analista     INTEGER REFERENCES analistas(id_analista) ON DELETE SET NULL,
    id_projeto      INTEGER REFERENCES projetos(id_projeto) ON DELETE SET NULL,
    analista_nome   TEXT NOT NULL,
    projeto_nome    TEXT NOT NULL,
    horas           REAL NOT NULL,
    custo           REAL NOT NULL,
    receita         REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS app_meta (
    chave   TEXT PRIMARY KEY,
    valor   TEXT NOT NULL
);
"""


def _pg_config():
    return os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")


def _turso_config():
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    return (url, token) if url and token else None


_PG_PARAM_RE = re.compile(r"(?<!:):(\w+)")  # nao casa "::" (cast do Postgres, ex.: CAST evita mas ainda assim protegido)
_PG_PK_POR_TABELA = {
    "habilidades": "id_habilidade",
    "analistas": "id_analista",
    "projetos": "id_projeto",
    "execucoes": "id_execucao",
    "alocacoes": "id_alocacao",
}
_PG_INSERT_TABELA_RE = re.compile(r"(?is)^\s*INSERT\s+INTO\s+(\w+)")


def _translate_sql_for_pg(sql: str) -> str:
    # db.py escreve as queries em sintaxe SQLite (placeholder posicional '?'
    # e nomeado ':nome'); psycopg2 usa '%s' e '%(nome)s'. So' texto, nao mexe
    # nos valores dos parametros - passados separados em todo lugar.
    sql = _PG_PARAM_RE.sub(r"%(\1)s", sql)
    return sql.replace("?", "%s")


class _PgCursor:
    # Mesma ideia do _LibsqlCursor: imita fetchone/fetchall/iteracao/lastrowid
    # o suficiente pro resto do db.py funcionar sem saber que esta' falando
    # com Postgres. Postgres nao tem cursor.lastrowid (conceito proprio do
    # SQLite) - _PgConnection.execute() detecta um INSERT INTO <tabela
    # conhecida> sem RETURNING explicito e acrescenta "RETURNING <pk>"; o
    # valor devolvido vira o lastrowid aqui.
    def __init__(self, cur, is_lastrowid_insert=False):
        if cur.description is not None:
            self._rows = cur.fetchall()
        else:
            self._rows = []
        self.lastrowid = (
            list(self._rows[0].values())[0] if is_lastrowid_insert and self._rows else None
        )
        cur.close()

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _PgConnection:
    # Adaptador equivalente ao _LibsqlConnection, pra Postgres (psycopg2) via
    # Supabase. Ao contrario do libsql_client, uma unica conexao psycopg2
    # mantem uma transacao real ao longo de todo o bloco `with
    # get_connection() as conn:` (varios cursor() na mesma connection
    # compartilham a mesma transacao) - falha no meio desfaz tudo, igual
    # sqlite3. commit()/close() sao passthrough direto pra connection real.
    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=None):
        translated = _translate_sql_for_pg(sql)
        m = _PG_INSERT_TABELA_RE.match(sql)
        is_lastrowid_insert = False
        if m and "returning" not in translated.lower():
            pk = _PG_PK_POR_TABELA.get(m.group(1).lower())
            if pk:
                translated = translated.rstrip().rstrip(";") + f" RETURNING {pk}"
                is_lastrowid_insert = True
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(translated, params if params is not None else ())
        return _PgCursor(cur, is_lastrowid_insert=is_lastrowid_insert)

    def executescript(self, script):
        cur = self._conn.cursor()
        cur.execute(script)
        cur.close()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


class _LibsqlCursor:
    # Imita o suficiente de sqlite3.Cursor pro resto do db.py funcionar sem
    # precisar saber se esta' falando com SQLite local ou libSQL remoto:
    # fetchone/fetchall, iteracao direta (usado em _column_names) e lastrowid.
    # As linhas do libsql_client ja suportam row["coluna"] e row[indice],
    # equivalente ao sqlite3.Row usado no resto do arquivo.
    def __init__(self, result_set):
        self._rows = list(result_set.rows)
        self.lastrowid = result_set.last_insert_rowid

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


def _split_sql_statements(script: str) -> List[str]:
    # _SCHEMA so' tem CREATE TABLE/INDEX simples (sem ';' dentro de strings,
    # triggers ou blocos PL/pgSQL), entao dividir por ';' e' seguro aqui.
    return [s.strip() for s in script.split(";") if s.strip()]


class _LibsqlConnection:
    # Adaptador minimo pra' get_connection() poder devolver algo com a mesma
    # API usada em todo o resto do db.py (conn.execute(...).fetchone()/
    # fetchall(), conn.executescript(...), cur.lastrowid) quando o banco e'
    # um libSQL remoto (Turso) em vez de um arquivo SQLite local. libsql_client
    # ja faz autocommit por statement (nao tem .commit()), entao commit() aqui
    # e' so' um no-op pra manter a mesma interface do bloco `with` abaixo.
    def __init__(self, client):
        self._client = client

    def execute(self, sql, params=None):
        return _LibsqlCursor(self._client.execute(sql, params if params is not None else []))

    def executescript(self, script):
        self._client.batch(_split_sql_statements(script))

    def commit(self):
        pass

    def close(self):
        self._client.close()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    pg_url = _pg_config()
    turso = _turso_config()
    if pg_url:
        if psycopg2 is None:
            raise RuntimeError(
                "SUPABASE_DB_URL/DATABASE_URL configurado, mas o pacote psycopg2 "
                "nao esta instalado (adicione 'psycopg2-binary' ao requirements.txt)."
            )
        conn = _PgConnection(psycopg2.connect(pg_url))
    elif turso:
        if libsql_client is None:
            raise RuntimeError(
                "TURSO_DATABASE_URL/TURSO_AUTH_TOKEN configurados, mas o pacote "
                "libsql-client nao esta instalado (adicione 'libsql-client' ao "
                "requirements.txt)."
            )
        url, token = turso
        conn = _LibsqlConnection(libsql_client.create_client_sync(url=url, auth_token=token))
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> set:
    if isinstance(conn, _PgConnection):
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,)
        )
        return {r["column_name"] for r in rows}
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
    if "data_confirmacao" not in cols_execucoes:
        if "confirmado_em" in cols_execucoes:
            # renomeado pra bater com o nome usado no texto do TCC (nao e'
            # coluna nova - banco antigo so' precisa trocar o nome)
            conn.execute("ALTER TABLE execucoes RENAME COLUMN confirmado_em TO data_confirmacao")
        else:
            conn.execute("ALTER TABLE execucoes ADD COLUMN data_confirmacao TEXT")
    if "tempo_processamento_s" not in cols_execucoes:
        conn.execute("ALTER TABLE execucoes ADD COLUMN tempo_processamento_s REAL")
    if "taxa_ocupacao_equipe" not in cols_execucoes:
        conn.execute("ALTER TABLE execucoes ADD COLUMN taxa_ocupacao_equipe REAL")

    cols_analista_habilidade = _column_names(conn, "analista_habilidade")
    if "nivel_proficiencia" not in cols_analista_habilidade and "nivel" in cols_analista_habilidade:
        conn.execute("ALTER TABLE analista_habilidade RENAME COLUMN nivel TO nivel_proficiencia")

    cols_projeto_habilidade = _column_names(conn, "projeto_habilidade_requerida")
    if "nivel_exigido" not in cols_projeto_habilidade and "nivel_minimo" in cols_projeto_habilidade:
        conn.execute("ALTER TABLE projeto_habilidade_requerida RENAME COLUMN nivel_minimo TO nivel_exigido")

    # Bancos que ja existiam antes da flag app_meta.seed_executado: se ja tem
    # analista cadastrado (seed anterior ou dado real do gestor), marca como
    # "ja executado" pra nao reseedar por engano na proxima vez que o gestor
    # esvaziar o cadastro. Se o banco ja estava vazio, deixa sem marcar - o
    # seed ainda roda normalmente na proxima inicializacao (primeira vez de
    # verdade).
    ja_marcado = conn.execute(
        "SELECT 1 FROM app_meta WHERE chave = 'seed_executado'"
    ).fetchone()
    if not ja_marcado:
        tem_analista = conn.execute("SELECT COUNT(*) AS n FROM analistas").fetchone()["n"] > 0
        if tem_analista:
            conn.execute(
                "INSERT INTO app_meta (chave, valor) VALUES ('seed_executado', '1')"
            )


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(_SCHEMA_PG if isinstance(conn, _PgConnection) else _SCHEMA)
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
        "SELECT id_habilidade FROM habilidades WHERE LOWER(nome) = LOWER(?)", (nome,)
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
        "SELECT id_habilidade FROM habilidades WHERE LOWER(nome) = LOWER(?) AND id_habilidade != ?",
        (novo_nome, id_habilidade),
    ).fetchone()
    if existente:
        raise ValueError(f"Ja existe uma habilidade chamada '{novo_nome}' no catalogo.")
    conn.execute("UPDATE habilidades SET nome = ? WHERE id_habilidade = ?", (novo_nome, id_habilidade))


def delete_habilidade(conn: sqlite3.Connection, id_habilidade: int) -> None:
    # Limpeza em cascata feita explicitamente aqui (nao delegada ao ON DELETE
    # CASCADE do schema) porque o backend libSQL/Turso opcional (ver
    # get_connection) nao demonstrou aplicar cascata de forma confiavel nos
    # testes locais - o app.py nao pode depender de um comportamento do
    # banco que nao da' pra' verificar contra o Turso real neste ambiente.
    # Idempotente com o ON DELETE CASCADE do SQLite local (que funciona e
    # continua declarado no schema): aqui ja' apaga tudo, entao a cascata,
    # quando existe, so' roda sobre um conjunto vazio.
    conn.execute("DELETE FROM analista_habilidade WHERE id_habilidade = ?", (id_habilidade,))
    conn.execute("DELETE FROM projeto_habilidade_requerida WHERE id_habilidade = ?", (id_habilidade,))
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
    # Cascata explicita - ver comentario em delete_habilidade().
    conn.execute("DELETE FROM analista_habilidade WHERE id_analista = ?", (id_analista,))
    conn.execute("UPDATE alocacoes SET id_analista = NULL WHERE id_analista = ?", (id_analista,))
    conn.execute("DELETE FROM analistas WHERE id_analista = ?", (id_analista,))


def get_niveis_analista(conn: sqlite3.Connection, id_analista: int) -> Dict[int, float]:
    rows = conn.execute(
        "SELECT id_habilidade, nivel_proficiencia FROM analista_habilidade WHERE id_analista = ?",
        (id_analista,),
    ).fetchall()
    return {r["id_habilidade"]: r["nivel_proficiencia"] for r in rows}


def set_nivel_analista(conn: sqlite3.Connection, id_analista: int, id_habilidade: int, nivel: float) -> None:
    conn.execute(
        """INSERT INTO analista_habilidade (id_analista, id_habilidade, nivel_proficiencia)
           VALUES (?, ?, ?)
           ON CONFLICT(id_analista, id_habilidade) DO UPDATE SET nivel_proficiencia = excluded.nivel_proficiencia""",
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
    # Cascata explicita - ver comentario em delete_habilidade().
    conn.execute("DELETE FROM projeto_habilidade_requerida WHERE id_projeto = ?", (id_projeto,))
    conn.execute("UPDATE alocacoes SET id_projeto = NULL WHERE id_projeto = ?", (id_projeto,))
    conn.execute("DELETE FROM projetos WHERE id_projeto = ?", (id_projeto,))


def get_requisitos_projeto(conn: sqlite3.Connection, id_projeto: int) -> Dict[int, float]:
    rows = conn.execute(
        "SELECT id_habilidade, nivel_exigido FROM projeto_habilidade_requerida WHERE id_projeto = ?",
        (id_projeto,),
    ).fetchall()
    return {r["id_habilidade"]: r["nivel_exigido"] for r in rows}


def set_requisito_projeto(conn: sqlite3.Connection, id_projeto: int, id_habilidade: int, nivel_minimo: float) -> None:
    conn.execute(
        """INSERT INTO projeto_habilidade_requerida (id_projeto, id_habilidade, nivel_exigido)
           VALUES (?, ?, ?)
           ON CONFLICT(id_projeto, id_habilidade) DO UPDATE SET nivel_exigido = excluded.nivel_exigido""",
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
            situacao, periodo_referencia, input_hash, tempo_processamento_s, taxa_ocupacao_equipe)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            resultado.tempo_processamento_s,
            resultado.taxa_ocupacao_equipe if resultado.viavel else None,
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
        # data_confirmacao e' o marco a partir do qual o prazo (prazo_semanas)
        # de cada projeto da execucao passa a contar (ver
        # _expiracao_sql()). So' e' gravado na transicao pra CONFIRMADA -
        # o botao que dispara essa transicao so aparece uma vez por
        # execucao, entao nunca e' sobrescrito.
        conn.execute(
            "UPDATE execucoes SET situacao = ?, data_confirmacao = ? WHERE id_execucao = ?",
            (situacao, datetime.utcnow().isoformat(timespec="seconds"), id_execucao),
        )
    else:
        conn.execute(
            "UPDATE execucoes SET situacao = ? WHERE id_execucao = ?", (situacao, id_execucao)
        )


# Expressao SQL reutilizada: 1 se a alocacao ainda conta como hora
# comprometida, 0 se ja' passou do prazo do projeto (prazo_semanas contado a
# partir de execucoes.data_confirmacao) ou se a execucao nao esta' confirmada.
# Prazo automatico por data (registrado em 06/09/2026): projetos tem fim, e
# uma vez o prazo estourado as horas do analista voltam a ficar livres sem
# precisar de acao manual do gestor. Compara em UTC (data_confirmacao e'
# gravada com datetime.utcnow()) pra' bater com "agora" do banco. Se o
# projeto foi excluido do cadastro (p.id_projeto IS NULL), mantem contando
# por seguranca (nao da pra saber o prazo original).
#
# datetime(x, '+N days')/datetime('now') e' sintaxe SQLite - Postgres nao
# tem essas funcoes, entao a expressao e' montada por dialeto (mesma logica,
# sintaxe diferente: cast pra timestamp + interval, comparado a NOW() AT
# TIME ZONE 'UTC').
_EXPIRACAO_SQL_SQLITE = """
    CASE
        WHEN e.situacao != 'confirmada' THEN 0
        WHEN e.data_confirmacao IS NULL THEN 1
        WHEN p.id_projeto IS NULL THEN 1
        WHEN datetime(e.data_confirmacao, '+' || (p.prazo_semanas * 7) || ' days') > datetime('now') THEN 1
        ELSE 0
    END
"""
_EXPIRACAO_SQL_PG = """
    CASE
        WHEN e.situacao != 'confirmada' THEN 0
        WHEN e.data_confirmacao IS NULL THEN 1
        WHEN p.id_projeto IS NULL THEN 1
        WHEN (CAST(e.data_confirmacao AS timestamp)
              + CAST((p.prazo_semanas * 7 || ' days') AS interval))
             > (NOW() AT TIME ZONE 'UTC') THEN 1
        ELSE 0
    END
"""


def _expiracao_sql(conn) -> str:
    return _EXPIRACAO_SQL_PG if isinstance(conn, _PgConnection) else _EXPIRACAO_SQL_SQLITE


def list_alocacoes_execucao(conn: sqlite3.Connection, id_execucao: int) -> List[sqlite3.Row]:
    return conn.execute(
        f"""SELECT al.*, ({_expiracao_sql(conn)}) AS ativa
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
            WHERE al.id_analista = ? AND ({_expiracao_sql(conn)}) = 1""",
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

def _get_or_create_habilidade(conn: sqlite3.Connection, nome: str) -> int:
    # add_habilidade() lanca ValueError se o nome ja existe (catalogo e' UNIQUE
    # COLLATE NOCASE) - usado aqui em vez dele porque o seed precisa ser
    # idempotente mesmo quando so' parte dos dados de exemplo foi removida
    # (ex.: gestor apaga todos os analistas mas mantem as habilidades).
    nome = normalizar_nome_habilidade(nome)
    existente = conn.execute(
        "SELECT id_habilidade FROM habilidades WHERE LOWER(nome) = LOWER(?)", (nome,)
    ).fetchone()
    if existente:
        return existente["id_habilidade"]
    return add_habilidade(conn, nome)


def seed_dados_exemplo(conn: sqlite3.Connection) -> None:
    # So' popula na PRIMEIRA vez que o banco e' inicializado de verdade - nunca
    # mais depois disso, controlado por app_meta.seed_executado (nao mais por
    # "analistas esta vazio"). Antes disso era baseado so' na contagem de
    # analistas, o que tinha um efeito colateral indesejado: se o gestor
    # apagava TODOS os analistas de proposito (pra comecar do zero), o
    # proximo rerun via essa tabela vazia como "primeira execucao" e
    # recolocava os dados de exemplo sozinho - o gestor nunca conseguia
    # manter o cadastro vazio. Reportado em 20/09/2026.
    ja_executou = conn.execute(
        "SELECT 1 FROM app_meta WHERE chave = 'seed_executado'"
    ).fetchone()
    if ja_executou:
        return
    conn.execute(
        "INSERT INTO app_meta (chave, valor) VALUES ('seed_executado', '1')"
    )

    habilidades_nomes = ["Tributario", "Auditoria", "SAP", "Power BI", "Compliance"]
    ids_habilidade = {nome: _get_or_create_habilidade(conn, nome) for nome in habilidades_nomes}

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
        # projetos.nome nao e' UNIQUE (duplicata nao lancaria erro), mas sem essa
        # checagem o mesmo cenario acima (analistas vazios, projetos ja existentes)
        # duplicaria "Consultoria Fiscal" etc a cada vez que o gestor esvaziasse
        # os analistas - a checagem e' so' pra' manter o seed idempotente.
        ja_existe = conn.execute(
            "SELECT 1 FROM projetos WHERE nome = ?", (p["nome"],)
        ).fetchone()
        if ja_existe:
            continue
        id_projeto = insert_projeto(conn, p)
        for nome_skill, nivel in reqs.items():
            set_requisito_projeto(conn, id_projeto, ids_habilidade[nome_skill], nivel)
