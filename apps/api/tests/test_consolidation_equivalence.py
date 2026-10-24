"""Full-pool optimization must preserve the pre-KE-PQ-002 grouping rules.

The reference functions below retain the uncached rules from 95c8f65. The
fixtures are synthetic, validated KnowledgeAssets; this is not semantic evidence
that similarly worded findings are equivalent.
"""
from copy import deepcopy
from itertools import product
import random
import re

import pytest
from pydantic import TypeAdapter

from app.models.knowledge_asset import KnowledgeAsset
from app.services import knowledge_extraction as extraction


def legacy_tension(left, right):
    ltext = extraction.normalize_text((left.get("what_it_says") or "") + " " + (left.get("action") or ""))
    rtext = extraction.normalize_text((right.get("what_it_says") or "") + " " + (right.get("action") or ""))
    lt, rt = set(ltext.split()), set(rtext.split())
    if extraction._jaccard(extraction._meaningful_tokens(ltext), extraction._meaningful_tokens(rtext)) < 0.35:
        return False
    neg = {"not", "never", "avoid", "without", "stop", "don", "cannot"}
    opposite = bool(lt & neg) != bool(rt & neg)
    ln, rn = set(re.findall(r"\b\d+\b", ltext)), set(re.findall(r"\b\d+\b", rtext))
    return opposite or bool(ln and rn and ln != rn)


def legacy_similarity(left, right):
    if left.get("asset_type") != right.get("asset_type") or legacy_tension(left, right):
        return 0.0
    left_evidence = extraction.normalize_text(left.get("evidence"))
    right_evidence = extraction.normalize_text(right.get("evidence"))
    if left_evidence and left_evidence == right_evidence:
        return 1.0
    left_title = extraction.normalize_text(left.get("title"))
    right_title = extraction.normalize_text(right.get("title"))
    if left_title and left_title == right_title:
        return 0.98
    title_similarity = extraction._jaccard(extraction._meaningful_tokens(left.get("title")), extraction._meaningful_tokens(right.get("title")))
    content_similarity = extraction._jaccard(extraction._meaningful_tokens(extraction._asset_similarity_text(left)), extraction._meaningful_tokens(extraction._asset_similarity_text(right)))
    if title_similarity >= 0.65 and content_similarity >= 0.35:
        return max(0.80, (title_similarity + content_similarity) / 2)
    return (title_similarity * 0.35) + (content_similarity * 0.65)


def assets():
    rng = random.Random(62002)
    values = []
    templates = [
        ("Audience response measurement", "Measure audience responses using 10 observations.", "Ten observations describe a limited sample."),
        ("Audience response measurement", "Measure audience responses using 20 observations.", "Twenty observations describe a limited sample."),
        ("Audience response measurement", "Do not measure audience responses using 10 observations.", "Ten observations describe a limited sample."),
        ("Measured audience response", "Measure audience responses using 10 observations.", "Independent response evidence."),
        ("Different setting", "Plants need water and suitable soil.", "Plant growth depends on water."),
        ("", "The numbers describe unknown context.", "."),
    ]
    for index in range(54):
        title, text, evidence = templates[index % len(templates)]
        asset_type = rng.choice(["principle", "concept", "decision_rule"])
        data = {"id": f"asset_{index}", "source_id": f"source_{index % 7}", "chunk_id": f"chunk_{index}",
                "asset_type": asset_type, "title": title, "what_it_says": text,
                "evidence": evidence, "keywords": ["measurement", rng.choice(["response", "context", "sample"])],
                "confidence_score": rng.randint(1, 5)}
        if asset_type == "decision_rule":
            data["action"] = rng.choice(["Measure audience responses.", "Never measure audience responses."])
        values.append(TypeAdapter(KnowledgeAsset).validate_python(data).model_dump(mode="json"))
    # Exact duplicates must preserve different source/chunk/asset identities.
    values.extend({**values[0], "id": f"copy_{i}", "source_id": f"copy_source_{i}", "chunk_id": f"copy_chunk_{i}"} for i in range(6))
    return values


def legacy_clusters(items, threshold):
    clusters = []
    for asset in items:
        match = next((cluster for cluster in clusters
                      if all(not legacy_tension(asset, other) for other in cluster)
                      and any(legacy_similarity(asset, other) >= threshold for other in cluster)), None)
        if match is None:
            clusters.append([asset])
        else:
            match.append(asset)
    return sorted(clusters, key=lambda cluster: (len(cluster), extraction._asset_quality_score(max(cluster, key=extraction._asset_quality_score))), reverse=True)


def test_cached_pair_features_preserve_legacy_scores_and_tension():
    for left, right in product(assets(), repeat=2):
        assert extraction.potential_tension(left, right) == legacy_tension(left, right)
        assert extraction.knowledge_asset_similarity(left, right) == legacy_similarity(left, right)


@pytest.mark.parametrize("threshold", [0, 0.35, 0.78, 0.98, 1.0, 1.01])
def test_full_grouping_and_provenance_match_legacy_rules(threshold):
    items = assets()
    original = deepcopy(items)
    expected = legacy_clusters(items, threshold)
    groups = extraction.consolidate_knowledge_assets(items, similarity_threshold=threshold)
    assert [group["asset_ids"] for group in groups] == [[asset["id"] for asset in cluster] for cluster in expected]
    for group, cluster in zip(groups, expected):
        assert group["canonical_asset"] == max(cluster, key=extraction._asset_quality_score)
        assert group["support_count"] == len(cluster)
        assert group["source_ids"] == sorted({asset["source_id"] for asset in cluster})
        assert [(member["asset_id"], member["source_id"], member["chunk_id"], member["evidence"])
                for member in group["evidence_trail"]] == [(asset["id"], asset["source_id"], asset["chunk_id"], asset["evidence"]) for asset in cluster]
    assert items == original


def test_next_consolidation_observes_mutated_evidence_without_a_global_cache():
    original, duplicate = deepcopy(assets()[0]), deepcopy(assets()[0])
    duplicate.update(id="duplicate", source_id="other", chunk_id="other_chunk")
    assert len(extraction.consolidate_knowledge_assets([original, duplicate])) == 1
    duplicate["what_it_says"] = "Do not measure audience responses using 10 observations."
    assert len(extraction.consolidate_knowledge_assets([original, duplicate])) == 2
