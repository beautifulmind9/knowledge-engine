import json

from app.services import ai_gateway


PRIVATE_TEXT = "PRIVATE_BOOK_PASSAGE_DO_NOT_LOG"
PRIVATE_KEY = "PRIVATE_API_KEY_DO_NOT_LOG"


class BadRequestError(Exception):
    status_code = 400

    def __init__(self, message, body=None, response=None):
        super().__init__(message)
        self.body = body
        self.response = response


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_provider_body_can_classify_schema_complexity_without_leaking_message():
    message = (
        "Invalid response schema: schema is too complex and should be simplified. "
        + PRIVATE_TEXT
        + PRIVATE_KEY
    )
    error = BadRequestError(
        message,
        body={"error": {"status": "INVALID_ARGUMENT", "message": message}},
    )
    diagnostic = ai_gateway._provider_diagnostic(error)

    assert diagnostic["exception_type"] == "BadRequestError"
    assert diagnostic["status_code"] == 400
    assert diagnostic["provider_status"] == "INVALID_ARGUMENT"
    assert diagnostic["message_category"] == "response_schema_complexity_or_size"
    serialized = json.dumps(diagnostic)
    assert PRIVATE_TEXT not in serialized
    assert PRIVATE_KEY not in serialized


def test_provider_body_can_classify_request_size_without_leaking_message():
    message = "Request payload size exceeds limit. " + PRIVATE_TEXT
    error = BadRequestError(
        message,
        body={"error": {"message": message}},
    )
    diagnostic = ai_gateway._provider_diagnostic(error)

    assert diagnostic["message_category"] == "request_size_limit"
    assert PRIVATE_TEXT not in json.dumps(diagnostic)


def test_provider_status_can_classify_failed_precondition_without_leaking_message():
    message = "Precondition check failed. " + PRIVATE_TEXT
    error = BadRequestError(
        message,
        body={"error": {"status": "FAILED_PRECONDITION", "message": message}},
    )
    diagnostic = ai_gateway._provider_diagnostic(error)

    assert diagnostic["provider_status"] == "FAILED_PRECONDITION"
    assert diagnostic["message_category"] == "provider_precondition_failed"
    assert PRIVATE_TEXT not in json.dumps(diagnostic)


def test_response_json_can_classify_real_interactions_error_without_leaking_message():
    message = "Unknown parameter in response_format. " + PRIVATE_TEXT + PRIVATE_KEY
    error = BadRequestError(
        "Bad request",
        response=FakeResponse(
            {
                "error": {
                    "code": "parameter_unknown",
                    "message": message,
                    "type": "invalid_request_error",
                }
            }
        ),
    )
    diagnostic = ai_gateway._provider_diagnostic(error)

    assert diagnostic["provider_code"] == "parameter_unknown"
    assert diagnostic["provider_type"] == "invalid_request_error"
    assert diagnostic["message_category"] == "unknown_request_parameter"
    serialized = json.dumps(diagnostic)
    assert PRIVATE_TEXT not in serialized
    assert PRIVATE_KEY not in serialized


def test_response_json_generic_invalid_request_is_fixed_category_only():
    error = BadRequestError(
        "Bad request",
        response=FakeResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": PRIVATE_TEXT,
                }
            }
        ),
    )
    diagnostic = ai_gateway._provider_diagnostic(error)
    assert diagnostic["message_category"] == "invalid_request_generic"
    assert PRIVATE_TEXT not in json.dumps(diagnostic)
