import warnings

import pytest

import omnibook
from omnibook import MAINNET, SANDBOX, AsyncClient, Client, Environment
from omnibook.environments import _DEMO, ENVIRONMENTS, resolve


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
    with pytest.warns(DeprecationWarning):
        assert resolve("demo") is _DEMO
    assert set(ENVIRONMENTS) == {"mainnet", "sandbox", "demo"}


def test_unknown_environment_names_the_sandbox():
    with pytest.raises(ValueError, match="sandbox") as err:
        resolve("testnet")
    assert "demo" not in str(err.value)


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


# The demo hosts are retired: DEMO still works, with a DeprecationWarning that points at the caller.


def test_importing_omnibook_does_not_warn():
    import importlib

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        importlib.reload(omnibook)
        from omnibook import SANDBOX as again  # noqa: F401


def _one_warning(record):
    # ``from omnibook import DEMO`` reads the attribute twice (CPython's fromlist check on a package),
    # so it may record twice; both are at the same line, and the default filter shows it once.
    assert len(record) >= 1
    assert len({(w.filename, w.lineno) for w in record}) == 1
    for w in record:
        assert issubclass(w.category, DeprecationWarning)
        assert "retired" in str(w.message) and "sandbox" in str(w.message)
        assert w.filename == __file__, w.filename  # the caller's line, not the SDK's


def test_omnibook_demo_warns():
    with pytest.warns(DeprecationWarning) as record:
        env = omnibook.DEMO
    assert env is _DEMO and env.rest_url == "https://demo-api.omnibook.xyz"
    _one_warning(record)


def test_from_import_demo_warns():
    with pytest.warns(DeprecationWarning) as record:
        from omnibook import DEMO
    assert DEMO is _DEMO
    _one_warning(record)


def test_environments_demo_warns():
    from omnibook import environments

    with pytest.warns(DeprecationWarning) as record:
        assert environments.DEMO is _DEMO
    _one_warning(record)


@pytest.mark.parametrize("name", ["demo", "DEMO"])
def test_resolve_demo_warns(name):
    with pytest.warns(DeprecationWarning) as record:
        assert resolve(name) is _DEMO
    _one_warning(record)


@pytest.mark.parametrize("environment", ["demo", _DEMO])
def test_client_on_demo_warns_at_the_callers_line(environment):
    with pytest.warns(DeprecationWarning) as record:
        client = Client(environment=environment)
    client.close()
    assert client.base_url == "https://demo-api.omnibook.xyz"
    _one_warning(record)


async def test_async_client_on_demo_warns():
    with pytest.warns(DeprecationWarning) as record:
        client = AsyncClient(environment="demo")
    await client.aclose()
    _one_warning(record)


@pytest.mark.parametrize("environment", [None, "mainnet", "sandbox", SANDBOX])
def test_other_environments_do_not_warn(environment):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Client(environment=environment).close()
        resolve(environment)


def test_a_custom_environment_named_demo_does_not_warn():
    mine = Environment(name="demo", rest_url="http://127.0.0.1:8080", ws_url="ws://x", ws_auth_url="ws://y")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert resolve(mine) is mine


def test_unknown_attribute_still_raises():
    with pytest.raises(AttributeError):
        omnibook.NOPE  # noqa: B018


def test_star_import_does_not_warn_or_export_demo():
    assert "DEMO" not in omnibook.__all__
    namespace = {}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        exec("from omnibook import *", namespace)
    assert "SANDBOX" in namespace and "DEMO" not in namespace
