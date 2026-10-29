"""Signing a bot's requests with its API key.

The exchange checks three headers on every bot request (docs: Authentication):

* ``OMNIBOOK-ACCESS-KEY``: the key ID the web app showed when the key was registered.
* ``OMNIBOOK-TIMESTAMP``: Unix milliseconds, as text.
* ``OMNIBOOK-ACCESS-SIGNATURE``: standard base64 of a signature over
  ``timestamp + METHOD + path``, where ``path`` starts at ``/trade-api/v2`` and stops
  before ``?``. The body is not signed.

Ed25519 and RSA-PSS (SHA-256, MGF1 SHA-256, salt length 32) keys are both accepted.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

KEY_HEADER = "OMNIBOOK-ACCESS-KEY"
TIMESTAMP_HEADER = "OMNIBOOK-TIMESTAMP"
SIGNATURE_HEADER = "OMNIBOOK-ACCESS-SIGNATURE"

_RSA_PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)


def signing_text(timestamp_ms: int | str, method: str, path: str) -> str:
    """The exact text a request's signature covers: ``timestamp + METHOD + path``.

    ``path`` may be a full URL or carry a query string; only the path is kept.
    """
    only_path = urlsplit(path).path if "://" in path else path.split("?", 1)[0]
    return f"{timestamp_ms}{method.upper()}{only_path}"


class Signer:
    """Signs requests with one API key: its ID and its private half.

    Build one with :meth:`from_pem`, :meth:`from_file` or :meth:`from_env`. The private key
    is the ``.pem`` file the web app saved when you created the key (PKCS#8,
    ``-----BEGIN PRIVATE KEY-----``).
    """

    def __init__(self, key_id: str, private_key: ed25519.Ed25519PrivateKey | rsa.RSAPrivateKey):
        if not key_id or not str(key_id).strip():
            raise ValueError("key_id is empty: use the key ID the web app showed for this key")
        if not isinstance(private_key, (ed25519.Ed25519PrivateKey, rsa.RSAPrivateKey)):
            raise TypeError("the private key must be Ed25519 or RSA")
        self.key_id = str(key_id).strip()
        self._key = private_key

    @property
    def algorithm(self) -> str:
        return "ed25519" if isinstance(self._key, ed25519.Ed25519PrivateKey) else "rsa-pss-sha256"

    @classmethod
    def from_pem(cls, key_id: str, pem: str | bytes, password: bytes | None = None) -> Signer:
        data = pem.encode() if isinstance(pem, str) else pem
        key = serialization.load_pem_private_key(data, password=password)
        return cls(key_id, key)  # type: ignore[arg-type]

    @classmethod
    def from_file(cls, key_id: str, path: str | os.PathLike[str], password: bytes | None = None) -> Signer:
        return cls.from_pem(key_id, Path(path).expanduser().read_bytes(), password)

    @classmethod
    def from_env(cls) -> Signer:
        """Read ``OMNIBOOK_API_KEY_ID`` and one of ``OMNIBOOK_PRIVATE_KEY_PATH`` or
        ``OMNIBOOK_PRIVATE_KEY`` (the PEM text itself)."""
        key_id = os.environ.get("OMNIBOOK_API_KEY_ID", "")
        if not key_id:
            raise ValueError("OMNIBOOK_API_KEY_ID is not set")
        if path := os.environ.get("OMNIBOOK_PRIVATE_KEY_PATH"):
            return cls.from_file(key_id, path)
        if pem := os.environ.get("OMNIBOOK_PRIVATE_KEY"):
            return cls.from_pem(key_id, pem.replace("\\n", "\n"))
        raise ValueError("set OMNIBOOK_PRIVATE_KEY_PATH or OMNIBOOK_PRIVATE_KEY")

    def sign(self, text: str) -> str:
        """Base64 signature over ``text``."""
        data = text.encode()
        if isinstance(self._key, ed25519.Ed25519PrivateKey):
            raw = self._key.sign(data)
        else:
            raw = self._key.sign(data, _RSA_PSS, hashes.SHA256())
        return base64.b64encode(raw).decode()

    def headers(self, method: str, path: str, timestamp_ms: int | None = None) -> dict[str, str]:
        """The three headers for one request."""
        ts = str(int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms))
        return {
            KEY_HEADER: self.key_id,
            TIMESTAMP_HEADER: ts,
            SIGNATURE_HEADER: self.sign(signing_text(ts, method, path)),
        }

    def public_key_pem(self) -> str:
        """The public half, as the PEM the web app registers."""
        return (
            self._key.public_key()
            .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            .decode()
        )

    def __repr__(self) -> str:
        return f"Signer(key_id={self.key_id!r}, algorithm={self.algorithm!r})"


def generate_key_pem() -> tuple[str, str]:
    """A new Ed25519 key pair as ``(private_pem, public_pem)``.

    Register the public PEM in the web app (Settings, API keys) to get a key ID. Keep the
    private PEM secret; the exchange never sees it.
    """
    key = ed25519.Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem
