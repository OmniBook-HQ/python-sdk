import base64

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from omnibook import Signer, generate_key_pem, signing_text
from omnibook._base import num

from .conftest import KEY_ID, pem_of


def test_signing_text_is_timestamp_method_path():
    assert signing_text(1759400000000, "post", "/trade-api/v2/portfolio/events/orders") == (
        "1759400000000POST/trade-api/v2/portfolio/events/orders"
    )


def test_signing_text_stops_before_the_query():
    assert signing_text("1", "GET", "/trade-api/v2/portfolio/orders?status=resting&limit=10") == (
        "1GET/trade-api/v2/portfolio/orders"
    )
    assert signing_text("1", "GET", "https://trade-api.omnibook.xyz/trade-api/v2/markets?x=1") == (
        "1GET/trade-api/v2/markets"
    )


def test_ed25519_headers_verify(signer, ed_key):
    headers = signer.headers("DELETE", "/trade-api/v2/portfolio/events/orders/7781", timestamp_ms=1790843825000)
    assert headers["OMNIBOOK-ACCESS-KEY"] == KEY_ID
    assert headers["OMNIBOOK-TIMESTAMP"] == "1790843825000"
    raw = base64.b64decode(headers["OMNIBOOK-ACCESS-SIGNATURE"], validate=True)
    ed_key.public_key().verify(raw, b"1790843825000DELETE/trade-api/v2/portfolio/events/orders/7781")


def test_ed25519_is_deterministic(signer, ed_key):
    text = "1790843825000GET/trade-api/v2/portfolio/balance"
    assert signer.sign(text) == base64.b64encode(ed_key.sign(text.encode())).decode()


def test_rsa_pss_salt_32_verifies(rsa_key):
    signer = Signer.from_pem("k", pem_of(rsa_key))
    assert signer.algorithm == "rsa-pss-sha256"
    text = "1790843825000POST/trade-api/v2/portfolio/events/orders"
    raw = base64.b64decode(signer.sign(text))
    rsa_key.public_key().verify(
        raw, text.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256()
    )


def test_from_file_and_env(tmp_path, ed_key, monkeypatch):
    path = tmp_path / "key.pem"
    path.write_text(pem_of(ed_key))
    assert Signer.from_file(KEY_ID, path).public_key_pem() == Signer(KEY_ID, ed_key).public_key_pem()
    monkeypatch.setenv("OMNIBOOK_API_KEY_ID", KEY_ID)
    monkeypatch.setenv("OMNIBOOK_PRIVATE_KEY_PATH", str(path))
    assert Signer.from_env().key_id == KEY_ID
    monkeypatch.delenv("OMNIBOOK_PRIVATE_KEY_PATH")
    monkeypatch.setenv("OMNIBOOK_PRIVATE_KEY", pem_of(ed_key).replace("\n", "\\n"))
    assert Signer.from_env().algorithm == "ed25519"


def test_generated_pair_round_trips():
    private_pem, public_pem = generate_key_pem()
    assert Signer.from_pem("k", private_pem).public_key_pem() == public_pem


def test_empty_key_id_is_refused(ed_key):
    with pytest.raises(ValueError):
        Signer("  ", ed_key)


def test_numbers_are_text_and_floats_are_refused():
    from decimal import Decimal

    assert num("0.4500", "price") == "0.4500"
    assert num(10, "count") == "10"
    assert num(Decimal("0.5625"), "price") == "0.5625"
    with pytest.raises(TypeError):
        num(0.45, "price")
    with pytest.raises(ValueError):
        num("abc", "price")
    with pytest.raises(ValueError):
        num("NaN", "price")
