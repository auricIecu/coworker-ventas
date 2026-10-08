"""Local review queue. Approval records intent; it never dispatches business actions."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from mostrador.backoffice import Reviewer, Snapshot, analyze
from mostrador.domain import DomainError


class RecommendationStore:
    def __init__(self, path: str, clock=time.time):
        self.path, self.clock = path, clock
        if path == ":memory:":
            raise ValueError("Use a file for durable review decisions")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS recommendations (
                    id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL,
                    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recommendation_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    recommendation_id TEXT NOT NULL, kind TEXT NOT NULL,
                    actor_id TEXT NOT NULL, timestamp INTEGER NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row):
        if row is None:
            raise DomainError("recommendation_not_found", 404)
        return {
            **json.loads(row["payload"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "execution_status": "not_configured",
        }

    @staticmethod
    def event(db, identifier, kind, actor, now):
        db.execute(
            "INSERT INTO recommendation_events "
            "(recommendation_id, kind, actor_id, timestamp) VALUES (?, ?, ?, ?)",
            (identifier, kind, actor, now),
        )

    def record(
        self, snapshot: Snapshot, *, proposals: list[dict] | None = None, renew_expired=False
    ) -> list[dict]:
        proposals, now = analyze(snapshot) if proposals is None else proposals, int(self.clock())
        fingerprint = snapshot.fingerprint()
        with self.connect() as db:
            outdated = db.execute(
                "SELECT id FROM recommendations WHERE status = 'pending' AND snapshot_id != ?",
                (fingerprint,),
            ).fetchall()
            for row in outdated:
                db.execute(
                    "UPDATE recommendations SET status = 'superseded' WHERE id = ?", (row["id"],)
                )
                self.event(db, row["id"], "superseded", "analyst-demo", now)
            for proposal in proposals:
                inserted = db.execute(
                    "INSERT OR IGNORE INTO recommendations VALUES (?, ?, ?, ?, ?, ?)",
                    (proposal["id"], fingerprint, json.dumps(proposal), "pending", now, now + 900),
                )
                if inserted.rowcount:
                    self.event(db, proposal["id"], "proposed", "analyst-demo", now)
                elif renew_expired:
                    renewed = db.execute(
                        "UPDATE recommendations SET expires_at = ?, payload = ? "
                        "WHERE id = ? AND status = 'pending' AND expires_at <= ?",
                        (now + 900, json.dumps(proposal), proposal["id"], now),
                    )
                    if renewed.rowcount:
                        self.event(db, proposal["id"], "revalidated", "analyst-demo", now)
            return [
                self.decode(
                    db.execute("SELECT * FROM recommendations WHERE id = ?", (p["id"],)).fetchone()
                )
                for p in proposals
            ]

    def list(self, actor: Reviewer) -> list[dict]:
        with self.connect() as db:
            rows = [
                self.decode(r)
                for r in db.execute("SELECT * FROM recommendations ORDER BY created_at DESC, id")
            ]
            return [r for r in rows if r["branch_id"] in actor.branches]

    def get(self, identifier: str, actor: Reviewer) -> dict:
        with self.connect() as db:
            result = self.decode(
                db.execute("SELECT * FROM recommendations WHERE id = ?", (identifier,)).fetchone()
            )
            self.authorize(result, actor)
            return result

    @staticmethod
    def authorize(recommendation: dict, actor: Reviewer):
        if recommendation["branch_id"] not in actor.branches:
            raise DomainError("recommendation_not_found", 404)

    def events(self, identifier: str, actor: Reviewer) -> list[dict]:
        self.get(identifier, actor)
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT sequence, kind, actor_id, timestamp FROM recommendation_events "
                    "WHERE recommendation_id = ? ORDER BY sequence",
                    (identifier,),
                )
            ]

    def decide(self, identifier: str, decision: str, actor: Reviewer, snapshot: Snapshot) -> dict:
        if actor.role != "operator":
            raise DomainError("permission_denied", 403)
        if decision not in {"approve", "reject"}:
            raise DomainError("invalid_decision", 422)
        status = "approved" if decision == "approve" else "rejected"
        now = int(self.clock())
        with self.connect() as db:
            current = self.decode(
                db.execute("SELECT * FROM recommendations WHERE id = ?", (identifier,)).fetchone()
            )
            self.authorize(current, actor)
            if current["status"] == status:
                return current
            if current["status"] != "pending":
                raise DomainError("decision_conflict")
            if decision == "approve":
                if current["snapshot_id"] != snapshot.fingerprint():
                    raise DomainError("evidence_changed")
                if now >= current["expires_at"]:
                    raise DomainError("recommendation_expired")
            db.execute("UPDATE recommendations SET status = ? WHERE id = ?", (status, identifier))
            self.event(db, identifier, status, actor.id, now)
            return {**current, "status": status}
