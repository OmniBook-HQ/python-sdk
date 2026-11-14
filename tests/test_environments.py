import pytest

import omnibook
from omnibook import DEMO, MAINNET, SANDBOX, AsyncClient, Client, Environment
from omnibook.environments import ENVIRONMENTS, resolve


def test_sandbox_hosts():
    assert SANDBOX.name == "sandbox"
    assert SANDBOX.rest_url == "https://test-api.omnibook.xyz"
    assert SANDBOX.ws_url == "wss://test-ws.omnibook.xyz/v1"
    assert SANDBOX.ws_auth_url == "wss://test-ws-auth.omnibook.xyz/v1"
    assert SANDBOX.api_base == "https://test-api.omnibook.xyz/trade-api/v2"


@pytest.mark.parametrize("name", ["sandbox", "SANDBOX", "Sandbox"])
def test_resolve_sandbox_by_name(name):
    assert resolve(name) is SANDBOX


def test_resolve_keeps_the_others():
    assert resolve(None) is MAINNET
    assert resolve("mainnet") is MAINNET
    assert resolve("demo") is DEMO
    assert set(ENVIRONMENTS) == {"mainnet", "sandbox", "demo"}


def test_unknown_environment_names_the_sandbox():
    with pytest.raises(ValueError, match="sandbox"):
        resolve("testnet")


def test_sandbox_is_exported():
    assert omnibook.SANDBOX is SANDBOX
    assert "SANDBOX" in omnibook.__all__


def test_the_2_0_recipe_equals_sandbox():
    # With 2.0.0, which has no SANDBOX, a trader builds the same Environment by hand.
    custom = Environment(
        name="sandbox",
        rest_url="https://test-api.omnibook.xyz",
        ws_url="wss://test-ws.omnibook.xyz/v1",
        ws_auth_url="wss://test-ws-auth.omnibook.xyz/v1",
    )
    assert custom == SANDBOX
    assert resolve(custom) is custom


@pytest.mark.parametrize("environment", ["sandbox", SANDBOX])
def test_client_on_the_sandbox(environment):
    with Client(environment=environment) as client:
        assert client.environment is SANDBOX
        assert client.base_url == "https://test-api.omnibook.xyz"


async def test_async_client_on_the_sandbox():
    async with AsyncClient(environment="sandbox") as client:
        assert client.environment is SANDBOX
        assert client.base_url == "https://test-api.omnibook.xyz"


def test_default_is_still_mainnet():
    with Client() as client:
        assert client.environment is MAINNET


def test_sandbox_feeds():
    with Client(environment="sandbox") as client:
        assert client._ws_args(private=False)["url"] == "wss://test-ws.omnibook.xyz/v1"
        assert client._ws_args(private=True)["url"] == "wss://test-ws-auth.omnibook.xyz/v1"
