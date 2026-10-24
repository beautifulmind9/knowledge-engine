"""Synthetic local explanations retain scoring/provenance, never excerpts."""
import json

from app.services.retrieval_diagnostics import RetrievalDiagnostics


def _asset(asset_id, source_id="source_a"):
    return {"id": asset_id, "source_id": source_id, "chunk_id": "chunk_" + asset_id,
            "title": "Private synthetic title", "evidence": "Private synthetic excerpt"}


def _group(*assets):
    return {"canonical_asset": assets[0], "asset_ids": [asset["id"] for asset in assets],
            "source_ids": [asset["source_id"] for asset in assets],
            "evidence_trail": [{"asset_id": asset["id"], **asset} for asset in assets]}


def test_default_capture_excludes_request_excerpts_and_unapproved_fields():
    trace = RetrievalDiagnostics()
    trace.request("find", "Private synthetic question", terms=["question"],
                  scope={"library_id": "library_a", "source_ids": ["source_b", "source_a"],
                         "title": "Private scope title"}, limit=2)
    asset = _asset("asset_a")
    trace.candidate(asset, 5, ["question"], [{"term": "question", "field": "title", "points": 5,
                                          "evidence": asset["evidence"], "private": ["text"]}])
    trace.groups([_group(asset)])
    trace.preparation("source_a", readiness="partly_ready", completed_parts=1, total_parts=3,
                      attention_message="Private preparation text", has_usable_knowledge=True)
    capture = trace.as_dict()
    encoded = json.dumps(capture, allow_nan=False)
    assert "Private" not in encoded
    assert capture["requests"][0]["query_character_count"] == len("Private synthetic question")
    assert len(capture["requests"][0]["query_sha256"]) == 64
    assert capture["candidates"][0]["contributions"] == [{"term": "question", "field": "title", "points": 5}]
    assert capture["groups"][0]["provenance"] == [{"asset_id": "asset_a", "source_id": "source_a", "chunk_id": "chunk_asset_a"}]
    assert capture["preparation"] == [{"source_id": "source_a", "readiness": "partly_ready",
                                      "completed_parts": 1, "total_parts": 3, "has_usable_knowledge": True}]


def test_consolidation_and_pool_limits_keep_distinct_positions_and_exclusion_reasons():
    trace = RetrievalDiagnostics()
    duplicate, independent, other, cut, irrelevant = (
        _asset("a"), _asset("b", "source_b"), _asset("c"), _asset("d"), _asset("e"))
    for item in (duplicate, independent, other, cut):
        trace.candidate(item, 5, ["term"])
    trace.candidate(irrelevant, reason="no_lexical_overlap")
    trace.ranked([duplicate, independent, other, cut], retained=[duplicate, independent, other])
    groups = [_group(duplicate, independent), _group(other)]
    trace.groups(groups, selected_groups=groups[:1])
    capture = trace.as_dict()
    candidates = {item["id"]: item for item in capture["candidates"]}
    assert candidates["b"]["position_before_consolidation"] == 2
    assert candidates["b"]["position_after_consolidation"] == 1
    assert candidates["b"]["position_in_results"] == 1
    assert candidates["a"]["retained_within_limit"] is True
    assert candidates["c"]["exclusion_reason"] == "result_limit"
    assert candidates["d"]["exclusion_reason"] == "candidate_limit"
    assert candidates["e"]["exclusion_reason"] == "no_lexical_overlap"
    assert capture["groups"][0]["source_ids"] == ["source_a", "source_b"]
    assert capture["final_selection"] == [{
        "position": 1, "canonical_asset_id": "a", "asset_ids": ["a", "b"],
        "source_ids": ["source_a", "source_b"],
    }]


def test_empty_selection_is_distinct_from_omitting_selection_and_results_are_isolated():
    trace = RetrievalDiagnostics()
    groups = [_group(_asset("a"))]
    trace.groups(groups, selected_groups=[])
    assert trace.as_dict()["groups"][0]["retained_within_limit"] is False
    trace.groups(groups, limit=1)
    first = trace.as_dict()
    assert first["result_limit"] == 1
    first["groups"][0]["asset_ids"].append("mutated")
    first["candidates"][0]["id"] = "mutated"
    assert trace.as_dict()["groups"][0]["asset_ids"] == ["a"]
    assert trace.as_dict()["candidates"][0]["id"] == "a"
    assert "exclusion_reason" not in trace.as_dict()["candidates"][0]


def test_explicit_request_opt_in_and_repeatable_json():
    def capture():
        trace = RetrievalDiagnostics(include_request_text=True)
        trace.request("create", "Synthetic question", terms=["question", "question", "synthetic"],
                      source_ids=["b", "a", "a"], asset_ids=["asset_b", "asset_a"], limit=3)
        trace.preparation("b", readiness="unknown", status_available=False)
        trace.preparation("a", readiness="ready", completed_parts=2, total_parts=2)
        return trace.as_dict()
    first = capture()
    assert first["requests"][0]["query"] == "Synthetic question"
    assert first["requests"][0]["terms"] == ["question", "synthetic"]
    assert first["requests"][0]["scope"]["source_ids"] == ["a", "b"]
    assert json.dumps(first, sort_keys=True) == json.dumps(capture(), sort_keys=True)
