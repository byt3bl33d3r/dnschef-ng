import pytest
import difflib
from dnslib import RDMAP

@pytest.mark.asyncio
async def test_proxy_request(dns_client):
    for proto in [False, True]:
        await dns_client.resolve("google.com", "A", tcp=proto)

@pytest.mark.asyncio
async def test_fake_A_response(dns_client):
    for proto in [False, True]:
        answers = await dns_client.resolve("fuck.shit.com", "A", tcp=proto)
        assert answers[0].address == "192.168.0.1"

@pytest.mark.asyncio
async def test_correct_wildcard_behavior(dns_client):
    for proto in [False, True]:
        answers = await dns_client.resolve("thesprawl.org", "A", tcp=proto, raise_on_no_answer = False)
        assert not len(answers)

        answers = await dns_client.resolve("test.thesprawl.org", "A", tcp=proto)
        assert answers[0].address == "100.100.100.100"

        answers = await dns_client.resolve("err.thesprawl.org", "A", tcp=proto)
        assert answers[0].address == "100.100.100.100"

        answers = await dns_client.resolve("ok.test.thesprawl.org", "A", tcp=proto)
        assert answers[0].address == "127.0.0.1"

        answers = await dns_client.resolve("not.bad.thesprawl.org", "A", tcp=proto)
        assert answers[0].address == "1.1.1.1"

        answers = await dns_client.resolve("c.bad.wat.thesprawl.org", "A", tcp=proto)
        assert answers[0].address == "1.1.2.2"

        answers = await dns_client.resolve("wa1.aint.nothing.org", "TXT", tcp=proto)
        assert answers[0].to_text().strip('"') == 'sequoia banshee buggers'

        answers = await dns_client.resolve("wattahog.aint.nothing.org", "TXT", tcp=proto)
        assert answers[0].to_text().strip('"') == 'sequoia banshee buggers'


@pytest.mark.asyncio
async def test_fake_wildcard_records(dns_client, random_string, config_file):
    for proto in [False, True]:
        for record in RDMAP.keys():
            if record == "RRSIG" or record not in config_file:
                continue

            answers = await dns_client.resolve(
                f"{random_string}.thesprawl.org",
                record,
                tcp=proto
            )

            #assert answers[0].to_text().replace('"', '').rstrip('.') == config_file[record]["*.thesprawl.org"]

            assert difflib.SequenceMatcher(
                a=answers[0].to_text(),
                b=config_file[record]["*.thesprawl.org"]
            ).quick_ratio() > 0.86
