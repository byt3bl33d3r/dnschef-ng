from dnschef.logger import log

from dnslib import *
from ipaddress import ip_address
from typing import List

import re
import socket
import asyncio
import functools
import random
import time
import operator

# Main storage of domain filters
# NOTE: RDMAP is a dictionary map of qtype strings to handling classes
nametodns = dict()
for qtype in list(RDMAP.keys()):
    nametodns[qtype] = dict()

class DNSKitchen:

    async def do_default(self, addr, record, qname, qtype):
        # dnslib doesn't like trailing dots
        if record[-1] == ".": record = record[:-1]
        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](record))

    async def do_AAAA(self, addr, record, qname, qtype):
        ipv6_hex_tuple = list(map(int, ip_address(record).packed))
        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](ipv6_hex_tuple))

    async def do_HTTPS(self, addr, record, qname, qtype):
        kv_pairs = record.split(" ")
        mydata = RDMAP[qtype].fromZone(kv_pairs)
        return RR(qname, getattr(QTYPE, qtype), rdata=mydata)

    async def do_SOA(self, addr, record, qname, qtype):
        mname, rname, t1, t2, t3, t4, t5 = record.split(" ")
        times = tuple([int(t) for t in [t1, t2, t3, t4, t5]])

        # dnslib doesn't like trailing dots
        if mname[-1] == ".": mname = mname[:-1]
        if rname[-1] == ".": rname = rname[:-1]

        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](mname, rname, times))

    async def do_NAPTR(self, addr, record, qname, qtype):
        order, preference, flags, service, regexp, replacement = list(map(lambda x: x.encode(), record.split(" ")))
        order = int(order)
        preference = int(preference)

        # dnslib doesn't like trailing dots
        if replacement[-1] == ".": replacement = replacement[:-1]

        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](order, preference, flags, service, regexp, DNSLabel(replacement)))

    async def do_SRV(self, addr, record, qname, qtype):
        priority, weight, port, target = record.split(" ")
        priority = int(priority)
        weight = int(weight)
        port = int(port)
        if target[-1] == ".": target = target[:-1]

        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](priority, weight, port, target))

    async def do_DNSKEY(self, addr, record, qname, qtype):
        flags, protocol, algorithm, key = record.split(" ")
        flags = int(flags)
        protocol = int(protocol)
        algorithm = int(algorithm)
        key = base64.b64decode(("".join(key)).encode('ascii'))

        return RR(qname, getattr(QTYPE, qtype), rdata=RDMAP[qtype](flags, protocol, algorithm, key))

    async def do_RRSIG(self, addr, record, qname, qtype):
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

                # Gather query parameters
                # NOTE: Do not lowercase qname here, because we want to see
                #       any case request weirdness in the logs.
                qname = str(d.q.qname)

                # Chop off the last period
                if qname[-1] == '.': qname = qname[:-1]

                qtype = QTYPE[d.q.qtype]

                # Find all matching fake DNS records for the query name or get False
                fake_records = dict()

                for record in nametodns:
                    fake_records[record] = findnametodns(qname, nametodns[record])

                # Create a custom response to the query
                response = DNSRecord(DNSHeader(id=d.header.id, bitmap=d.header.bitmap, qr=1, aa=1, ra=1), q=d.q)

                # Check if there is a fake record for the current request qtype
                if qtype in fake_records and fake_records[qtype]:

                    fake_record = fake_records[qtype]
                    logger.info(f"cooking response", type=qtype, name=qname, record=fake_record)

                    response_func = getattr(self.dnsresponses, f"do_{qtype}", "do_default")

                    task = asyncio.create_task(response_func(addr, fake_record, qname, qtype))
                    task.add_done_callback(functools.partial(self.send_response, response=response, addr=addr))

                elif (qtype == "*" or qtype == "ANY") and None not in list(fake_records.values()):
                    logger.info("cooking response with all known fake records", type='ANY', name=qname)

                    for qtype, fake_record in list(fake_records.items()):
                        if fake_record:
                            response_func = getattr(self.dnsresponses, f"do_{qtype}", "do_default")
                            response.add_answer(response_func(addr, fake_record, qname, qtype))

                    self.transport.sendto(response.pack(), addr)

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
def findnametodns(qname, nametodns):

    # Make qname case insensitive
    qname = qname.lower()

    # Split and reverse qname into components for matching.
    qnamelist = qname.split('.')
    qnamelist.reverse()

    # HACK: It is important to search the nametodns dictionary before iterating it so that
    # global matching ['*.*.*.*.*.*.*.*.*.*'] will match last. Use sorting for that.
    for domain, host in sorted(iter(nametodns.items()), key=operator.itemgetter(1)):

        # NOTE: It is assumed that domain name was already lowercased
        #       when it was loaded through --file, --fakedomains or --truedomains
        #       don't want to waste time lowercasing domains on every request.

        # Split and reverse domain into components for matching
        domain = domain.split('.')
        domain.reverse()

        # Compare domains in reverse.
        for a, b in zip(qnamelist, domain):
            if a != b and b != "*":
                break
        else:
            # Could be a real IP or False if we are doing reverse matching with 'truedomains'
            return host
    else:
        return False
