import duckdb

from app.core.config import settings

_connection: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    global _connection
    if _connection is None:
        _connection = duckdb.connect(settings.database_path)
        _init_tables(_connection)
    return _connection


def close_connection() -> None:
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


def _init_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS browse_results_id_seq START 1
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS browse_results (
            id INTEGER PRIMARY KEY DEFAULT nextval('browse_results_id_seq'),
            url VARCHAR NOT NULL,
            task VARCHAR NOT NULL,
            found BOOLEAN NOT NULL,
            confidence DOUBLE NOT NULL,
            answer VARCHAR,
            error VARCHAR,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)


def save_result(
    url: str, task: str, found: bool, confidence: float,
    answer: str | None, error: str | None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO browse_results (url, task, found, confidence, answer, error)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [url, task, found, confidence, answer, error],
    )


def get_results(url: str | None = None, limit: int = 50) -> list[dict]:
    conn = get_connection()
    if url:
        result = conn.execute(
            "SELECT * FROM browse_results WHERE url = ? ORDER BY created_at DESC LIMIT ?",
            [url, limit],
        )
    else:
        result = conn.execute(
            "SELECT * FROM browse_results ORDER BY created_at DESC LIMIT ?",
            [limit],
        )
    columns = [desc[0] for desc in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]
