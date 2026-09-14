import json
import logging

import httpx
import pytest
from fastapi import HTTPException
from google import genai
from google.genai.errors import ClientError

from app.services import ai_gateway


PRIVATE_TEXT = 'PRIVATE_BOOK_PASSAGE_DO_NOT_LOG'
PRIVATE_KEY = 'PRIVATE_API_KEY_DO_NOT_LOG'


@pytest.mark.parametrize('status', [400, 429, 503, 0])
def test_real_sdk_failure_diagnostic_is_safe_and_single_attempt(monkeypatch, caplog, status):
    original_client = genai.Client
    attempts = []
    secret_message = f'Invalid response schema: {PRIVATE_TEXT} key={PRIVATE_KEY}'
    def transport(request):
        attempts.append(request)
        if status == 0:
            raise httpx.ReadTimeout(secret_message, request=request)
        return httpx.Response(status, json={'error': {'code': 'INVALID_ARGUMENT', 'message': secret_message}},
                              headers={'private-header': PRIVATE_KEY})
    def factory(**kwargs):
        kwargs['http_options'].update(client_args={'transport': httpx.MockTransport(transport), 'trust_env': False},
                                      async_client_args={'trust_env': False})
        return original_client(**kwargs)
    monkeypatch.setattr(ai_gateway.genai, 'Client', factory)
    monkeypatch.setenv('GEMINI_API_KEY', PRIVATE_KEY)
    monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED', 'true')
    with caplog.at_level(logging.WARNING, logger=ai_gateway.__name__):
        with pytest.raises(HTTPException) as failure:
            ai_gateway.generate('fixture-model', {'chunk_text': PRIVATE_TEXT, 'input': PRIVATE_TEXT}, {'type': 'object'})
    assert failure.value.status_code == (429 if status == 429 else 502)
    assert len(attempts) == 1 and ai_gateway.status()['calls_today'] == 1
    logs = [r for r in caplog.records if r.name == ai_gateway.__name__]
    assert len(logs) == 1 and logs[0].exc_info is None
    diagnostic = json.loads(logs[0].getMessage().split('diagnostic: ', 1)[1])
    assert PRIVATE_TEXT not in caplog.text and PRIVATE_KEY not in caplog.text
    assert PRIVATE_TEXT not in failure.value.detail and PRIVATE_KEY not in failure.value.detail
    if status:
        assert diagnostic['status_code'] == status
        assert diagnostic['exception_type'] == {400: 'BadRequestError', 429: 'RateLimitError', 503: 'InternalServerError'}[status]
        assert diagnostic['provider_code'] == 'INVALID_ARGUMENT'
        assert diagnostic['message_category'] == 'response_schema_rejected'
    else:
        assert diagnostic['exception_type'] == 'APITimeoutError'
        assert diagnostic['message_category'] == 'transport_timeout'
    if status == 429:
        assert ai_gateway.status()['paused']
        with pytest.raises(HTTPException):
            ai_gateway.generate('fixture-model', {}, {})
        assert len(attempts) == 1 and ai_gateway.status()['calls_today'] == 1


def test_metadata_and_message_cannot_echo_source_or_key():
    error = ClientError(400, {'error': {'status': 'INVALID_ARGUMENT',
                                      'message': PRIVATE_TEXT + PRIVATE_KEY}})
    diagnostic = ai_gateway._provider_diagnostic(error)
    assert diagnostic == {'exception_type': 'ClientError', 'code': 400,
                          'provider_status': 'INVALID_ARGUMENT', 'message_category': 'provider_message_omitted'}
    error.status = PRIVATE_TEXT
    error.reason = PRIVATE_KEY
    error.code = PRIVATE_KEY
    assert PRIVATE_TEXT not in json.dumps(ai_gateway._provider_diagnostic(error))
    assert PRIVATE_KEY not in json.dumps(ai_gateway._provider_diagnostic(error))


def test_unknown_exception_names_are_not_logged():
    error = type(PRIVATE_TEXT, (Exception,), {})(PRIVATE_KEY)
    assert ai_gateway._provider_diagnostic(error)['exception_type'] == 'OtherProviderError'
