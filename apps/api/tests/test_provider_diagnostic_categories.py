import json

from app.services import ai_gateway


PRIVATE_TEXT = "PRIVATE_BOOK_PASSAGE_DO_NOT_LOG"
PRIVATE_KEY = "PRIVATE_API_KEY_DO_NOT_LOG"


class BadRequestError(Exception):
    status_code = 400

    def __init__(self, message):
        super().__init__(message)
        self.body = {
            "error": {
                "status": "INVALID_ARGUMENT",
                "message": message,
            }
        }


def test_provider_body_can_classify_schema_complexity_without_leaking_message():
    error = BadRequestError(
        "Invalid response schema: schema is too complex and should be simplified. "
        + PRIVATE_TEXT
        + PRIVATE_KEY
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
    error = BadRequestError("Request payload size exceeds limit. " + PRIVATE_TEXT)
    diagnostic = ai_gateway._provider_diagnostic(error)

    assert diagnostic["message_category"] == "request_size_limit"
    assert PRIVATE_TEXT not in json.dumps(diagnostic)
