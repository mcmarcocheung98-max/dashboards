import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "network: fetches the live sources (run by hand: pytest -m network tests/test_sources.py)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("-m", default="") == "":
        skip = pytest.mark.skip(reason="network test: run with -m network")
        for it in items:
            if "network" in it.keywords:
                it.add_marker(skip)
