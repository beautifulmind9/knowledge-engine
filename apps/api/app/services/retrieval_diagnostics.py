"""Opt-in lexical retrieval explanations, kept separate from answer contracts.

The collector does no IO and never reads source content or preparation state.
Callers pass facts from the retrieval path they actually execute. Titles, source
excerpts and full requests are omitted by default. Matched terms and opaque IDs
can still be sensitive: inspect locally and do not commit real-user captures.
"""
from copy import deepcopy
from hashlib import sha256
from math import isfinite


_CONTRIBUTION_FIELDS = {
    "term", "field", "points", "weight", "strength", "section", "bonus",
    "matched_variant", "section_weight", "field_weight", "kind",
}
_PREPARATION_FIELDS = {
    "readiness", "completed_parts", "total_parts", "completed_sections",
    "total_sections", "prepared_sections", "has_usable_knowledge",
    "attention_category", "file_state", "read_state", "operation",
    "candidate_count", "positive_match_count", "retained_asset_count",
    "retained_group_count", "status_available",
}


def _scalar(value):
    return value is None or isinstance(value, (str, bool, int)) or (
        isinstance(value, float) and isfinite(value)
    )


def _strings(values):
    if isinstance(values, str):
        values = [values]
    return sorted({value for value in (values or ()) if isinstance(value, str) and value})


def _asset_id(asset):
    return asset.get("id") if isinstance(asset, dict) else asset


def _identity(asset):
    return {field: asset[field] for field in ("id", "source_id", "chunk_id")
            if isinstance(asset.get(field), str)}


class RetrievalDiagnostics:
    """A deterministic JSON-safe collector for optional development diagnostics.

    ``candidate`` records score explanations; ``ranked`` records raw-pool cuts;
    ``groups`` records consolidation and final result cuts. These methods accept
    the real retrieval objects but copy only allowlisted identity/scoring facts.
    ``preparation`` accepts existing readiness facts, without deriving relevance
    or evidence sufficiency from preparation state.
    """

    def __init__(self, include_request_text=False):
        self.include_request_text = include_request_text
        self._requests = []
        self._candidates = {}
        self._groups = []
        self._final_selection = []
        self._result_limit = None
        self._preparation = {}

    def request(self, pipeline, query="", scope=None, limit=None, terms=(), *,
                source_ids=(), library_id=None, asset_ids=(), output_type=None,
                acquisition=None):
        scope = scope or {}
        selected = {}
        for field in ("source_id", "library_id", "asset_type"):
            value = scope.get(field)
            if isinstance(value, str):
                selected[field] = value
        for field in ("source_ids", "asset_ids"):
            if field in scope:
                selected[field] = _strings(scope[field])
        if source_ids:
            selected["source_ids"] = _strings(source_ids)
        if library_id is not None:
            selected["library_id"] = library_id
        if asset_ids:
            selected["asset_ids"] = _strings(asset_ids)
        query = str(query or "")
        record = {"pipeline": str(pipeline), "query_sha256": sha256(query.encode()).hexdigest(),
                  "query_character_count": len(query), "terms": _strings(terms), "scope": selected}
        if limit is not None:
            record["limit"] = limit
        if output_type is not None:
            record["output_type"] = output_type
        if acquisition is not None:
            record["candidate_acquisition"] = acquisition
        if self.include_request_text:
            record["query"] = query
        self._requests.append(record)

    def candidate(self, asset, score=0, matched_terms=(), contributions=(), reason=None,
                  rank=None, *, exclusion_reason=None):
        asset_id = _asset_id(asset)
        if not isinstance(asset_id, str):
            return
        record = self._candidates.setdefault(asset_id, {})
        record.update(_identity(asset) if isinstance(asset, dict) else {"id": asset_id})
        record.update(score=score if _scalar(score) else None,
                      matched_terms=_strings(matched_terms),
                      contributions=[{key: value for key, value in contribution.items()
                                      if key in _CONTRIBUTION_FIELDS and _scalar(value)}
                                     for contribution in contributions if isinstance(contribution, dict)])
        if rank is not None:
            record["position_before_consolidation"] = rank
        reason = exclusion_reason or reason
        if reason is not None:
            record["exclusion_reason"] = reason
            record["retained_within_limit"] = False

    def ranked(self, items, *, retained=None, exclusion_reason="candidate_limit"):
        items = list(items)
        kept = {_asset_id(item) for item in (items if retained is None else retained)}
        for position, item in enumerate(items, 1):
            asset_id = _asset_id(item)
            if not isinstance(asset_id, str):
                continue
            record = self._candidates.setdefault(asset_id, {"id": asset_id})
            if isinstance(item, dict):
                record.update(_identity(item))
            record["position_before_consolidation"] = position
            record["retained_in_candidate_pool"] = asset_id in kept
            if asset_id not in kept:
                record.update(exclusion_reason=exclusion_reason, retained_within_limit=False)

    def groups(self, groups, limit=None, selected_groups=None, *, retained=None,
               exclusion_reason="result_limit"):
        groups = list(groups)
        self._result_limit = limit
        selected = retained if retained is not None else selected_groups
        if selected is None:
            selected = groups if limit is None else groups[:limit]
        positions = {tuple(group.get("asset_ids", ())): position
                     for position, group in enumerate(selected, 1)}
        self._groups = []
        self._final_selection = []
        for position, group in enumerate(groups, 1):
            member_ids = list(group.get("asset_ids", ()))
            final_position = positions.get(tuple(member_ids))
            canonical = group.get("canonical_asset", {})
            record = {"canonical_asset_id": canonical.get("id", group.get("asset_id")),
                      "asset_ids": member_ids, "source_ids": _strings(group.get("source_ids")),
                      "position_after_consolidation": position,
                      "position_in_results": final_position,
                      "retained_within_limit": final_position is not None,
                      "provenance": [{key: evidence[key] for key in ("asset_id", "source_id", "chunk_id")
                                      if isinstance(evidence.get(key), str)}
                                     for evidence in group.get("evidence_trail", ())
                                     if isinstance(evidence, dict)]}
            if final_position is None:
                record["exclusion_reason"] = exclusion_reason
            self._groups.append(record)
            if final_position is not None:
                self._final_selection.append({
                    "position": final_position,
                    "canonical_asset_id": record["canonical_asset_id"],
                    "asset_ids": list(member_ids),
                    "source_ids": list(record["source_ids"]),
                })
            for asset_id in member_ids:
                member = self._candidates.setdefault(asset_id, {"id": asset_id})
                member.update(canonical_asset_id=record["canonical_asset_id"],
                              position_after_consolidation=position,
                              position_in_results=final_position,
                              retained_within_limit=final_position is not None)
                if final_position is None:
                    member["exclusion_reason"] = exclusion_reason
                else:
                    member.pop("exclusion_reason", None)

    def preparation(self, source_id, **facts):
        if not isinstance(source_id, str):
            return
        record = self._preparation.setdefault(source_id, {"source_id": source_id})
        record.update({key: value for key, value in facts.items()
                       if key in _PREPARATION_FIELDS and _scalar(value)})

    def as_dict(self):
        return deepcopy({"schema_version": 2, "requests": self._requests,
                         "result_limit": self._result_limit,
                         "candidates": [self._candidates[key] for key in sorted(self._candidates)],
                         "groups": self._groups,
                         "final_selection": sorted(self._final_selection, key=lambda row: row["position"]),
                         "preparation": [self._preparation[key] for key in sorted(self._preparation)]})
