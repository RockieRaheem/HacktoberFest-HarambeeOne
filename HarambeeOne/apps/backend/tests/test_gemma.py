import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from fastapi import HTTPException

from harambeeone_api import gemma, support
from harambeeone_api.models import Person, Student, SupportCase


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *_args):
        return False


def valid_result() -> dict:
    return {
        "summary": "The anonymous school obligation is internally consistent.",
        "risk_level": "high",
        "observed_factors": ["A verified school balance remains overdue"],
        "missing_information": [],
        "consistency_flags": [],
        "recommended_action": "A school owner should complete the human review.",
        "safe_public_summary": (
            "An anonymous learner needs support for a verified school obligation."
        ),
    }


def settings():
    return SimpleNamespace(
        gemini_api_key="server-secret-key", gemma_model="gemma-4-26b-a4b-it"
    )


def test_gemma_uses_exact_model_secure_header_and_local_schema(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": "internal scratchpad", "thought": True},
                                {"text": json.dumps(valid_result())},
                            ]
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(gemma, "get_settings", settings)
    monkeypatch.setattr(gemma, "urlopen", fake_urlopen)

    model, result = support._call_gemma(
        case_payload={"campaign_code": "TEST"},
        evidence_image_base64=None,
        evidence_mime_type=None,
    )

    request = captured["request"]
    request_body = json.loads(request.data)
    assert model == "gemma-4-26b-a4b-it"
    assert result["risk_level"] == "high"
    assert result["summary"].startswith("The anonymous school obligation")
    assert request.full_url.endswith("/models/gemma-4-26b-a4b-it:generateContent")
    assert "server-secret-key" not in request.full_url
    assert request.get_header("X-goog-api-key") == "server-secret-key"
    assert captured["timeout"] == 60
    assert "responseMimeType" not in request_body["generationConfig"]
    assert "responseJsonSchema" not in request_body["generationConfig"]
    assert request_body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    prompt = request_body["contents"][0]["parts"][0]["text"]
    assert json.dumps(gemma.GEMMA_REVIEW_SCHEMA, separators=(",", ":")) in prompt


def test_gemma_sends_camel_case_inline_image(monkeypatch) -> None:
    captured = {}
    png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ZxFkAAAAASUVORK5CYII="
    )

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        return FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "```json\n"
                                    + json.dumps(valid_result())
                                    + "\n```"
                                }
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(gemma, "get_settings", settings)
    monkeypatch.setattr(gemma, "urlopen", fake_urlopen)
    support._call_gemma(
        case_payload={"campaign_code": "TEST"},
        evidence_image_base64=png,
        evidence_mime_type="image/png",
    )
    image_part = captured["body"]["contents"][0]["parts"][1]
    assert image_part["inlineData"]["mimeType"] == "image/png"
    assert image_part["inlineData"]["data"] == png


def test_gemma_strips_unexpected_response_fields(monkeypatch) -> None:
    result = valid_result()
    result["learner_name"] = "Must never be accepted"
    monkeypatch.setattr(gemma, "get_settings", settings)
    monkeypatch.setattr(
        gemma,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"candidates": [{"content": {"parts": [{"text": json.dumps(result)}]}}]}
        ),
    )

    _model, cleaned = support._call_gemma(
        case_payload={"campaign_code": "TEST"},
        evidence_image_base64=None,
        evidence_mime_type=None,
    )
    assert "learner_name" not in cleaned
    assert set(cleaned) == set(gemma.GEMMA_REVIEW_SCHEMA["required"])


def test_gemma_reports_rejected_api_key_without_exposing_it(monkeypatch) -> None:
    monkeypatch.setattr(gemma, "get_settings", settings)

    def reject(*_args, **_kwargs):
        raise HTTPError("https://example.invalid", 403, "Forbidden", {}, None)

    monkeypatch.setattr(gemma, "urlopen", reject)

    with pytest.raises(HTTPException) as caught:
        support._call_gemma(
            case_payload={"campaign_code": "TEST"},
            evidence_image_base64=None,
            evidence_mime_type=None,
        )

    assert caught.value.status_code == 502
    assert caught.value.detail == (
        "Gemma rejected the server API key. Check the Google AI Studio key."
    )
    assert "server-secret-key" not in caught.value.detail


def test_gemma_status_never_includes_the_api_key(monkeypatch) -> None:
    monkeypatch.setattr(gemma, "get_settings", settings)
    payload = gemma.gemma_status()
    assert payload == {
        "configured": True,
        "model": "gemma-4-26b-a4b-it",
        "decision_authority": "human",
    }
    assert "server-secret-key" not in json.dumps(payload)


def test_review_identity_scan_rejects_name_in_recommendation() -> None:
    case = SupportCase(public_code="HSP-TEST", title="Anonymous", public_summary="x" * 20)
    student = Student(admission_no="TA-001")
    person = Person(first_name="Amina", last_name="Kato")
    result = valid_result()
    result["recommended_action"] = "Ask the owner to publish support for Amina."
    with pytest.raises(HTTPException, match="must not identify"):
        support._assert_review_identity(case, student, person, result)
