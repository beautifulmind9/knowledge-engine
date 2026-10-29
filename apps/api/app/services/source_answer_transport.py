"""Counted, frozen GenerateContent for the isolated local source-answer experiment.

No automatic counting, repair, fallback or continuation. Generation stays disabled.
Receipts are private local server artifacts, never accepted from request payloads.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
import os
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import httpx

MODEL = 'gemini-3.5-flash-lite'
API_VERSION = 'v1beta'
INPUT_LIMIT = 32768
INPUT_HEADROOM = 8192  # 25% of policy capacity, reserved for count/usage variation.
MAX_COUNT = INPUT_LIMIT - INPUT_HEADROOM
OUTPUT_LIMIT = 4096
POLICY = 'source-answer-count-headroom-v1'
RECEIPT_MAX_AGE = timedelta(hours=24)


class BudgetUnavailable(ValueError):pass
class BudgetExceeded(ValueError):pass


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def sha(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


_generation_permit = ContextVar('source_answer_generation_permit',default=None)


def generation_authorized(request_sha256=None):
    permit=_generation_permit.get()
    return permit is not None and (request_sha256 is None or permit['request_sha256']==request_sha256)


@contextmanager
def _one_shot_generation_scope(request_sha256,marker,audit):
    """Private command capability; never an environment flag or API input."""
    from app.db.persistence import STORAGE_ROOT
    marker=Path(marker)
    if (marker.is_symlink() or marker.resolve()!=STORAGE_ROOT.parent/'audit/generation-intent.json'
        or marker.stat().st_mode&0o077 or marker.stat().st_uid!=os.getuid()):
        raise BudgetUnavailable('Invalid generation intent.')
    intent=json.loads(marker.read_text())
    if (intent.get('request_sha256')!=request_sha256 or intent.get('authorized') is not True
        or intent.get('max_provider_attempts')!=2 or _generation_permit.get() is not None):
        raise BudgetUnavailable('Invalid or nested generation authorization.')
    permit={'request_sha256':request_sha256,'claimed':False,'dispatches':0,'last_http_status':None,'audit':audit}
    token=_generation_permit.set(permit)
    try:yield permit
    finally:_generation_permit.reset(token)


def claim_generation(request_sha256):
    permit=_generation_permit.get()
    if not generation_authorized(request_sha256) or permit['claimed']:
        raise BudgetUnavailable('One-shot generation already claimed or unauthorized.')
    permit['claimed']=True


def _start_dispatch(request):
    permit=_generation_permit.get()
    if (not generation_authorized(request.fingerprint) or not permit['claimed'] or permit['dispatches']>=2
        or permit['dispatches']==1 and permit['last_http_status']!=503):
        raise BudgetUnavailable('Dispatch is outside the one-shot gateway claim.')
    permit['dispatches']+=1
    number=permit['dispatches']
    def audit(event,detail):
        permit['audit'](number,event,{'request_sha256':request.fingerprint,**detail})
    audit('dispatch-intent',{})
    return audit


@dataclass(frozen=True)
class FrozenRequest:
    encoded: str

    @property
    def value(self):return json.loads(self.encoded)
    @property
    def fingerprint(self):return sha(self.value)
    @property
    def counting_body(self):return {'generateContentRequest':self.value}
    @property
    def generation_body(self):
        value=self.value;value.pop('model');return value

    def validate(self):
        try:
            value=self.value
            if (set(value)!={'model','contents','generationConfig'} or value['model']!='models/'+MODEL
                or len(value['contents'])!=1 or set(value['contents'][0])!={'role','parts'}
                or value['contents'][0]['role']!='user' or len(value['contents'][0]['parts'])!=1
                or set(value['contents'][0]['parts'][0])!={'text'}
                or not isinstance(value['contents'][0]['parts'][0]['text'],str)):
                raise BudgetUnavailable('Unsupported experimental request.')
            config=value['generationConfig']
            if (set(config)!={'responseMimeType','responseJsonSchema','maxOutputTokens'}
                or config['responseMimeType']!='application/json' or type(config['maxOutputTokens']) is not int or config['maxOutputTokens']!=OUTPUT_LIMIT
                or not isinstance(config['responseJsonSchema'],dict)):
                raise BudgetUnavailable('Unsupported experimental configuration.')
            return self
        except (KeyError,TypeError,IndexError,AttributeError,json.JSONDecodeError):
            raise BudgetUnavailable('Malformed experimental request.') from None


def freeze(model,payload,schema):
    from app.services.ai_gateway import _gemini_response_schema
    value={'model':'models/'+model,'contents':[{'role':'user','parts':[{'text':json.dumps(payload,ensure_ascii=False)}]}],
           'generationConfig':{'responseMimeType':'application/json','responseJsonSchema':_gemini_response_schema(schema),
                               'maxOutputTokens':OUTPUT_LIMIT}}
    return FrozenRequest(canonical(value)).validate()


@dataclass(frozen=True)
class CountReceipt:
    request_sha256: str
    count_body_sha256: str
    response_sha256: str
    total_tokens: int
    counted_at: str
    model: str = MODEL
    api_version: str = API_VERSION
    policy: str = POLICY
    operation: str = 'countTokens'
    http_status: int = 200


def receipt_from_response(request,response,*,http_status=200,counted_at=None):
    request.validate()
    if http_status!=200 or not isinstance(response,dict) or type(response.get('totalTokens')) is not int or response['totalTokens']<=0:
        raise BudgetUnavailable('Successful nonempty provider count required.')
    if response.get('cachedContentTokenCount',0)!=0:
        raise BudgetUnavailable('Unexpected cached content in stateless count.')
    return CountReceipt(request.fingerprint,sha(request.counting_body),sha(response),response['totalTokens'],
                        counted_at or datetime.now(timezone.utc).isoformat(),http_status=http_status)


def verify_receipt(request,receipt):
    request.validate()
    if (not isinstance(receipt,CountReceipt) or receipt.request_sha256!=request.fingerprint
        or receipt.count_body_sha256!=sha(request.counting_body) or receipt.model!=MODEL
        or receipt.api_version!=API_VERSION or receipt.policy!=POLICY or receipt.operation!='countTokens'
        or receipt.http_status!=200 or type(receipt.total_tokens) is not int or receipt.total_tokens<=0):
        raise BudgetUnavailable('Missing or incompatible trusted count receipt.')
    try:
        age=datetime.now(timezone.utc)-datetime.fromisoformat(receipt.counted_at)
        if age<timedelta(0) or age>RECEIPT_MAX_AGE:raise ValueError()
    except (ValueError,TypeError):raise BudgetUnavailable('Stale or invalid count receipt.') from None
    if receipt.total_tokens+INPUT_HEADROOM>INPUT_LIMIT:
        raise BudgetExceeded('Count leaves insufficient policy headroom.')
    return receipt


class ProviderHTTPError(RuntimeError):
    def __init__(self,status):
        super().__init__('Experimental provider HTTP error.')
        self.status_code=status
        self.code=status


def post(request,operation,key,*,count_authorized=False):
    """One direct REST request, no SDK retry/AFC/continuation or redirect/proxy."""
    request.validate()
    if operation not in ('countTokens','generateContent'):raise BudgetUnavailable('Unsupported operation.')
    if operation=='countTokens' and not count_authorized:raise BudgetUnavailable('Counting is not authorized.')
    if operation=='generateContent' and not generation_authorized(request.fingerprint):raise BudgetUnavailable('Generation is not authorized.')
    body=request.counting_body if operation=='countTokens' else request.generation_body
    url=f'https://generativelanguage.googleapis.com/{API_VERSION}/models/{MODEL}:{operation}'
    audit=_start_dispatch(request) if operation=='generateContent' else lambda *args:None
    try:
        with httpx.Client(timeout=60,trust_env=False,follow_redirects=False,transport=httpx.HTTPTransport(retries=0)) as client:
            response=client.post(url,headers={'x-goog-api-key':key,'Content-Type':'application/json'},content=canonical(body).encode())
    except BaseException:
        audit('transport-interrupted',{'outcome':'unconfirmed'})
        raise
    if operation=='generateContent':_generation_permit.get()['last_http_status']=response.status_code
    if response.status_code!=200:
        audit('http-failure',{'http_status':response.status_code})
        raise ProviderHTTPError(response.status_code)
    try:result=response.json()
    except ValueError:
        audit('response',{'http_status':200,'unvalidated_response_text':response.text})
        raise ValueError('Invalid provider JSON.') from None
    audit('response',{'http_status':200,'provider_response':result})
    if not isinstance(result,dict):raise ValueError('Invalid provider response.')
    return result


def normalize_response(raw,receipt):
    """Do not require count == usage. Refuse missing/contradictory actual counters."""
    usage=raw.get('usageMetadata') or {}
    mapping={'total_input_tokens':'promptTokenCount','total_output_tokens':'candidatesTokenCount',
             'total_thought_tokens':'thoughtsTokenCount','total_tokens':'totalTokenCount'}
    counters={key:usage.get(provider) for key,provider in mapping.items()}
    valid=all(type(value) is int and value>=0 for value in counters.values())
    if valid:
        valid=(counters['total_tokens']==sum(counters[k] for k in ('total_input_tokens','total_output_tokens','total_thought_tokens'))
               and counters['total_input_tokens']<=min(INPUT_LIMIT,receipt.total_tokens+INPUT_HEADROOM)
               and counters['total_output_tokens']+counters['total_thought_tokens']<=OUTPUT_LIMIT)
    valid=valid and usage.get('toolUsePromptTokenCount',0)==0 and usage.get('cachedContentTokenCount',0)==0
    candidates=raw.get('candidates') or []
    candidate=candidates[0] if len(candidates)==1 else {}
    parts=(candidate.get('content') or {}).get('parts') or []
    valid=valid and not (raw.get('promptFeedback') or {}).get('blockReason') and len(candidates)==1
    text=''.join(p.get('text','') for p in parts if isinstance(p,dict) and isinstance(p.get('text',''),str))
    valid=valid and bool(parts) and all(isinstance(p,dict) and set(p)=={'text'} and isinstance(p['text'],str) for p in parts)
    valid=valid and candidate.get('finishReason')=='STOP'
    return SimpleNamespace(output_text=text,status='completed' if valid else 'incomplete',
        errors=[] if valid else ['response_or_usage_invalid'],usage=SimpleNamespace(**counters),
        id=raw.get('responseId'),model_version=raw.get('modelVersion'),
        raw_response=raw,finish_reason=candidate.get('finishReason'),
        usage_difference=(counters['total_input_tokens']-receipt.total_tokens) if type(counters['total_input_tokens']) is int else None)


def load_receipt(request):
    from app.db.persistence import STORAGE_ROOT
    folder=STORAGE_ROOT/'source_answer_counts';path=folder/(request.fingerprint+'.json')
    try:
        if folder.is_symlink() or path.is_symlink() or path.stat().st_mode&0o077 or folder.stat().st_mode&0o077:
            raise ValueError()
        record=json.loads(path.read_text())
        if record['request']!=request.value:raise ValueError()
        response=record['response'];receipt=CountReceipt(**record['receipt'])
        if receipt.response_sha256!=sha(response) or receipt.total_tokens!=response.get('totalTokens'):raise ValueError()
        return verify_receipt(request,receipt)
    except BudgetExceeded:raise
    except (OSError,ValueError,TypeError,KeyError):
        raise BudgetUnavailable('Trusted private receipt unavailable.') from None


def save_receipt(request,receipt,response):
    from app.db.persistence import STORAGE_ROOT
    from app.services.source_answer import _publish_private_json
    if receipt.response_sha256!=sha(response) or receipt.total_tokens!=response.get('totalTokens'):
        raise BudgetUnavailable('Contradictory count evidence.')
    # Oversized counts may be retained for review; loading them never admits generation.
    record={'contract':'source-answer-count-v1','request':request.value,'receipt':asdict(receipt),'response':response}
    _publish_private_json(STORAGE_ROOT/'source_answer_counts',request.fingerprint+'.json',record)
