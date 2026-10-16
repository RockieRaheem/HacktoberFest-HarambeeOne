"""Run a privacy-safe live smoke test against the configured Gemma model."""

from fastapi import HTTPException

from harambeeone_api.gemma import call_gemma


def main() -> None:
    try:
        model, result = call_gemma(
            case_payload={
                "campaign_code": "LIVE-SMOKE-TEST",
                "need_category": "fees",
                "target_amount": "350000.00",
                "currency": "UGX",
                "rule_based_risk": "high",
                "rule_based_reasons": ["A verified school obligation remains overdue"],
                "draft_public_summary": (
                    "An anonymous learner needs support for a verified school obligation."
                ),
            },
            evidence_image_base64=None,
            evidence_mime_type=None,
        )
    except HTTPException as error:
        raise SystemExit(f"Gemma live verification failed: {error.detail}") from error
    assert model == "gemma-4-26b-a4b-it"
    assert result["safe_public_summary"]
    print(f"Gemma live verification passed: model={model} risk={result['risk_level']}")


if __name__ == "__main__":
    main()
