from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.researcher import assemble_quote_block_from_selected_segments
from models import VerbatimQuoteSelection
from store import CURRENT_SCHEMA_VERSION, init_db


def test_selection_contract_rejects_formatting_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        VerbatimQuoteSelection.model_validate(
            {
                "selected_segments": (" Exact source sentence.",),
            }
        )
    with pytest.raises(ValidationError):
        VerbatimQuoteSelection.model_validate(
            {
                "selected_segments": ("Exact source sentence.",),
                "extracted_quote_block": '[Invented.] "Exact source sentence." [Invented.]',
            }
        )


def test_application_assembles_context_and_multiple_segments_deterministically() -> None:
    text = (
        "Opening context. First exact evidence sentence. Intervening source sentence. "
        "Second exact evidence sentence. Closing context."
    )
    selection = VerbatimQuoteSelection(
        selected_segments=(
            "First exact evidence sentence.",
            "Second exact evidence sentence.",
        )
    )

    quote = assemble_quote_block_from_selected_segments(
        text,
        selection,
        truncated=False,
    )

    assert quote == (
        '[Opening context.] "First exact evidence sentence. ... '
        'Second exact evidence sentence." [Closing context.]'
    )


def test_application_assembles_exact_text_from_source_sentence_ranges() -> None:
    text = (
        "Opening context. First exact evidence sentence. Intervening source sentence. "
        "Second exact evidence sentence. Closing context."
    )
    selection = VerbatimQuoteSelection.model_validate(
        {
            "selected_sentence_ranges": (
                {"start_sentence": 2, "end_sentence": 2},
                {"start_sentence": 4, "end_sentence": 4},
            )
        }
    )

    quote = assemble_quote_block_from_selected_segments(text, selection, truncated=False)

    assert quote == (
        '[Opening context.] "First exact evidence sentence. ... '
        'Second exact evidence sentence." [Closing context.]'
    )


def test_source_sentence_ranges_reject_overlap_and_out_of_bounds() -> None:
    with pytest.raises(ValidationError, match="ordered and non-overlapping"):
        VerbatimQuoteSelection.model_validate(
            {
                "selected_sentence_ranges": (
                    {"start_sentence": 2, "end_sentence": 3},
                    {"start_sentence": 3, "end_sentence": 4},
                )
            }
        )
    with pytest.raises(ValueError, match="exceeds the snapshot"):
        assemble_quote_block_from_selected_segments(
            "One. Two.",
            VerbatimQuoteSelection.model_validate(
                {"selected_sentence_ranges": ({"start_sentence": 3, "end_sentence": 3},)}
            ),
            truncated=False,
        )


@pytest.mark.parametrize(
    ("text", "selection", "truncated", "expected"),
    (
        (
            "Exact opening evidence. Following context.",
            VerbatimQuoteSelection(selected_segments=("Exact opening evidence.",)),
            False,
            '[Start of Text] "Exact opening evidence." [Following context.]',
        ),
        (
            "Preceding context. Exact ending evidence.",
            VerbatimQuoteSelection(selected_segments=("Exact ending evidence.",)),
            False,
            '[Preceding context.] "Exact ending evidence." [End of Text]',
        ),
        (
            "Preceding context. Exact truncated evidence.",
            VerbatimQuoteSelection(selected_segments=("Exact truncated evidence.",)),
            True,
            '[Preceding context.] "Exact truncated evidence." [Truncated End of Snapshot]',
        ),
    ),
)
def test_application_owns_boundary_markers(
    text: str,
    selection: VerbatimQuoteSelection,
    truncated: bool,
    expected: str,
) -> None:
    assert (
        assemble_quote_block_from_selected_segments(
            text,
            selection,
            truncated=truncated,
        )
        == expected
    )


def test_nonexistent_or_out_of_order_selection_fails_closed() -> None:
    text = "Opening. First evidence. Second evidence. Closing."

    with pytest.raises(ValueError, match="does not appear"):
        assemble_quote_block_from_selected_segments(
            text,
            VerbatimQuoteSelection(selected_segments=("Invented evidence.",)),
            truncated=False,
        )
    with pytest.raises(ValueError, match="does not appear"):
        assemble_quote_block_from_selected_segments(
            text,
            VerbatimQuoteSelection(selected_segments=("Second evidence.", "First evidence.")),
            truncated=False,
        )


def test_mvp9_quote_storage_remains_compatible_with_mvp10_additive_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mvp9.sqlite3"

    init_db(str(db_path))

    with sqlite3.connect(db_path) as connection:
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        provisional_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(provisional_extractions)")
        }
    assert CURRENT_SCHEMA_VERSION == 12
    assert versions == [
        (1,),
        (2,),
        (3,),
        (4,),
        (5,),
        (6,),
        (7,),
        (8,),
        (9,),
        (10,),
        (11,),
        (12,),
    ]
    assert "extracted_quote_block" in provisional_columns
    assert "selected_segments" not in provisional_columns
