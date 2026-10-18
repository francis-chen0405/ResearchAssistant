"""Atomic portfolio/trail/source-family aggregate persistence and replay."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from uuid import UUID

from researchassistant.contracts.models import (
    EvidenceTrailEntry,
    PortfolioCoverageAssessment,
    PortfolioItem,
)
from researchassistant.storage.store_types import (
    DatabaseReader as DatabaseReader,
)
from researchassistant.storage.store_types import ReadConnectionFactory, WriteConnectionFactory
from researchassistant.storage.store_types import (
    _dt_to_iso as _dt_to_iso,
)
from researchassistant.storage.store_types import (
    _read_execute as _read_execute,
)


def insert_source_family_member(
    db_path: str, entry: EvidenceTrailEntry, *, _connect: WriteConnectionFactory
) -> None:
    """Persist one immutable family assignment when a source has an identified family."""
    if entry.source_family is None:
        return
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO source_family_members
               (run_id, retrieval_attempt_id, source_family_id, family_key,
                identification_basis, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(entry.run_id),
                str(entry.retrieval_attempt_id),
                str(entry.source_family.source_family_id),
                entry.source_family.family_key,
                entry.source_family.identification_basis,
                _dt_to_iso(entry.created_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_evidence_trail_entry(
    db_path: str, entry: EvidenceTrailEntry, *, _connect: WriteConnectionFactory
) -> None:
    """Persist one complete source outcome without rewriting source history."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO evidence_trail_entries
               (trail_entry_id, run_id, retrieval_attempt_id, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                str(entry.trail_entry_id),
                str(entry.run_id),
                str(entry.retrieval_attempt_id),
                entry.model_dump_json(),
                _dt_to_iso(entry.created_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_evidence_trail_entries(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> tuple[EvidenceTrailEntry, ...]:
    """Read appended source outcomes; a pre-MVP-10 database has no such rows."""
    with _read_connection(db_path) as conn:
        try:
            rows = _read_execute(
                conn,
                "SELECT payload_json FROM evidence_trail_entries WHERE run_id = ? "
                "ORDER BY created_at, trail_entry_id",
                (str(run_id),),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return ()
            raise
    return tuple(EvidenceTrailEntry.model_validate_json(row["payload_json"]) for row in rows)


def insert_portfolio_item(
    db_path: str, item: PortfolioItem, *, _connect: WriteConnectionFactory
) -> None:
    """Append one approved Ledger statement to the portfolio."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO portfolio_items (run_id, ledger_claim_id, source_family_id, payload_json)
               VALUES (?, ?, ?, ?)""",
            (
                str(item.run_id),
                str(item.ledger_claim_id),
                str(item.source_family_id),
                item.model_dump_json(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_portfolio_items(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> tuple[PortfolioItem, ...]:
    """Read the immutable portfolio, or an empty portfolio for historical runs."""
    with _read_connection(db_path) as conn:
        try:
            rows = _read_execute(
                conn,
                "SELECT payload_json FROM portfolio_items WHERE run_id = ? "
                "ORDER BY ledger_claim_id",
                (str(run_id),),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return ()
            raise
    return tuple(PortfolioItem.model_validate_json(row["payload_json"]) for row in rows)


def insert_mvp10_portfolio_batch(
    db_path: str,
    entries: Sequence[EvidenceTrailEntry],
    items: Sequence[PortfolioItem],
    *,
    _connect: WriteConnectionFactory,
) -> None:
    """Append one portfolio phase atomically, accepting exact historical replay."""
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for entry in entries:
            stored_entry = conn.execute(
                """SELECT payload_json FROM evidence_trail_entries
                   WHERE run_id = ? AND retrieval_attempt_id = ?""",
                (str(entry.run_id), str(entry.retrieval_attempt_id)),
            ).fetchone()
            prior_entry = (
                EvidenceTrailEntry.model_validate_json(stored_entry["payload_json"])
                if stored_entry is not None
                else None
            )
            legacy_missing_provenance = (
                prior_entry is not None and _legacy_missing_snapshot_projection(prior_entry, entry)
            )
            stored_family = conn.execute(
                """SELECT source_family_id, family_key, identification_basis
                   FROM source_family_members WHERE run_id = ? AND retrieval_attempt_id = ?""",
                (str(entry.run_id), str(entry.retrieval_attempt_id)),
            ).fetchone()
            if legacy_missing_provenance:
                if stored_family is not None:
                    raise sqlite3.IntegrityError(
                        "legacy evidence trail has conflicting source family membership"
                    )
            elif entry.source_family is not None:
                family = entry.source_family
                family_values = (
                    str(family.source_family_id),
                    family.family_key,
                    family.identification_basis,
                )
                if stored_family is None:
                    conn.execute(
                        """INSERT INTO source_family_members
                           (run_id, retrieval_attempt_id, source_family_id, family_key,
                            identification_basis, created_at) VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            str(entry.run_id),
                            str(entry.retrieval_attempt_id),
                            *family_values,
                            _dt_to_iso(entry.created_at),
                        ),
                    )
                elif tuple(stored_family) != family_values:
                    raise sqlite3.IntegrityError(
                        "source family replay conflicts with immutable data"
                    )
            elif stored_family is not None:
                raise sqlite3.IntegrityError("source family replay conflicts with immutable data")
            if stored_entry is None:
                conn.execute(
                    """INSERT INTO evidence_trail_entries
                       (trail_entry_id, run_id, retrieval_attempt_id, payload_json, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        str(entry.trail_entry_id),
                        str(entry.run_id),
                        str(entry.retrieval_attempt_id),
                        entry.model_dump_json(),
                        _dt_to_iso(entry.created_at),
                    ),
                )
            else:
                assert prior_entry is not None
                if not legacy_missing_provenance and prior_entry != entry.model_copy(
                    update={"created_at": prior_entry.created_at}
                ):
                    raise sqlite3.IntegrityError(
                        "evidence trail replay conflicts with immutable data"
                    )
        for item in items:
            stored_item = conn.execute(
                "SELECT payload_json FROM portfolio_items WHERE run_id = ? AND ledger_claim_id = ?",
                (str(item.run_id), str(item.ledger_claim_id)),
            ).fetchone()
            if stored_item is None:
                conn.execute(
                    """INSERT INTO portfolio_items
                       (run_id, ledger_claim_id, source_family_id, payload_json)
                       VALUES (?, ?, ?, ?)""",
                    (
                        str(item.run_id),
                        str(item.ledger_claim_id),
                        str(item.source_family_id),
                        item.model_dump_json(),
                    ),
                )
            else:
                prior_item = PortfolioItem.model_validate_json(stored_item["payload_json"])
                if prior_item != item.model_copy(update={"added_at": prior_item.added_at}):
                    raise sqlite3.IntegrityError("portfolio replay conflicts with immutable data")
        conn.commit()
    finally:
        conn.close()


def _legacy_missing_snapshot_projection(
    prior: EvidenceTrailEntry,
    current: EvidenceTrailEntry,
) -> bool:
    """Recognize only the earlier snapshot-ID lookup bug's stored projection."""
    if (
        current.source_family is None
        or current.snapshot_status != "snapshotted"
        or current.snapshot_sha256 is None
        or prior.source_family is not None
        or prior.snapshot_status != "not snapshotted"
        or prior.snapshot_sha256 is not None
        or prior.model_attempt_ids
        or prior.accepted_statement is not None
        or prior.accepted_quote is not None
        or prior.cost_incurred
    ):
        return False
    projected = current.model_copy(
        update={
            "source_family": None,
            "snapshot_status": "not snapshotted",
            "snapshot_sha256": None,
            "model_attempt_ids": (),
            "accepted_statement": None,
            "accepted_quote": None,
            "cost_incurred": False,
            "created_at": prior.created_at,
        }
    )
    return prior == projected


def insert_portfolio_coverage_assessment(
    db_path: str, assessment: PortfolioCoverageAssessment, *, _connect: WriteConnectionFactory
) -> None:
    """Persist the single terminal deterministic coverage assessment."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO portfolio_coverage_assessments (run_id, payload_json, assessed_at)
               VALUES (?, ?, ?)""",
            (
                str(assessment.run_id),
                assessment.model_dump_json(),
                _dt_to_iso(assessment.assessed_at),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_portfolio_coverage_assessment(
    db_path: DatabaseReader, run_id: UUID, *, _read_connection: ReadConnectionFactory
) -> PortfolioCoverageAssessment | None:
    """Read terminal coverage when present, without fabricating it for history."""
    with _read_connection(db_path) as conn:
        try:
            row = _read_execute(
                conn,
                "SELECT payload_json FROM portfolio_coverage_assessments WHERE run_id = ?",
                (str(run_id),),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
    return PortfolioCoverageAssessment.model_validate_json(row["payload_json"]) if row else None
