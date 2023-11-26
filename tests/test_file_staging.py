import pytest
import hashlib
from base64 import b64decode
from ipaddress import IPv4Address, IPv6Address


def compare_file_digests(tmp_file_path, orig_file_path):
    with tmp_file_path.open('rb') as staged_file:
        with open(orig_file_path, 'rb') as orig_file:
            staged_file_digest = hashlib.file_digest(staged_file, "md5").digest()
            orig_file_digest = hashlib.file_digest(orig_file, "md5").digest()

            return staged_file_digest == orig_file_digest

@pytest.mark.asyncio
async def test_A_file_staging(dns_client, tmp_path, random_string_gen):
    orig_file_path = "tests/small-bin-test"
    for proto in [False, True]:
        chunk_n  = 0
        tmp_file_path = tmp_path / next(random_string_gen)
        with tmp_file_path.open('ab') as f:
            while True:
                answers = await dns_client.resolve(f"lala{chunk_n}dayum.wat.org", "A", tcp=proto, raise_on_no_answer=False)
                print(list(answers))
                for answer in answers:
                    data = IPv4Address(answer.address).packed
                    data = data.replace(b'\x00', b'')
                    f.write(data)

                if not len(answers):
                    break

                chunk_n += 1

        assert compare_file_digests(tmp_file_path, orig_file_path) == True

@pytest.mark.asyncio
async def test_AAAA_file_staging(dns_client, tmp_path, random_string_gen):
    orig_file_path = "tests/small-bin-test"
    for proto in [False, True]:
        chunk_n  = 0
        tmp_file_path = tmp_path / next(random_string_gen)
        with tmp_file_path.open('ab') as f:
            while True:
                answers = await dns_client.resolve(f"lala{chunk_n}dayum.wat.org", "AAAA", tcp=proto, raise_on_no_answer=False)
                for answer in answers:
                    data = IPv6Address(answer.address).packed
                    data = data.replace(b'\x00', b'')
                    f.write(data)

                if not len(answers):
                    break

                chunk_n += 1

        assert compare_file_digests(tmp_file_path, orig_file_path) == True

@pytest.mark.asyncio
async def test_TXT_file_staging(dns_client, tmp_path, random_string_gen):
    orig_file_path = "tests/thicc-bin-test"
    for proto in [False, True]:
        chunk_n  = 0
        tmp_file_path = tmp_path / next(random_string_gen)
        with tmp_file_path.open('ab') as f:
            while True:
                answers = await dns_client.resolve(f"ns{chunk_n}.fronted.brick.org", "TXT", tcp=proto, raise_on_no_answer=False)
                for answer in answers:
                    f.write(b64decode(answer.to_text().strip('"')))

                if not len(answers):
                    break

                chunk_n += 1

        assert compare_file_digests(tmp_file_path, orig_file_path) == True
