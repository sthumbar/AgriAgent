"""SQLite-backed agronomist review queue.

Shared by the MCP server and the orchestrator so both paths write to the same DB.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DB_PATH = Path(os.getenv("REVIEW_DB_PATH", "rag/review_queue.db"))
LOW_CONFIDENCE_THRESHOLD = int(os.getenv("LOW_CONFIDENCE_THRESHOLD", "60"))


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id            TEXT PRIMARY KEY,
            submitted_at  TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'pending',
            image_path    TEXT,
            crop          TEXT,
            disease       TEXT,
            confidence    INTEGER,
            severity      TEXT,
            analysis_json TEXT NOT NULL,
            expert_note   TEXT,
            reviewed_at   TEXT,
            reviewed_by   TEXT
        )
    """)
    con.commit()
    return con


# ── Write operations ─────────────────────────────────────────────────────────

def submit_for_review(image_path: str, analysis: Dict[str, Any]) -> str:
    """Queue a low-confidence analysis for expert review. Returns the review_id."""
    review_id = str(uuid.uuid4())[:8].upper()
    vision = analysis.get("vision_result", {})
    with _conn() as con:
        con.execute(
            """INSERT INTO reviews
               (id, submitted_at, status, image_path, crop, disease,
                confidence, severity, analysis_json)
               VALUES (?,?,  'pending', ?,?,?,?,?,?)""",
            (
                review_id,
                datetime.now().isoformat(timespec="seconds"),
                image_path,
                vision.get("crop", "Unknown"),
                vision.get("disease", "Unknown"),
                int(vision.get("confidence", 0)),
                vision.get("severity", "Unknown"),
                json.dumps(analysis),
            ),
        )
    return review_id


def add_expert_note(
    review_id: str,
    note: str,
    action: str = "approved",
    reviewer: str = "agronomist",
    corrected_crop: str = "",
    corrected_disease: str = "",
) -> Dict[str, Any]:
    """Set expert note + decision on a review. Returns the updated row."""
    with _conn() as con:
        con.execute(
            """UPDATE reviews
               SET expert_note=?, status=?, reviewed_at=?, reviewed_by=?
               WHERE id=?""",
            (note, action, datetime.now().isoformat(timespec="seconds"), reviewer, review_id),
        )
        row = con.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()

    result = dict(row) if row else {"error": "Review not found"}

    # Patch corrected names into the stored analysis so callers can resume the pipeline
    if row and (corrected_crop or corrected_disease):
        analysis = json.loads(row["analysis_json"])
        if corrected_crop:
            analysis["vision_result"]["crop"] = corrected_crop
            analysis["vision_result"]["human_corrected"] = True
        if corrected_disease:
            analysis["vision_result"]["disease"] = corrected_disease
            analysis["vision_result"]["human_corrected"] = True
        with _conn() as con:
            con.execute(
                "UPDATE reviews SET analysis_json=? WHERE id=?",
                (json.dumps(analysis), review_id),
            )
        result["analysis_json"] = json.dumps(analysis)

    return result


# ── Read operations ──────────────────────────────────────────────────────────

def get_review_status(review_id: str) -> Dict[str, Any]:
    with _conn() as con:
        row = con.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    return dict(row) if row else {"error": f"Review {review_id!r} not found"}


def get_full_analysis(review_id: str) -> Dict[str, Any]:
    """Return the stored analysis dict for a review (used to resume the pipeline)."""
    row = get_review_status(review_id)
    if "error" in row:
        return row
    return json.loads(row["analysis_json"])


def list_pending_reviews() -> List[Dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM reviews WHERE status='pending' ORDER BY submitted_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_all_reviews(limit: int = 50) -> List[Dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM reviews ORDER BY submitted_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Helper ───────────────────────────────────────────────────────────────────

def is_low_confidence(confidence: int) -> bool:
    return confidence < LOW_CONFIDENCE_THRESHOLD
