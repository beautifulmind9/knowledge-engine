def _brief(source_id):
    return {
        "situation": "Prepare a practical learning note",
        "goal": "Use the supplied knowledge clearly",
        "output_type": "writing",
        "source_ids": [source_id],
    }


def _output(asset_id):
    return {
        "title": "Practical learning note",
        "output_type": "writing",
        "content": "Use practice breaks so participants can apply the material during the session.",
        "applied_knowledge": [
            {
                "asset_id": asset_id,
                "usage_note": "Used the supplied practice guidance.",
            }
        ],
        "design_choices": [
            "Old rationale: allocate a 25-minute practice block.",
        ],
    }


def test_manual_revision_does_not_silently_inherit_parent_design_choices(client, knowledge):
    first_response = client.post(
        "/outputs",
        json={
            "brief": _brief(knowledge["source_id"]),
            "output": _output(knowledge["id"]),
        },
    )
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()

    second_response = client.post(
        f"/outputs/{first['id']}/revise",
        json={
            "instruction": "Replace the old timing",
            "content": "Use a shorter practice activity and keep the revised note grounded in the supplied knowledge.",
        },
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()

    assert first["design_choices"] == ["Old rationale: allocate a 25-minute practice block."]
    assert second["design_choices"] == [
        "Manual revision: Replace the old timing. Source attribution requires review."
    ]
    assert client.get(f"/outputs/{first['id']}").json()["design_choices"] == first["design_choices"]

    exported = client.get(f"/outputs/{second['id']}/export")
    assert exported.status_code == 200
    assert "Old rationale: allocate a 25-minute practice block." not in exported.text
    assert "Manual revision: Replace the old timing. Source attribution requires review." in exported.text


def test_browser_style_unchanged_prefilled_design_choices_are_not_inherited(client, knowledge):
    first = client.post(
        "/outputs",
        json={
            "brief": _brief(knowledge["source_id"]),
            "output": _output(knowledge["id"]),
        },
    ).json()

    second_response = client.post(
        f"/outputs/{first['id']}/revise",
        json={
            "instruction": "Refresh revision metadata",
            "content": "Use a shorter practice activity and keep the revised note grounded in the supplied knowledge.",
            # The browser historically prefilled this textarea and submitted it
            # unchanged even when the user only edited content.
            "design_choices": first["design_choices"],
        },
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()

    assert second["design_choices"] == [
        "Manual revision: Refresh revision metadata. Source attribution requires review."
    ]
    exported = client.get(f"/outputs/{second['id']}/export")
    assert exported.status_code == 200
    assert "Old rationale: allocate a 25-minute practice block." not in exported.text


def test_manual_revision_can_supply_revised_design_choices(client, knowledge):
    first = client.post(
        "/outputs",
        json={
            "brief": _brief(knowledge["source_id"]),
            "output": _output(knowledge["id"]),
        },
    ).json()

    second_response = client.post(
        f"/outputs/{first['id']}/revise",
        json={
            "instruction": "Replace the old timing",
            "content": "Use a shorter practice activity and keep the revised note grounded in the supplied knowledge.",
            "design_choices": ["Revised rationale: use a shorter practice block."],
        },
    )
    assert second_response.status_code == 200, second_response.text
    assert second_response.json()["design_choices"] == [
        "Revised rationale: use a shorter practice block.",
        "Manual revision: Replace the old timing. Source attribution requires review.",
    ]
