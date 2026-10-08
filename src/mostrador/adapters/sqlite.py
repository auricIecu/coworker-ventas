import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from mostrador.domain import Actor, DomainError, Offer, Proposal, Quote, validate_quantity


def decode_proposal(raw: str) -> Proposal:
    data = json.loads(raw)
    quote = data.pop("quote")
    quote["offer"] = Offer(**quote["offer"])
    return Proposal(**data, quote=Quote(**quote))


class Database:
    def __init__(self, path: str):
        if path == ":memory:":
            raise ValueError("Use a file: each transaction opens its own connection")
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS offers (
                    sku TEXT, branch_id TEXT, title TEXT, sell_unit TEXT,
                    available INTEGER NOT NULL CHECK(available >= 0),
                    unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
                    version INTEGER NOT NULL, PRIMARY KEY(sku, branch_id)
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    operation_id TEXT PRIMARY KEY, payload TEXT NOT NULL, receipt TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, request_key TEXT NOT NULL,
                    payload TEXT NOT NULL, UNIQUE(actor_id, request_key)
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id TEXT NOT NULL, kind TEXT NOT NULL, actor_id TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                );
            """)
            # Wholly invented products and counts; never imports company files.
            db.executemany(
                "INSERT OR IGNORE INTO offers VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("DEMO-001", "centro", "Gasas demo 10 unidades", "paquete", 8, 350, 1),
                    ("DEMO-001", "norte", "Gasas demo 10 unidades", "paquete", 20, 350, 1),
                    ("DEMO-002", "centro", "Shampoo demo 250 ml", "frasco", 5, 625, 1),
                    ("DEMO-003", "norte", "Jabón demo 100 g", "unidad", 12, 180, 1),
                ],
            )

    @contextmanager
    def connect(self, write: bool = False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


class SQLiteCommerce:
    def __init__(self, database: Database):
        self.database = database

    def search(self, query: str) -> list[Offer]:
        with self.database.connect() as db:
            rows = db.execute("SELECT * FROM offers ORDER BY sku, branch_id").fetchall()
        return [
            Offer(**dict(row))
            for row in rows
            if query.casefold() in f"{row['sku']} {row['title']}".casefold()
        ][:50]

    def quote(self, sku: str, branch_id: str, quantity: int) -> Quote:
        validate_quantity(quantity)
        with self.database.connect() as db:
            row = db.execute(
                "SELECT * FROM offers WHERE sku = ? AND branch_id = ?", (sku, branch_id)
            ).fetchone()
        if row is None:
            raise DomainError("offer_not_found", 404)
        offer = Offer(**dict(row))
        if quantity > offer.available:
            raise DomainError("insufficient_stock")
        return Quote(offer, quantity, int(time.time()))

    def reserve(self, quote: Quote, operation_id: str) -> dict:
        validate_quantity(quote.quantity)
        payload = json.dumps(asdict(quote), sort_keys=True)
        with self.database.connect(write=True) as db:
            old = db.execute(
                "SELECT * FROM reservations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if old:
                if old["payload"] != payload:
                    raise DomainError("idempotency_conflict")
                return json.loads(old["receipt"])
            offer = quote.offer
            changed = db.execute(
                """
                UPDATE offers SET available = available - ?, version = version + 1
                WHERE sku = ? AND branch_id = ? AND version = ?
                    AND unit_price_cents = ? AND available >= ?
            """,
                (
                    quote.quantity,
                    offer.sku,
                    offer.branch_id,
                    offer.version,
                    offer.unit_price_cents,
                    quote.quantity,
                ),
            )
            if changed.rowcount != 1:
                raise DomainError("offer_changed")
            receipt = {
                "reservation_id": f"demo-{operation_id}",
                "source": "synthetic-demo",
                "sku": offer.sku,
                "branch_id": offer.branch_id,
                "quantity": quote.quantity,
                "total_cents": quote.total_cents,
                "currency": offer.currency,
            }
            db.execute(
                "INSERT INTO reservations VALUES (?, ?, ?)",
                (operation_id, payload, json.dumps(receipt)),
            )
            return receipt


class SQLiteWorkflowStore:
    def __init__(self, database: Database):
        self.database = database
        self.path = database.path

    @staticmethod
    def _get(db, proposal_id: str) -> Proposal:
        row = db.execute("SELECT payload FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise DomainError("proposal_not_found", 404)
        return decode_proposal(row["payload"])

    @staticmethod
    def _event(db, proposal_id: str, kind: str, actor_id: str, now: int):
        db.execute(
            "INSERT INTO events (proposal_id, kind, actor_id, timestamp) VALUES (?, ?, ?, ?)",
            (proposal_id, kind, actor_id, now),
        )

    @staticmethod
    def _save(db, proposal: Proposal):
        db.execute(
            "UPDATE proposals SET payload = ? WHERE id = ?",
            (json.dumps(asdict(proposal)), proposal.id),
        )

    def find(self, actor_id: str, key: str) -> Proposal | None:
        with self.database.connect() as db:
            row = db.execute(
                "SELECT payload FROM proposals WHERE actor_id = ? AND request_key = ?",
                (actor_id, key),
            ).fetchone()
        return decode_proposal(row["payload"]) if row else None

    def create(self, proposal: Proposal) -> Proposal:
        with self.database.connect(write=True) as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO proposals VALUES (?, ?, ?, ?)",
                (
                    proposal.id,
                    proposal.actor_id,
                    proposal.idempotency_key,
                    json.dumps(asdict(proposal)),
                ),
            )
            if inserted.rowcount:
                self._event(db, proposal.id, "proposed", proposal.actor_id, proposal.created_at)
            row = db.execute(
                "SELECT payload FROM proposals WHERE actor_id = ? AND request_key = ?",
                (proposal.actor_id, proposal.idempotency_key),
            ).fetchone()
            return decode_proposal(row["payload"])

    def get(self, proposal_id: str) -> Proposal:
        with self.database.connect() as db:
            return self._get(db, proposal_id)

    def claim(
        self, proposal_id: str, actor: Actor, decision: str, now: int
    ) -> tuple[Proposal, bool]:
        from dataclasses import replace

        with self.database.connect(write=True) as db:
            proposal = self._get(db, proposal_id)
            if proposal.status != "pending":
                if (decision == "approve" and proposal.status == "rejected") or (
                    decision == "reject" and proposal.status not in {"rejected", "expired"}
                ):
                    raise DomainError("decision_conflict")
                return proposal, False
            if now >= proposal.expires_at:
                status, kind = "expired", "expired"
            elif decision == "reject":
                status, kind = "rejected", "rejected"
            else:
                status, kind = "executing", "approved"
            proposal = replace(proposal, status=status)
            self._save(db, proposal)
            self._event(db, proposal.id, kind, actor.id, now)
            return proposal, status == "executing"

    def finish(
        self,
        proposal_id: str,
        actor: Actor,
        status: str,
        now: int,
        receipt: dict | None = None,
        error_code: str | None = None,
    ) -> Proposal:
        from dataclasses import replace

        with self.database.connect(write=True) as db:
            proposal = self._get(db, proposal_id)
            if proposal.status != "executing" or status not in {"executed", "failed", "uncertain"}:
                raise DomainError("invalid_transition")
            proposal = replace(proposal, status=status, receipt=receipt, error_code=error_code)
            self._save(db, proposal)
            self._event(db, proposal.id, status, actor.id, now)
            return proposal

    def events(self, proposal_id: str) -> list[dict]:
        with self.database.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT sequence, kind, actor_id, timestamp FROM events "
                    "WHERE proposal_id = ? ORDER BY sequence",
                    (proposal_id,),
                ).fetchall()
            ]
