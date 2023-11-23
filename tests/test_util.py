import pytest
from dnschef import __version__
from dnschef.utils import header

@pytest.mark.asyncio
async def test_config_parse(config_file):
    assert len(config_file)

@pytest.mark.asyncio
async def test_header():
    assert __version__ in header
