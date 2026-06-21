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

    # Identify top issues from failed runs and low-scoring dimensions
    issues = _identify_issues(conn, summary)
    recommendations = _generate_recommendations(summary, issues)

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
        "top_issues": issues,
        "recommendations": recommendations,
    }


def _identify_issues(conn: duckdb.DuckDBPyConnection, summary: tuple) -> list[dict]:
    """Analyze runs to identify top friction points."""
    issues = []
    total = summary[0] or 0
    if total == 0:
        return issues

    success_rate = (summary[1] or 0) / total
    avg_completeness = summary[3] or 0
    avg_confidence = summary[4] or 0
    avg_efficiency = summary[5] or 0
    avg_speed = summary[6] or 0
    avg_reliability = summary[7] or 0

    # High failure rate
    if success_rate < 0.7:
        issues.append({
            "severity": "high",
            "category": "Completeness",
            "title": "High failure rate",
            "detail": f"{(1 - success_rate) * 100:.0f}% of runs failed to find the requested information",
        })

    # Low confidence
    if avg_confidence < 0.6:
        issues.append({
            "severity": "high",
            "category": "Confidence",
            "title": "Low agent confidence",
            "detail": f"Average confidence is {avg_confidence:.0%} — the agent is uncertain about its answers",
        })

    # Poor efficiency (too many steps)
    if avg_efficiency < 0.5:
        issues.append({
            "severity": "medium",
            "category": "Efficiency",
            "title": "Excessive navigation steps",
            "detail": f"Efficiency score is {avg_efficiency:.0%} — the agent takes too many steps to find information",
        })

    # Slow runs
    if avg_speed < 0.5:
        issues.append({
            "severity": "medium",
            "category": "Speed",
            "title": "Slow task completion",
            "detail": f"Speed score is {avg_speed:.0%} — runs are taking longer than the 60s baseline",
        })

    # Reliability problems (code errors)
    if avg_reliability < 0.7:
        issues.append({
            "severity": "high",
            "category": "Reliability",
            "title": "Frequent code execution errors",
            "detail": f"Reliability score is {avg_reliability:.0%} — the agent encounters errors during browsing",
        })

    # Find URLs with worst performance
    worst = conn.execute("""
        SELECT url, AVG(score_overall) as avg_score,
               SUM(CASE WHEN NOT found THEN 1 ELSE 0 END) as failures,
               COUNT(*) as runs
        FROM browse_results
        GROUP BY url
        HAVING COUNT(*) >= 1 AND AVG(score_overall) < 0.5
        ORDER BY avg_score ASC
        LIMIT 3
    """).fetchall()
    for row in worst:
        issues.append({
            "severity": "medium",
            "category": "URL-specific",
            "title": f"Poor performance on {row[0][:50]}",
            "detail": f"Average score {row[1]:.0%} across {row[3]} run(s), {row[2]} failure(s)",
        })

    # Sort by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: severity_order.get(x["severity"], 99))

    return issues[:5]


def _generate_recommendations(summary: tuple, issues: list[dict]) -> list[str]:
    """Generate actionable recommendations based on identified issues."""
    recs = []
    if not summary or (summary[0] or 0) == 0:
        return ["Run some agent tasks to start collecting performance data"]

    categories = {i["category"] for i in issues}

    if "Completeness" in categories:
        recs.append(
            "Improve task prompts with more specific instructions — "
            "vague tasks like 'find info' lead to higher failure rates"
        )

    if "Confidence" in categories:
        recs.append(
            "Websites with heavy JavaScript rendering or dynamic content may "
            "reduce agent confidence — consider testing on pages with static content first"
        )

    if "Efficiency" in categories:
        recs.append(
            "The agent is taking many steps to navigate — sites with clear navigation "
            "structure and descriptive link text improve efficiency"
        )

    if "Speed" in categories:
        recs.append(
            "Long run times may indicate complex page structures or slow model responses — "
            "consider reducing max_steps or using a faster model endpoint"
        )

    if "Reliability" in categories:
        recs.append(
            "Code execution errors often stem from pop-ups, cookie banners, or "
            "dynamic elements — sites should have dismissible overlays and standard HTML structure"
        )

    if "URL-specific" in categories:
        recs.append(
            "Some URLs consistently score low — review their page structure for "
            "agent-unfriendly patterns like login walls, CAPTCHAs, or infinite scroll"
        )

    if not recs:
        recs.append("Overall performance looks good — keep testing across diverse URLs to build a comprehensive profile")

    return recs


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
