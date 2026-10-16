import base64
import binascii
import json
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException, status

from harambeeone_api.config import get_settings

GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ALLOWED_EVIDENCE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_EVIDENCE_BYTES = 6_000_000
GEMMA_SYSTEM_INSTRUCTION = (
    "You are the privacy-safe review assistant for a Ugandan school support programme. "
    "Use only the supplied anonymous financial facts and optional redacted evidence image. "
    "Do not infer identity, health, disability, gender, pregnancy, abuse, ethnicity "
    "or family details. Do not claim fraud or predict that a learner will drop out. "
    "Flag uncertainty for human review. Never issue a final eligibility, publication, fraud "
    "or financial decision. The safe public summary must contain no invented facts."
)
GEMMA_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 20, "maxLength": 500},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "review"]},
        "observed_factors": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 180},
            "maxItems": 8,
        },
        "missing_information": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 180},
            "maxItems": 8,
        },
        "consistency_flags": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 180},
            "maxItems": 8,
        },
        "recommended_action": {"type": "string", "minLength": 10, "maxLength": 500},
        "safe_public_summary": {"type": "string", "minLength": 20, "maxLength": 500},
    },
    "required": [
        "summary",
        "risk_level",
        "observed_factors",
        "missing_information",
        "consistency_flags",
        "recommended_action",
        "safe_public_summary",
    ],
    "additionalProperties": False,
}
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def gemma_status() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "configured": bool(settings.gemini_api_key),
        "model": settings.gemma_model,
        "decision_authority": "human",
    }


def call_gemma(
    *,
    case_payload: dict,
    evidence_image_base64: str | None,
    evidence_mime_type: str | None,
) -> tuple[str, dict]:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemma review is not configured. Add GEMINI_API_KEY to the server environment.",
        )
    parts: list[dict[str, Any]] = [
        {
            "text": (
                "Review these anonymous case facts. Return only one JSON object with no "
                "markdown or commentary. It must match this schema exactly: "
                f"{json.dumps(GEMMA_REVIEW_SCHEMA, separators=(',', ':'))}. "
                "Anonymous case facts: "
                f"{json.dumps(case_payload, separators=(',', ':'))}"
            )
        }
    ]
    if evidence_image_base64 and evidence_mime_type:
        parts.append(_evidence_part(evidence_image_base64, evidence_mime_type))
    last_error: Exception | None = None
    for attempt in range(2):
        generation_config: dict[str, Any] = {
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "temperature": 0.1,
            "maxOutputTokens": 4096,
        }
        request = Request(
            GEMINI_GENERATE_URL.format(model=settings.gemma_model),
            data=json.dumps(
                {
                    "systemInstruction": {"parts": [{"text": GEMMA_SYSTEM_INSTRUCTION}]},
                    "contents": [{"role": "user", "parts": parts}],
                    "generationConfig": generation_config,
                }
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Goog-Api-Key": settings.gemini_api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed Google API origin
                api_result = json.load(response)
            return settings.gemma_model, _validated_review(_parse_model_json(api_result))
        except HTTPError as error:
            last_error = error
            if error.code >= 500 and attempt == 0:
                time.sleep(1.5)
                continue
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=_http_error_detail(error, settings.gemma_model),
            ) from error
        except (URLError, TimeoutError) as error:
            last_error = error
            if attempt == 0:
                time.sleep(1.5)
                continue
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemma could not be reached. The case remains safe to review manually.",
            ) from error
        except (KeyError, IndexError, TypeError, ValueError) as error:
            last_error = error
            if attempt == 0:
                time.sleep(1.5)
                continue
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemma returned an invalid review. No case data was changed.",
            ) from error
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Gemma is temporarily unavailable. The case remains safe to review manually.",
    ) from last_error


def _evidence_part(image_base64: str, mime_type: str) -> dict[str, Any]:
    if mime_type not in ALLOWED_EVIDENCE_TYPES:
        raise HTTPException(status_code=422, detail="Evidence image must be JPEG, PNG or WebP")
    try:
        raw = base64.b64decode(image_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise HTTPException(
            status_code=422, detail="Evidence image is not valid base64"
        ) from error
    if not raw or len(raw) > MAX_EVIDENCE_BYTES:
        raise HTTPException(
            status_code=422, detail="Use a redacted evidence image smaller than 6 MB"
        )
    return {"inlineData": {"mimeType": mime_type, "data": image_base64}}


def _parse_model_json(api_result: dict) -> dict:
    candidate = api_result["candidates"][0]
    if candidate.get("finishReason") not in {None, "STOP"}:
        raise ValueError("Gemma response did not finish normally")
    parts = candidate.get("content", {}).get("parts") or []
    text = "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict) and "text" in part and not part.get("thought")
    )
    cleaned = _FENCE.sub("", text.strip()).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Gemma response did not contain JSON")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Gemma response was not a JSON object")
    return parsed


def _validated_review(result: dict) -> dict:
    risk = str(result.get("risk_level") or "").strip().casefold()
    if risk not in {"low", "medium", "high", "review"}:
        raise ValueError("Gemma returned an invalid review structure")
    cleaned: dict[str, Any] = {"risk_level": risk}
    for key in ("observed_factors", "missing_information", "consistency_flags"):
        value = result.get(key, [])
        if value is None:
            value = []
        if not isinstance(value, list) or len(value) > 8:
            raise ValueError("Gemma returned an invalid review structure")
        items = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("Gemma returned an invalid review structure")
            text = item.strip()
            if not text:
                continue
            if len(text) > 180:
                raise ValueError("Gemma returned an invalid review structure")
            items.append(text)
        cleaned[key] = items
    for key, minimum, label in (
        ("summary", 20, "summary"),
        ("recommended_action", 10, "recommendation"),
        ("safe_public_summary", 20, "public summary"),
    ):
        value = result.get(key)
        if not isinstance(value, str) or not minimum <= len(value.strip()) <= 500:
            raise ValueError(f"Gemma returned an invalid review {label}")
        cleaned[key] = value.strip()
    return cleaned


def _http_error_detail(error: HTTPError, model_name: str) -> str:
    if error.code in {401, 403}:
        return "Gemma rejected the server API key. Check the Google AI Studio key."
    if error.code == 429:
        return "Gemma quota is temporarily exhausted. Try again shortly."
    if error.code == 404:
        return f"Gemma model {model_name} is unavailable for this API key."
    return "Gemma is temporarily unavailable. The case remains safe to review manually."
