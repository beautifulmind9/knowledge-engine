"""Hosted retrieval applies capacity preflight before loading asset payloads."""
from contextlib import contextmanager

import pytest

from app.persistence.phase3 import MARKER, Phase3Coordinator
from app.persistence.partitions import PartitionCapacityExceeded


class Tx:
    workspace = 'synthetic-workspace'

    def __init__(self, count, size):
        self.count = count
        self.size = size
        self.all_calls = []
        self.one_calls = []
        self.execute_calls = []

    def execute(self, sql, params=()):
        self.execute_calls.append((sql, params))

    def _one(self, sql, params):
        self.one_calls.append((sql, params))
        if "payload->'partition'" in sql:
            return {'marker': MARKER}
        assert 'count(*) AS item_count' in sql
        assert 'sum(pg_column_size(a.payload))' in sql
        return {'item_count': self.count, 'payload_bytes': self.size}

    def _all(self, sql, params):
        self.all_calls.append((sql, params))
        return [{'payload': {'id': 'asset'}}]


def coordinator(tx):
    value = object.__new__(Phase3Coordinator)

    @contextmanager
    def transaction():
        yield tx

    value.transaction = transaction
    return value


@pytest.mark.parametrize('method,args', [
    ('active_assets', {'source_ids': ['source_a']}),
    ('search_candidates', {'tokens': ['narrative'], 'normalized_query': 'narrative',
                           'source_ids': ['source_a']}),
])
def test_oversized_indexed_scope_rejects_before_payload_query(method, args):
    tx = Tx(count=1001, size=1024)
    with pytest.raises(PartitionCapacityExceeded) as error:
        getattr(coordinator(tx), method)(**args, max_items=1000, max_bytes=4 * 1024 * 1024)
    assert error.value.item_count == 1001
    assert tx.all_calls == []
    assert tx.execute_calls == [('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ', ())]


@pytest.mark.parametrize('count,size', [(1000, 1024), (1, 4 * 1024 * 1024)])
def test_indexed_scope_accepts_inclusive_boundaries_and_defensively_bounds_fetch(count, size):
    tx = Tx(count=count, size=size)
    result = coordinator(tx).active_assets(max_items=1000, max_bytes=4 * 1024 * 1024)
    assert result == [{'id': 'asset'}]
    sql, params = tx.all_calls[0]
    assert sql.endswith(' LIMIT %s')
    assert params[-1] == 1001
    assert tx.execute_calls == [('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ', ())]
