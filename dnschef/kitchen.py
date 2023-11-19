from dnslib import *
from ipaddress import IPv4Address, IPv6Address
from typing import List

from dnschef.logger import log

import difflib
import fnmatch
import base64
import io
import re
import itertools
import pathlib
import socket
import asyncio
import functools
import random
import time

CONFIG = dict()

def chunk_string(string_to_chunk: str, chunk_size: int):
    data = io.StringIO(string_to_chunk)
    while True:
        piece = data.read(chunk_size)
        if not piece:
            break
        yield piece

def chunk_file(file_path: pathlib.Path, chunk_size: int):
    with file_path.open('rb') as f:
        while True:
            piece = f.read(chunk_size)
            if not piece:
                break
            yield piece


def get_file_chunk(file_path, chunk_index, chunk_size):
    return next(itertools.islice(
        chunk_file(file_path, chunk_size),
        chunk_index,
        chunk_index+1
    ), b'')


async def stage_file(qname, record, chunk_size: int):
    loop = asyncio.get_event_loop()

    file_to_stage = pathlib.Path(record['file'])
    if file_to_stage.exists() and file_to_stage.is_file():
        chunk_index = int(''.join([ c for c in qname.split('.')[0] if c.isdigit() ]))

        file_chunk = await loop.run_in_executor(None, get_file_chunk, file_to_stage, chunk_index, chunk_size)
        return file_chunk


class DNSKitchen:

    async def do_default(self, addr, qname, qtype, record):
        if record[-1] == ".": record = record[:-1]
        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](record))

    async def do_A(self, addr, qname, qtype, record):
        if isinstance(record, dict):
            chunk_size = record.get('chunk_size', 4)
            if chunk_size > 4:
                log.warning(f"chunk_size {chunk_size} is too large for A record, defaulting to 4")
                chunk_size = 4

            file_chunk = await stage_file(qname, record, chunk_size)
            if file_chunk:
                record = file_chunk

        ipv4_hex_tuple = list(map(int, IPv4Address(record).packed))
        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](ipv4_hex_tuple))

    async def do_TXT(self, addr, qname, qtype, record):
        if isinstance(record, dict):
            prefix = random.choice(record.get('response_prefix_pool'))
            response_format = record.get('response_format')

            space_left = 255 - len(response_format.format(prefix=prefix, chunk=''))
            max_data_len = ( space_left // 4 ) * 3

            file_chunk = await stage_file(qname, record, chunk_size=max_data_len)
            if file_chunk:
                record = response_format.format(prefix=prefix, chunk=base64.b64encode(file_chunk).decode())

        # dnslib doesn't like trailing dots
        if record[-1] == ".": record = record[:-1]
        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](record))

    async def do_AAAA(self, addr, qname, qtype, record):
        if isinstance(record, dict):
            chunk_size = record.get('chunk_size', 16)
            if chunk_size > 16:
                log.warning(f"chunk_size {chunk_size} is too large for AAAA record, defaulting to 16")
                chunk_size = 16

            file_chunk = await stage_file(qname, record, chunk_size)
            if file_chunk:
                record = file_chunk

        ipv6_hex_tuple = list(map(int, IPv6Address(record).packed))
        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](ipv6_hex_tuple))

    async def do_HTTPS(self, addr, qname, qtype, record):
        kv_pairs = record.split(" ")
        mydata = RDMAP[qtype].fromZone(kv_pairs)
        return RR(qname, getattr(QTYPE, qtype), rdata=mydata)

    async def do_SOA(self, addr, qname, qtype, record):
        mname, rname, t1, t2, t3, t4, t5 = record.split(" ")
        times = tuple([int(t) for t in [t1, t2, t3, t4, t5]])

        # dnslib doesn't like trailing dots
        if mname[-1] == ".": mname = mname[:-1]
        if rname[-1] == ".": rname = rname[:-1]

        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](mname, rname, times))

    async def do_NAPTR(self, addr, qname, qtype, record):
        order, preference, flags, service, regexp, replacement = list(map(lambda x: x.encode(), record.split(" ")))
        order = int(order)
        preference = int(preference)

        # dnslib doesn't like trailing dots
        if replacement[-1] == ".": replacement = replacement[:-1]

        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](order, preference, flags, service, regexp, DNSLabel(replacement)))

    async def do_SRV(self, addr, qname, qtype, record):
        priority, weight, port, target = record.split(" ")
        priority = int(priority)
        weight = int(weight)
        port = int(port)
        if target[-1] == ".": target = target[:-1]

        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](priority, weight, port, target))

    async def do_DNSKEY(self, addr, qname, qtype, record):
        flags, protocol, algorithm, key = record.split(" ")
        flags = int(flags)
        protocol = int(protocol)
        algorithm = int(algorithm)
        key = base64.b64decode(("".join(key)).encode('ascii'))

        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](flags, protocol, algorithm, key))

    async def do_RRSIG(self, addr, qname, qtype, record):
        covered, algorithm, labels, orig_ttl, sig_exp, sig_inc, key_tag, name, sig = record.split(" ")

        covered = getattr(QTYPE, covered)  # NOTE: Covered QTYPE
        algorithm = int(algorithm)
        labels = int(labels)
        orig_ttl = int(orig_ttl)
        sig_exp = int(time.mktime(time.strptime(sig_exp + 'GMT', "%Y%m%d%H%M%S%Z")))
        sig_inc = int(time.mktime(time.strptime(sig_inc + 'GMT', "%Y%m%d%H%M%S%Z")))
        key_tag = int(key_tag)
        if name[-1] == '.': name = name[:-1]
        sig = base64.b64decode(("".join(sig)).encode('ascii'))

        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](covered, algorithm, labels, orig_ttl, sig_exp, sig_inc, key_tag, name, sig))

class DNSProxyProtocol:
    def __init__(self, request, loop):
        self.transport = None
        self.request = request
        self.on_con_lost = loop.create_future()

    def connection_made(self, transport):
        self.transport = transport
        log.debug('sending', request=self.request)
        self.transport.sendto(self.request)

    def datagram_received(self, data, addr):
        log.debug("received", data=data)
        self.reply = data
        self.transport.close()

    def error_received(self, exc):
        log.exception('error received')

    def connection_lost(self, exc):
        log.debug("connection closed")
        self.on_con_lost.set_result(True)


class DNSServerProtocol:
    def __init__(self, nameservers, dnsresponses=DNSKitchen()):
        self.nameservers = nameservers
        self.dnsresponses = dnsresponses

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data, addr):
        pass
        #self.datagram_received(data, addr)

    def send_response(self, coro, response, addr):
        response.add_answer(coro.result())
        self.transport.sendto(response.pack(), addr)

    def datagram_received(self, data, addr):
        logger = log.bind(address=addr[0])
        try:
            d = DNSRecord.parse(data)
        except Exception:
            logger.error("invalid DNS request")

        else:
            # Only Process DNS Queries
            if QR[d.header.qr] == "QUERY":

                qtype = QTYPE[d.q.qtype]
                # Create a custom response to the query
                response = DNSRecord(
                    DNSHeader(id=d.header.id, bitmap=d.header.bitmap, qr=1, aa=1, ra=1), 
                    q=d.q
                )

                # Gather query parameters
                # NOTE: Do not lowercase qname here, because we want to see
                #       any case request weirdness in the logs.
                qname = str(d.q.qname)

                # Chop off the last period
                if qname[-1] == '.': qname = qname[:-1]

                cooked_reply = findnametodns(qname, qtype)

                # Check if there is a fake record for the current request qtype
                if CONFIG.get(qtype) and cooked_reply:
                    logger.info("cooking response", type=qtype, name=qname) #record=record)

                    response_func = getattr(
                        self.dnsresponses,
                        f"do_{qtype}",
                        self.dnsresponses.do_default
                    )

                    task = asyncio.create_task(response_func(addr, qname, qtype, cooked_reply))
                    task.add_done_callback(functools.partial(self.send_response, response=response, addr=addr))

                else:
                    logger.info(f"proxying response", type=qtype, name=qname)
                    nameserver_tuple = re.split('[:#]', random.choice(self.nameservers))

                    task = asyncio.create_task(proxyrequest(data, *nameserver_tuple))
                    task.add_done_callback(functools.partial(lambda c, t, a: t.sendto(c.result(), a), t=self.transport, a=addr))


async def start_cooking(interface: str, nameservers: List[str], tcp: bool = False, ipv6: bool = False, port: int = 53):
    loop = asyncio.get_running_loop()

    family= socket.AF_INET if not ipv6 else socket.AF_INET6
    if tcp:
        server = await loop.create_server(
            lambda: DNSServerProtocol(nameservers),
            host=interface, 
            port=int(port),
            family=family
        )
    else:
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: DNSServerProtocol(nameservers),
            local_addr=(interface, int(port)),
            family=family
        )

    log.info("DNSChef is active", interface=interface, tcp=tcp, ipv6=ipv6, port=port, nameservers=nameservers)

    while True:
        await asyncio.sleep(1)


# Obtain a response from a real DNS server.
async def proxyrequest(request, host, port="53", protocol="udp"):
    loop = asyncio.get_running_loop()

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: DNSProxyProtocol(request, loop),
        remote_addr=(host, int(port)))

    try:
        await protocol.on_con_lost
    finally:
        transport.close()
        return protocol.reply

# Find appropriate ip address to use for a queried name.
def findnametodns(qname, qtype):
    # Make qname case insensitive
    qname = qname.lower()

    matched_domains = [
        k for k,_ in CONFIG[qtype].items() 
        if qname.count('.') == k.count('.') and fnmatch.fnmatch(qname, k)
    ]

    if matched_domains:
        top_matched_domains = list(sorted(
            matched_domains,
            key=lambda domain: difflib.SequenceMatcher(a=domain, b=qname).quick_ratio(),
            reverse=True
        ))

        #return { qtype: { k:v for k,v in CONFIG[qtype].items() if k == top_matched_domains[0] } }
        return CONFIG[qtype][top_matched_domains[0]]
