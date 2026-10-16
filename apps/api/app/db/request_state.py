"""Request-local legacy-shaped projections for active hosted authority only."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy

view = ContextVar('ke_phase2_view', default=None)
request_mode = ContextVar('ke_request_authority', default=None)


@contextmanager
def legacy_request():
    token=request_mode.set(False)
    try: yield
    finally: request_mode.reset(token)


class LazyProjection:
    def __init__(self,records):
        self.records=records


class ProjectionList(list):
    def __init__(self, name, initial):
        super().__init__(initial)
        self.name = name

    def target(self):
        current = view.get()
        if current is None:return self
        value=current[self.name]
        if isinstance(value,LazyProjection):
            value=deepcopy(value.records);current[self.name]=value
        return value

    def __iter__(self):
        target=self.target()
        return list.__iter__(self) if target is self else iter(target)

    def __len__(self):
        target=self.target()
        return list.__len__(self) if target is self else len(target)

    def __getitem__(self,key):
        target=self.target()
        return list.__getitem__(self,key) if target is self else target[key]

    def __setitem__(self,key,value):
        current=view.get()
        if current is not None and isinstance(current[self.name],LazyProjection) and key==slice(None):
            current[self.name]=list(value);return
        target=self.target()
        if target is self: return list.__setitem__(self,key,value)
        target[key]=value

    def __delitem__(self,key):
        target=self.target()
        if target is self: return list.__delitem__(self,key)
        del target[key]

    def append(self,value):
        target=self.target()
        return list.append(self,value) if target is self else target.append(value)

    def extend(self,values):
        target=self.target()
        return list.extend(self,values) if target is self else target.extend(values)

    def clear(self):
        del self[:]

    def remove(self,value):
        target=self.target()
        return list.remove(self,value) if target is self else target.remove(value)

    def __contains__(self,value): return any(v==value for v in self)
    def __eq__(self,other): return list(self)==other
    def __ne__(self,other): return not self==other
    def copy(self): return list(self)
    def insert(self,index,value):
        target=self.target()
        return list.insert(self,index,value) if target is self else target.insert(index,value)
    def pop(self,index=-1):
        target=self.target()
        return list.pop(self,index) if target is self else target.pop(index)

    def __add__(self,other): return list(self)+list(other)
    def __radd__(self,other): return list(other)+list(self)
    def __deepcopy__(self,memo): return deepcopy(list(self),memo)


@contextmanager
def request_projection(coordinator, source_ids=None, job_id=None, *, preloaded=None):
    from app.db import mock_data as db
    from app.persistence.factory import get_state_store
    names=('libraries','sources','extraction_jobs','knowledge_assets','outputs')
    store=get_state_store()
    with store._lock:
        # Cached snapshots are immutable and replaced only after a confirmed commit.
        # Scoped reads keep a reference, not a full-corpus copy/reload.
        baseline=store._loaded_snapshot
        current={name:(LazyProjection(baseline.get(name,[])) if name in {'knowledge_assets','outputs'}
                       else deepcopy(baseline.get(name,[]))) for name in names}
        current['baseline']=baseline
        current['revision']=store._revision
    current['claims']={}
    current['jobs']={}
    scoped=preloaded if preloaded is not None else coordinator.scoped(source_ids,job_id=job_id,include_jobs=source_ids is not None or job_id is not None)
    chosen={s['id'] for s in scoped['sources']}
    if source_ids is None and job_id is None:
        current['sources']=scoped['sources']
    else:
        requested=set(source_ids or chosen)
        replacements={s['id']:s for s in scoped['sources']}
        current['sources']=[replacements.pop(s['id'],s) for s in current['sources'] if s['id'] not in requested or s['id'] in replacements]
        current['sources'].extend(replacements.values())
    current['extraction_jobs']=scoped.get('extraction_jobs',[])
    current['job_sources']=set(chosen) if source_ids is not None or job_id is not None else set()
    current['generations']=scoped.get('_generations',{})
    token=view.set(current)
    mode_token=request_mode.set(True)
    try:
        yield
    finally:
        view.reset(token)
        request_mode.reset(mode_token)
