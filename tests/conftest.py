import pytest
import pytest_asyncio
import logging
import asyncio
import contextlib
import random
import string
import dns.asyncresolver

from dnschef import kitchen
from dnschef.api import app
from dnschef.protocols import start_server
from dnschef.utils import parse_config_file
from dnschef.logger import log, json_capture_formatter #,debug_formatter
from fastapi.testclient import TestClient

#log.setLevel(logging.DEBUG)
#log.handlers[0].setFormatter(debug_formatter)

jh = logging.StreamHandler()
jh.setFormatter(json_capture_formatter)
log.addHandler(jh)

@pytest.fixture
def random_string():
    return ''.join(random.choices(string.ascii_letters, k=6))

@pytest.fixture
def api_test_client():
    return TestClient(app)

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="session")
async def dns_client():
    resolver = dns.asyncresolver.Resolver()
    resolver.nameservers = ['127.0.0.1']
    resolver.port = 5553
    yield resolver

@pytest.fixture(scope="session")
def config_file():
    return parse_config_file("tests/dnschef-tests.toml")

@pytest_asyncio.fixture(scope="session", autouse=True)
async def start_dnschef(config_file):
    kitchen.CONFIG = config_file

    server_task = asyncio.create_task(
        start_server(
            interface="127.0.0.1",
            nameservers=["8.8.8.8"],
            tcp=True,
            ipv6=False,
            port=5553
    ))

    yield

    server_task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await server_task
