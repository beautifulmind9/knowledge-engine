"""Offline research proof only. Not imported by application or a live runner.

Mock totals below are deliberately invented TEST DATA, never measurements.
No SDK client, credentials, HTTP transport, allowance or dispatch path is added.
"""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from types import SimpleNamespace

import pytest
from google import genai
from google.genai import models, types
from app.db import mock_data as db
from app.services import ai_gateway, source_answer
from app.services.source_context import build_source_context, validate_citations, verify_snapshot
from test_source_search import ROOT, upload

MODEL = 'models/' + source_answer.DEFAULT_MODEL
MOCK_INPUT_TOKENS = 123  # Fixture, not a computed or provider token count.


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class FrozenCandidate:
    """Immutable complete GenerateContentRequest; transport never lives here."""
    encoded: str

    @property
    def request(self):return json.loads(self.encoded)

    @property
    def fingerprint(self):return digest(self.request)

    def counting(self):
        return self.request['model']+':countTokens', {'generateContentRequest': self.request}

    def generation(self):
        body=self.request
        model=body.pop('model')
        return model+':generateContent',body


def freeze(data,schema):
    # Use the installed SDK's REAL serializer, not a hand-waved text equivalence.
    params=types._GenerateContentParameters(
        model=source_answer.DEFAULT_MODEL,
        contents=json.dumps(data,ensure_ascii=False),
        config=types.GenerateContentConfig(
            response_mime_type='application/json',response_json_schema=schema,
            max_output_tokens=4096,automatic_function_calling={'disable':True}))
    wire=models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False),params)
    model=wire.pop('_url')['model']
    assert set(wire)=={'contents','generationConfig'}
    return FrozenCandidate(canonical({'model':model,**wire}))


def mock_receipt(candidate):
    # Only an offline policy example; the real count response echoes neither hash nor coverage.
    return {'operation':'countTokens','model':MODEL,'request_sha256':candidate.fingerprint,
            'count_body_sha256':digest(candidate.counting()[1]),
            'total_tokens':MOCK_INPUT_TOKENS,'raw_response':{'totalTokens':MOCK_INPUT_TOKENS},
            'coverage_confirmed':True,'verification_method':'OFFLINE_MOCK_ONLY'}


def admit_mock(candidate,receipt):
    """Illustrate proposed checks, without implementing a production verifier."""
    if (candidate.request.get('model')!=MODEL
        or candidate.request.get('generationConfig',{}).get('maxOutputTokens')!=4096
        or not isinstance(receipt,dict) or receipt.get('operation')!='countTokens'
        or receipt.get('model')!=MODEL or receipt.get('request_sha256')!=candidate.fingerprint
        or receipt.get('count_body_sha256')!=digest(candidate.counting()[1])
        or receipt.get('coverage_confirmed') is not True
        or type(receipt.get('total_tokens')) is not int
        or receipt['total_tokens']<=0
        or receipt.get('raw_response',{}).get('totalTokens')!=receipt['total_tokens']):
        raise ValueError('budget_unverified')
    if receipt['total_tokens']>32768 or receipt['total_tokens']+4096>1048576:
        raise ValueError('request_budget_exceeded')
    return candidate.generation()


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    def deny(*a,**kw):raise AssertionError('No provider requests permitted')
    monkeypatch.setattr(genai,'Client',deny)
    monkeypatch.setattr('google.genai._api_client.BaseApiClient.request',deny)


@pytest.fixture
def prepared(client):
    source,_=upload(client,(ROOT/'acceptance/extraction_quality_2026-10-17/source.md').read_text())
    question='What does consent to inspect authorize, and what actions require further consent?'
    package=build_source_context(question,[source['id']])
    data={'instructions':source_answer.INSTRUCTIONS,'question':question,'source_context':package}
    schema=ai_gateway._gemini_response_schema(source_answer.SourceAnswerDocument.model_json_schema())
    schema['$defs']['SourceCitation']['properties']['evidence_ref']['enum']=sorted(e['evidence_ref'] for e in package['evidence'])
    return data,schema,freeze(data,schema)


def test_complete_request_frozen_and_identical_across_count_wrapper_and_dispatch(prepared):
    data,schema,candidate=prepared
    count_path,count_body=candidate.counting();generation_path,generation_body=candidate.generation()
    assert count_path==MODEL+':countTokens'
    assert generation_path==MODEL+':generateContent'
    assert count_body['generateContentRequest']=={'model':MODEL,**generation_body}
    assert json.loads(generation_body['contents'][0]['parts'][0]['text'])==data
    assert generation_body['generationConfig']=={
        'maxOutputTokens':4096,'responseMimeType':'application/json','responseJsonSchema':schema}
    assert candidate==freeze(data,schema)
    changed=candidate.request;changed['contents'][0]['parts'][0]['text']='mutated'
    assert candidate.request!=changed  # callers cannot mutate the frozen request.
    assert not db.knowledge_assets and not db.extraction_jobs


@pytest.mark.parametrize('field',['question','instructions','context','schema','model','output_cap'])
def test_any_changed_request_invalidates_count_receipt(prepared,field):
    data,schema,candidate=prepared;receipt=mock_receipt(candidate);wire=candidate.request
    if field in ('question','instructions','context'):
        payload=json.loads(wire['contents'][0]['parts'][0]['text'])
        if field=='context':payload['source_context']['evidence'][0]['text']+=' changed'
        else:payload[field]+=' changed'
        wire['contents'][0]['parts'][0]['text']=json.dumps(payload,ensure_ascii=False)
    if field=='schema':wire['generationConfig']['responseJsonSchema']['title']='changed'
    if field=='model':wire['model']='models/other'
    if field=='output_cap':wire['generationConfig']['maxOutputTokens']=4095
    with pytest.raises(ValueError,match='budget_unverified'):
        admit_mock(FrozenCandidate(canonical(wire)),receipt)


@pytest.mark.parametrize('failure',['absent','missing_count','negative','zero','boolean','wrong_model',
 'wrong_operation','wrong_hash','wrong_count_body','contradictory','unknown_coverage','oversized'])
def test_missing_or_contradictory_mock_receipts_never_admit(prepared,failure):
    candidate=prepared[2];receipt=mock_receipt(candidate)
    if failure=='absent':receipt=None
    if failure=='missing_count':receipt.pop('total_tokens')
    if failure in ('negative','zero','boolean','oversized'):
        receipt['total_tokens']={'negative':-1,'zero':0,'boolean':True,'oversized':32769}[failure]
        receipt['raw_response']['totalTokens']=receipt['total_tokens']
    if failure=='wrong_model':receipt['model']='models/other'
    if failure=='wrong_operation':receipt['operation']='generateContent'
    if failure=='wrong_hash':receipt['request_sha256']='bad'
    if failure=='wrong_count_body':receipt['count_body_sha256']='bad'
    if failure=='contradictory':receipt['raw_response']['totalTokens']+=1
    if failure=='unknown_coverage':receipt['coverage_confirmed']=False
    with pytest.raises(ValueError,match='budget_unverified|request_budget_exceeded'):
        admit_mock(candidate,receipt)
    assert ai_gateway.status()['calls_today']==0


class FakeApi:
    """Offline object underneath the actual SDK Models module; no HTTP client."""
    vertexai=False
    def __init__(self,response):self.reply=response;self.calls=[]
    def request(self,method,path,body,options):
        self.calls.append((method,path,deepcopy(body)))
        return SimpleNamespace(body=json.dumps(self.reply),headers={})
    def _verify_response(self,response):pass


def mock_result(data):
    evidence=next(e for e in data['source_context']['evidence'] if 'Consent to inspect' in e['text'])
    answer={'disposition':'answered','title':'Synthetic contract response',
        'sections':[{'kind':'source_supported','heading':'Consent','content':'Inspection does not authorize replacing parts.',
        'citations':[{k:evidence[k] for k in ('evidence_ref','start_char','end_char')}|{'quote':evidence['text']}]}],
        'limitations':['Mock fixture, not semantic acceptance.']}
    return {'candidates':[{'content':{'role':'model','parts':[{'text':json.dumps(answer)}]},'finishReason':'STOP'}],
        'usageMetadata':{'promptTokenCount':MOCK_INPUT_TOKENS,'candidatesTokenCount':100,
                         'thoughtsTokenCount':20,'totalTokenCount':MOCK_INPUT_TOKENS+120}}


def validate_mock_generation(response,data,receipt):
    if len(response.candidates or [])!=1 or response.prompt_feedback and response.prompt_feedback.block_reason:
        raise ValueError('response_rejected')
    candidate=response.candidates[0];usage=response.usage_metadata
    if (candidate.finish_reason!=types.FinishReason.STOP or not usage
        or any(type(n) is not int or n<0 for n in
               (usage.prompt_token_count,usage.candidates_token_count,usage.thoughts_token_count))
        or usage.prompt_token_count!=receipt['total_tokens']
        or usage.prompt_token_count>32768 or usage.candidates_token_count+usage.thoughts_token_count>4096
        or not candidate.content or not candidate.content.parts
        or any(p.text is None or p.thought for p in candidate.content.parts)):
        raise ValueError('response_rejected')
    answer=source_answer.SourceAnswerDocument.model_validate_json(''.join(p.text for p in candidate.content.parts))
    validate_citations(data['source_context'],[c.model_dump() for s in answer.sections for c in s.citations])
    return answer


@pytest.mark.parametrize('finish',['STOP','MAX_TOKENS','SAFETY','OTHER','CONTINUATION',None])
def test_actual_sdk_response_contract_and_no_automatic_generation(prepared,finish):
    data,schema,frozen=prepared;receipt=mock_receipt(frozen);admit_mock(frozen,receipt)
    raw=mock_result(data);raw['candidates'][0]['finishReason']=finish
    api=FakeApi(raw)
    # This pinned SDK warns on the newer finish reason, which must still be refused.
    with pytest.warns(UserWarning,match='CONTINUATION') if finish=='CONTINUATION' else nullcontext():
        response=models.Models(api).generate_content(model=source_answer.DEFAULT_MODEL,
            contents=json.dumps(data,ensure_ascii=False),config=types.GenerateContentConfig(
                response_mime_type='application/json',response_json_schema=schema,max_output_tokens=4096,
                automatic_function_calling={'disable':True}))
    assert len(api.calls)==1  # actual installed SDK, all outcomes including truncation
    method,path,body=api.calls[0];body.pop('_url',None)
    assert (path,body)==frozen.generation() and method=='post'
    if finish=='STOP':assert validate_mock_generation(response,data,receipt).disposition=='answered'
    else:
        with pytest.raises(ValueError,match='response_rejected'):validate_mock_generation(response,data,receipt)
    assert verify_snapshot(data['source_context']) and ai_gateway.status()['calls_today']==0


@pytest.mark.parametrize('failure',['missing_usage','missing_thoughts','input_mismatch','output_over','invalid_citation'])
def test_mock_generation_safeguards_retain_original_validation(prepared,failure):
    data,_,candidate=prepared;receipt=mock_receipt(candidate);raw=mock_result(data)
    if failure=='missing_usage':raw.pop('usageMetadata')
    if failure=='missing_thoughts':raw['usageMetadata'].pop('thoughtsTokenCount')
    if failure=='input_mismatch':raw['usageMetadata']['promptTokenCount']+=1
    if failure=='output_over':raw['usageMetadata']['thoughtsTokenCount']=4096
    if failure=='invalid_citation':
        answer=json.loads(raw['candidates'][0]['content']['parts'][0]['text'])
        answer['sections'][0]['citations'][0]['quote']='forged'
        raw['candidates'][0]['content']['parts'][0]['text']=json.dumps(answer)
    response=types.GenerateContentResponse.model_validate(raw)
    with pytest.raises(ValueError):validate_mock_generation(response,data,receipt)


def test_high_level_counting_sdk_cannot_send_full_generation_config(prepared):
    data,schema,_=prepared;api=FakeApi({'totalTokens':MOCK_INPUT_TOKENS})
    with pytest.raises(ValueError,match='not in Gemini Developer API mode'):
        models.Models(api).count_tokens(model=source_answer.DEFAULT_MODEL,contents=json.dumps(data),
            config=types.CountTokensConfig(generation_config={'response_json_schema':schema,'max_output_tokens':4096}))
    assert api.calls==[]


def test_plain_sdk_count_drops_no_unknown_fields_but_has_no_schema_contract(prepared):
    data,_,candidate=prepared;api=FakeApi({'totalTokens':MOCK_INPUT_TOKENS})
    models.Models(api).count_tokens(model=source_answer.DEFAULT_MODEL,contents=json.dumps(data,ensure_ascii=False))
    _,path,body=api.calls[0]
    assert path==candidate.counting()[0] and 'generateContentRequest' not in body
    assert 'generationConfig' not in body  # text count cannot attest schema inclusion.
