from datetime import timedelta

import pytest
from pydantic import ValidationError

from mostrador import sales_context as context


def test_complete_sources_include_ambiguity_and_never_count_receipts_as_sales():
    sources = context.load_sources()
    assert len(sources.operations.branches) == 3
    assert {m.kind for m in sources.operations.movements} == {"sale", "receipt", "adjustment"}
    assert any(c.branch_id is None for c in sources.conversations)
    assert len(sources.burst) == 6
    assert not sources.operations.signals
    assert any(d.valid_until < sources.operations.as_of for d in sources.documents)


def test_documents_are_filtered_by_branch_product_and_effective_time():
    sources = context.load_sources()
    selected = context.applicable_documents(sources, "SC-001", "gye-centro-demo")
    ids = {d.id for d in selected}
    assert "PROC-REPLENISH" in ids
    assert "DOC-CAMPAIGN-GYE" in ids
    assert "DOC-CAMPAIGN-UIO" not in ids
    assert "DOC-EXPIRED-SC001" not in ids


def test_source_revision_changes_when_a_document_changes():
    sources = context.load_sources()
    revision = sources.revision()
    changed = sources.model_copy(deep=True)
    changed.documents[0].body += " Nueva condición sintética."
    assert changed.revision() != revision


def test_conversation_future_unknown_branch_or_real_data_cannot_enter_sources():
    sources = context.load_sources()
    for change in ("future", "unknown_branch", "real", "duplicate"):
        data = sources.model_dump()
        if change == "future":
            data["conversations"][0]["occurred_at"] = sources.operations.as_of + timedelta(days=1)
        elif change == "unknown_branch":
            data["conversations"][0]["branch_id"] = "not-a-branch"
        elif change == "real":
            data["synthetic"] = False
        else:
            data["conversations"].append(data["conversations"][0])
        with pytest.raises(ValidationError):
            context.Sources.model_validate(data)
