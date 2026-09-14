from app.services.knowledge_extraction import _evidence_supported_by_text


def test_evidence_support_accepts_exact_and_ordered_ellipsis():
    text = (
        "Use practice breaks to help participants retain learning. "
        "A facilitator may add examples between the useful excerpts. "
        "Use specific goals and practical activities."
    )

    assert _evidence_supported_by_text(
        "Use practice breaks to help participants retain learning.",
        text,
    )
    assert _evidence_supported_by_text(
        "Use practice breaks to help participants retain learning... "
        "Use specific goals and practical activities.",
        text,
    )
    assert not _evidence_supported_by_text(
        "Use specific goals and practical activities... "
        "Use practice breaks to help participants retain learning.",
        text,
    )


def test_audit_does_not_flag_ordered_ellipsis_evidence(client, source, asset):
    s, c = source
    job = client.post(
        "/knowledge-extractions",
        json={"source_id": s["id"], "chunk_id": c["id"]},
    ).json()["job"]

    submitted = {
        **asset,
        "evidence": (
            "Use practice breaks to help participants retain learning... "
            "Use specific goals and practical activities."
        ),
    }
    result = client.post(
        f"/knowledge-extractions/{job['id']}/results",
        json={"assets": [submitted]},
    )
    assert result.status_code == 200, result.text

    saved = result.json()["assets"][0]
    audit = client.get(f"/sources/{s['id']}/audit").json()
    assert saved["id"] not in audit["evidence_needing_review"]


def test_audit_still_flags_unsupported_evidence(client, source, asset):
    s, c = source
    job = client.post(
        "/knowledge-extractions",
        json={"source_id": s["id"], "chunk_id": c["id"]},
    ).json()["job"]

    submitted = {
        **asset,
        "evidence": "This unsupported evidence does not occur in the source chunk.",
    }
    result = client.post(
        f"/knowledge-extractions/{job['id']}/results",
        json={"assets": [submitted]},
    )
    assert result.status_code == 200, result.text

    saved = result.json()["assets"][0]
    audit = client.get(f"/sources/{s['id']}/audit").json()
    assert saved["id"] in audit["evidence_needing_review"]
