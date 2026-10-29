import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from omnibook import Signer

# Keys made for these tests only. They are not registered anywhere.
ED25519_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
KEY_ID = "0b1c2d3e-test-key-0000-000000000000"


@pytest.fixture
def ed_key():
    return ed25519.Ed25519PrivateKey.from_private_bytes(ED25519_SEED)


@pytest.fixture
def signer(ed_key):
    return Signer(KEY_ID, ed_key)


@pytest.fixture(scope="session")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def pem_of(key):
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
