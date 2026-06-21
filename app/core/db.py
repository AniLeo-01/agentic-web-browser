import json
from datetime import datetime

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
    conn.execute("CREATE SEQUENCE IF NOT EXISTS browse_results_id_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS browse_results (
            id INTEGER PRIMARY KEY DEFAULT nextval('browse_results_id_seq'),
            url VARCHAR NOT NULL,
            task VARCHAR NOT NULL,
            found BOOLEAN NOT NULL,
            confidence DOUBLE NOT NULL,
            answer VARCHAR,
            error VARCHAR,
            steps_taken INTEGER NOT NULL DEFAULT 0,
            duration_seconds DOUBLE NOT NULL DEFAULT 0.0,
            errors_encountered INTEGER NOT NULL DEFAULT 0,
            score_completeness DOUBLE NOT NULL DEFAULT 0.0,
            score_confidence DOUBLE NOT NULL DEFAULT 0.0,
            score_efficiency DOUBLE NOT NULL DEFAULT 0.0,
            score_speed DOUBLE NOT NULL DEFAULT 0.0,
            score_reliability DOUBLE NOT NULL DEFAULT 0.0,
            score_overall DOUBLE NOT NULL DEFAULT 0.0,
            step_details VARCHAR DEFAULT '[]',
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)


def save_result(
    url: str,
    task: str,
    found: bool,
    confidence: float,
    answer: str | None,
    error: str | None,
    steps_taken: int,
    duration_seconds: float,
    errors_encountered: int,
    scores: dict,
    step_details: list[dict] | None = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO browse_results (
            url, task, found, confidence, answer, error,
            steps_taken, duration_seconds, errors_encountered,
            score_completeness, score_confidence, score_efficiency,
            score_speed, score_reliability, score_overall, step_details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            url, task, found, confidence, answer, error,
            steps_taken, duration_seconds, errors_encountered,
            scores["completeness"], scores["confidence"], scores["efficiency"],
            scores["speed"], scores["reliability"], scores["overall"],
            json.dumps(step_details or []),
        ],
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
    rows = []
    for row in result.fetchall():
        d = dict(zip(columns, row))
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        if isinstance(d.get("step_details"), str):
            d["step_details"] = json.loads(d["step_details"])
        rows.append(d)
    return rows


def get_dashboard_stats() -> dict:
    """Aggregate stats for the dashboard."""
    conn = get_connection()
    summary = conn.execute("""
        SELECT
            COUNT(*) as total_runs,
            SUM(CASE WHEN found THEN 1 ELSE 0 END) as successful_runs,
            AVG(score_overall) as avg_overall_score,
            AVG(score_completeness) as avg_completeness,
            AVG(score_confidence) as avg_confidence,
            AVG(score_efficiency) as avg_efficiency,
            AVG(score_speed) as avg_speed,
            AVG(score_reliability) as avg_reliability,
            AVG(duration_seconds) as avg_duration,
            AVG(steps_taken) as avg_steps
        FROM browse_results
    """).fetchone()

    by_url = conn.execute("""
        SELECT
            url,
            COUNT(*) as runs,
            AVG(score_overall) as avg_score,
            SUM(CASE WHEN found THEN 1 ELSE 0 END) as successes
        FROM browse_results
        GROUP BY url
        ORDER BY runs DESC
        LIMIT 20
    """)
    url_columns = [desc[0] for desc in by_url.description]
    url_stats = [dict(zip(url_columns, row)) for row in by_url.fetchall()]

    return {
        "total_runs": summary[0],
        "successful_runs": summary[1],
        "avg_scores": {
            "overall": round(summary[2] or 0, 3),
            "completeness": round(summary[3] or 0, 3),
            "confidence": round(summary[4] or 0, 3),
            "efficiency": round(summary[5] or 0, 3),
            "speed": round(summary[6] or 0, 3),
            "reliability": round(summary[7] or 0, 3),
        },
        "avg_duration": round(summary[8] or 0, 2),
        "avg_steps": round(summary[9] or 0, 1),
        "by_url": url_stats,
    }


def get_url_performance(url: str) -> dict:
    """Detailed performance breakdown for a single URL."""
    conn = get_connection()
    summary = conn.execute("""
        SELECT
            COUNT(*) as total_runs,
            SUM(CASE WHEN found THEN 1 ELSE 0 END) as successful_runs,
            AVG(score_overall) as avg_overall,
            AVG(score_completeness) as avg_completeness,
            AVG(score_confidence) as avg_confidence,
            AVG(score_efficiency) as avg_efficiency,
            AVG(score_speed) as avg_speed,
            AVG(score_reliability) as avg_reliability,
            AVG(duration_seconds) as avg_duration,
            AVG(steps_taken) as avg_steps
        FROM browse_results
        WHERE url = ?
    """, [url]).fetchone()

    if not summary or summary[0] == 0:
        return {"url": url, "total_runs": 0, "runs": []}

    runs = conn.execute("""
        SELECT task, found, score_overall, score_completeness, score_confidence,
               score_efficiency, score_speed, score_reliability,
               steps_taken, duration_seconds, errors_encountered, step_details, created_at
        FROM browse_results
        WHERE url = ?
        ORDER BY created_at DESC
        LIMIT 50
    """, [url])
    run_cols = [desc[0] for desc in runs.description]
    run_rows = []
    for row in runs.fetchall():
        d = dict(zip(run_cols, row))
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        if isinstance(d.get("step_details"), str):
            d["step_details"] = json.loads(d["step_details"])
        run_rows.append(d)

    return {
        "url": url,
        "total_runs": summary[0],
        "successful_runs": summary[1],
        "avg_scores": {
            "overall": round(summary[2] or 0, 3),
            "completeness": round(summary[3] or 0, 3),
            "confidence": round(summary[4] or 0, 3),
            "efficiency": round(summary[5] or 0, 3),
            "speed": round(summary[6] or 0, 3),
            "reliability": round(summary[7] or 0, 3),
        },
        "avg_duration": round(summary[8] or 0, 2),
        "avg_steps": round(summary[9] or 0, 1),
        "runs": run_rows,
    }


def get_all_urls() -> list[str]:
    """Return all distinct URLs that have been browsed."""
    conn = get_connection()
    result = conn.execute(
        "SELECT DISTINCT url FROM browse_results ORDER BY url"
    )
    return [row[0] for row in result.fetchall()]
