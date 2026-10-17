import pytest

from app.persistence.phase2 import MARKER as V2_MARKER, active as v2_active
from app.persistence.phase3 import MARKER as V3_MARKER, authority_version, compact
from app.persistence.partitions import PartitionVersionError


def test_v3_compaction_keeps_core_domains_and_removes_narrow_authority():
    state = {
        "partition": V2_MARKER,
        "libraries": [{"id": "library"}],
        "sources": [{"id": "source", "title": "Title", "processing_status": "ready",
                     "stopped_reason": None, "generation": 4, "deleted": False,
                     "chunk_manifest": {"chunk_ids": ["chunk"]}}],
        "extraction_jobs": [{"id": "job"}],
        "knowledge_assets": [{"id": "asset"}],
        "outputs": [{"id": "output", "knowledge_snapshot": []}],
        "usage": {"calls": 7},
    }

    result = compact(state)

    assert result["partition"] == V3_MARKER
    assert result["libraries"] == state["libraries"]
    assert result["outputs"] == state["outputs"]
    assert result["usage"] == state["usage"]
    assert result["sources"] == [{"id": "source", "title": "Title",
                                  "chunk_manifest": {"chunk_ids": ["chunk"]}}]
    assert "extraction_jobs" not in result
    assert "knowledge_assets" not in result


def test_v2_readers_reject_v3_marker_and_marker_versions_are_exact():
    assert authority_version({"partition": V2_MARKER}) == 2
    assert authority_version({"partition": V3_MARKER}) == 3
    with pytest.raises(PartitionVersionError):
        v2_active({"partition": V3_MARKER})


def test_unknown_or_malformed_authority_marker_fails_closed():
    for marker in ({"version": 3, "state": "active", "domains": ["assets"]},
                   {"version": 4, "state": "active", "domains": []},
                   {"version": "3", "state": "active", "domains": []}):
        with pytest.raises(PartitionVersionError):
            authority_version({"partition": marker})
