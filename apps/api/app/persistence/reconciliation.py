"""Conservative three-way merge for independent hosted snapshot mutations."""
from copy import deepcopy
from typing import Any


class StateReconciliationConflict(ValueError):
    """Concurrent edits overlap and cannot be merged without choosing a winner."""


_RECORD_LISTS = {
    "libraries", "sources", "extraction_jobs", "knowledge_assets", "outputs",
}


def _merge_record_list(base: list, local: list, latest: list, path: str) -> list:
    def index(items):
        if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in items):
            raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
        result = {item["id"]: item for item in items}
        if len(result) != len(items):
            raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
        return result

    before, ours, theirs = index(base), index(local), index(latest)
    merged = {}
    for record_id in before.keys() | ours.keys() | theirs.keys():
        b, l, r = before.get(record_id), ours.get(record_id), theirs.get(record_id)
        record_path = f"{path}.{record_id}"
        if b is None:
            if l is not None and r is not None and l != r:
                raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
            if l is not None or r is not None:
                merged[record_id] = deepcopy(l if l is not None else r)
        elif l is None:
            if r is not None and r != b:
                raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
        elif r is None:
            if l != b:
                raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
        else:
            merged[record_id] = _merge_value(b, l, r, record_path)

    # Preserve a one-sided reorder. If both writers reorder the same collection
    # differently, fail closed rather than silently choosing one ordering.
    base_ids = set(before)
    merged_base_ids = base_ids & set(merged)
    base_order = [item["id"] for item in base if item["id"] in merged_base_ids]
    local_base_order = [item["id"] for item in local if item["id"] in merged_base_ids]
    latest_base_order = [item["id"] for item in latest if item["id"] in merged_base_ids]
    local_reordered = local_base_order != base_order
    latest_reordered = latest_base_order != base_order
    if local_reordered and latest_reordered and local_base_order != latest_base_order:
        raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
    order = local_base_order if local_reordered else latest_base_order
    order.extend(item["id"] for item in latest if item["id"] in merged and item["id"] not in order)
    order.extend(item["id"] for item in local if item["id"] in merged and item["id"] not in order)
    return [merged[record_id] for record_id in order]


def _merge_usage_calls(base: dict, local: dict, latest: dict, path: str) -> int | None:
    """Add concurrent call increments instead of losing one allowance count."""
    before, ours, theirs = base.get("calls", 0), local.get("calls"), latest.get("calls")
    base_day = base.get("day")
    same_new_day = (
        base_day is None and not base.get("calls")
        and local.get("day") and local.get("day") == latest.get("day")
    )
    if (isinstance(before, int) and isinstance(ours, int) and isinstance(theirs, int)
            and (same_new_day or (base_day is not None and local.get("day") == base_day
                                  and latest.get("day") == base_day))
            and ours >= before and theirs >= before):
        if ours != before and theirs != before:
            return before + (ours - before) + (theirs - before)
    return None


def _merge_value(base: Any, local: Any, latest: Any, path: str) -> Any:
    if path == "usage" and all(isinstance(value, dict) for value in (base, local, latest)):
        incremented = _merge_usage_calls(base, local, latest, "usage.calls")
        if incremented is not None:
            without_calls = lambda value: {key: item for key, item in value.items() if key != "calls"}
            result = _merge_value(without_calls(base), without_calls(local), without_calls(latest), "usage_fields")
            result["calls"] = incremented
            return result
    if local == base:
        return deepcopy(latest)
    if latest == base:
        return deepcopy(local)
    if local == latest:
        return deepcopy(local)

    if isinstance(base, dict) and isinstance(local, dict) and isinstance(latest, dict):
        result = {}
        for key in base.keys() | local.keys() | latest.keys():
            b, l, r = base.get(key), local.get(key), latest.get(key)
            has_b, has_l, has_r = key in base, key in local, key in latest
            child_path = f"{path}.{key}" if path else key
            if path == "usage" and key == "calls" and has_b and has_l and has_r:
                incremented = _merge_usage_calls(base, local, latest, child_path)
                if incremented is not None:
                    result[key] = incremented
                    continue
            if not has_l:
                if not has_r:
                    continue
                if not has_b:
                    result[key] = deepcopy(r)
                elif r != b:
                    raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
                continue
            if not has_r:
                if not has_b:
                    result[key] = deepcopy(l)
                elif l != b:
                    raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
                continue
            if not has_b:
                if l != r:
                    raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
                result[key] = deepcopy(l)
                continue
            result[key] = _merge_value(b, l, r, child_path)
        return result

    if (isinstance(base, list) and isinstance(local, list) and isinstance(latest, list)
            and path in _RECORD_LISTS):
        return _merge_record_list(base, local, latest, path)

    raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")


def merge_state_snapshots(base: dict, local: dict, latest: dict) -> dict:
    """Reapply only local JSON changes to the newest snapshot; conflicts fail closed."""
    if not all(isinstance(value, dict) for value in (base, local, latest)):
        raise StateReconciliationConflict("Concurrent state changes could not be reconciled safely.")
    return _merge_value(base, local, latest, "")
