"""mask_secrets (7.1 §2.10): what an A3 card shows the owner keeps the
recipients and the amounts, and masks only credentials (by value and by key)."""

from __future__ import annotations

from hq_common.redact import MASK, is_credential_key, mask_secrets, scrub

ANT = "sk-ant-" + "a" * 30
GH = "ghp_" + "b" * 36
PHONE = "0912" + "345" + "6789"
CARD = "4111 1111 1111 1111"
IBAN = "IR" + "06" + "0120" * 5 + "0000"


def test_credentials_go_personal_data_and_amounts_stay() -> None:
    args = {
        "to": "sara@example.com",
        "phone": PHONE,
        "card_number": CARD,
        "iban": IBAN,
        "amount": 1_500_000,
        "currency": "IRR",
        "body": f"Pay 1500 USD to {PHONE}. Authorization: Bearer {GH}",
        "api_key": "plain-value-123",
        "headers": [{"name": "X-Client-Secret", "value": "s3cr3t-v4lue"}],
        "nested": {"password": "hunter2!!", "note": f"key {ANT}"},
        "ok": True,
        "none": None,
    }
    out = mask_secrets(args)
    assert out["to"] == "sara@example.com" and out["phone"] == PHONE
    assert out["card_number"] == CARD and out["iban"] == IBAN
    assert out["amount"] == 1_500_000 and out["currency"] == "IRR"
    assert "Pay 1500 USD to " + PHONE in out["body"] and GH not in out["body"]
    assert out["api_key"] == MASK and out["nested"]["password"] == MASK
    assert out["headers"][0]["value"] == MASK and ANT not in out["nested"]["note"]
    assert out["ok"] is True and out["none"] is None
    assert args["api_key"] == "plain-value-123"  # a copy; the input is untouched


def test_full_scrub_is_unchanged_and_credential_keys() -> None:
    assert PHONE not in scrub(f"call {PHONE}") and "@" not in scrub("a@example.com")
    assert scrub(f"call {PHONE}", secrets_only=True) == f"call {PHONE}"
    assert ANT not in scrub(ANT, secrets_only=True)
    assert is_credential_key("clientSecret") and is_credential_key("access_token")
    assert not is_credential_key("email") and not is_credential_key("mobile_number")
    assert not is_credential_key("recipient")
