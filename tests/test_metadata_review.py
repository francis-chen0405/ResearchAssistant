"""Review regressions for fresh bounded Scout input and historical compatibility."""

from test_metadata_ranking import _item

from agents.v2_discovery import _scout_candidate


def test_legacy_scout_preserves_all_author_metadata() -> None:
    authors = tuple(f"Researcher {index} " + "x" * 250 for index in range(15))
    item = _item(1).model_copy(update={"authors": authors})

    assert _scout_candidate(item).authors == authors
    bounded = _scout_candidate(item, bounded=True)
    assert bounded.authors == tuple(author[:240] for author in authors[:12])
