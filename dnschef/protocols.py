import asyncio
import socket
import re
import random
import functools
import enum
from dnslib import DNSRecord, QR, QTYPE
from typing import List
from dnschef.logger import log

from dnschef import kitchen

class ClientProtocol(enum.Enum):
    UDP = 1
    TCP = 2

class UdpDnsClientProtocol:
    def __init__(self, request, on_con_lost):
        self.transport = None
        self.request = request
        self.on_con_lost = on_con_lost

    def connection_made(self, transport):
        self.transport = transport
        log.debug('sending', request=self.request)
        self.transport.sendto(self.request)

    def datagram_received(self, data, addr):
        log.debug("received", addr=addr, data=data)
        self.reply = data
        self.transport.close()

    def error_received(self, exc):
        log.exception('error received')

    def connection_lost(self, exc):
        log.debug("connection closed")
        self.on_con_lost.set_result(True)

class TcpDnsClientProtocol(asyncio.Protocol):
    def __init__(self, request, on_con_lost):
        self.request = request
        self.on_con_lost = on_con_lost

    def connection_made(self, transport):
        self.transport = transport
        log.debug('sending', request=self.request)
        self.transport.write(self.request)

    def data_received(self, data):
        addr = self.transport.get_extra_info('peername')
        log.debug("received", addr=addr, data=data)
        self.reply = data
        self.transport.close()

    def connection_lost(self, exc):
        log.debug("connection closed")
        # The socket has been closed
        self.on_con_lost.set_result(True)

# Obtain a response from a real DNS server.
async def proxy_request(request, host, protocol: ClientProtocol, port: int = 53):
    loop = asyncio.get_running_loop()
    on_con_lost = loop.create_future()

    if protocol == ClientProtocol.UDP:
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UdpDnsClientProtocol(request, on_con_lost),
            remote_addr=(host, int(port)))
    else:
        transport, protocol = await loop.create_connection(
            lambda: TcpDnsClientProtocol(request, on_con_lost),
            host=host,
            port=int(port)
        )

    try:
        await on_con_lost
    finally:
        transport.close()
        return protocol.reply

class UdpDnsServerProtocol:
    def __init__(self, nameservers, dns_kitchen):
        self.nameservers = [ re.split('[:#]', ns) for ns in nameservers ]
        self.dns_kitchen = dns_kitchen

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        logger = log.bind(address=addr[0], proto="udp")

        try:
            d = DNSRecord.parse(data)
        except Exception:
            logger.error("invalid DNS request")
        else:
            # Only Process DNS Queries
            if not QR[d.header.qr] == "QUERY":
                logger.warning("received a non-query DNS request")
                return

            qtype = QTYPE[d.q.qtype]
            qname = str(d.q.qname).rstrip('.')
            logger = logger.bind(name=qname, type=qtype)

            def _cooked_cb(future):
                response = future.result()
                if response:
                    logger.debug("dns packet", packet=response.pack())
                    self.transport.sendto(response.pack(), addr)
                else:
                    logger.info("proxying response")
                    task = asyncio.create_task(
                        proxy_request(
                            data, 
                            *random.choice(self.nameservers),
                            protocol=ClientProtocol.UDP
                        )
                    )
                    task.add_done_callback(functools.partial(
                        lambda c, t, a: t.sendto(c.result(), a), t=self.transport, a=addr
                    ))

            task = asyncio.create_task(self.dns_kitchen.we_cookin(logger, d, qtype, qname, addr))
            task.add_done_callback(_cooked_cb)

class TcpDnsServerProtocol(asyncio.Protocol):
    def __init__(self, nameservers, dns_kitchen):
        self.nameservers = [ re.split('[:#]', ns) for ns in nameservers ]
        self.dns_kitchen = dns_kitchen

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        addr = self.transport.get_extra_info('peername')
        logger = log.bind(address=addr[0], proto="tcp")

        try:
            d = DNSRecord.parse(data[2:])
        except Exception:
            logger.error("invalid DNS request")
        else:
            # Only Process DNS Queries
            if not QR[d.header.qr] == "QUERY":
                logger.warning("received a non-query DNS request")
                return

            qtype = QTYPE[d.q.qtype]
            qname = str(d.q.qname).rstrip('.')
            logger = logger.bind(name=qname, type=qtype)

            def _cooked_cb(future):
                response = future.result()
                if response:
                    logger.debug("dns packet", packet=response.pack())
                    self.transport.write(
                        len(response.pack()).to_bytes(2, byteorder='big') + response.pack()
                    )
                else:
                    logger.info("proxying response")
                    task = asyncio.create_task(
                        proxy_request(
                            data,
                            *random.choice(self.nameservers),
                            protocol=ClientProtocol.TCP
                        )
                    )
                    task.add_done_callback(functools.partial(
                        lambda c, t: t.write(c.result()), t=self.transport
                    ))

            task = asyncio.create_task(self.dns_kitchen.we_cookin(logger, d, qtype, qname, addr))
            task.add_done_callback(_cooked_cb)

async def start_server(interface: str, nameservers: List[str], tcp: bool = False, ipv6: bool = False, port: int = 53):
    loop = asyncio.get_running_loop()

    family= socket.AF_INET if not ipv6 else socket.AF_INET6
    if tcp:
        server = await loop.create_server(
            lambda: TcpDnsServerProtocol(nameservers, kitchen.DNSKitchen()),
            host=interface, 
            port=int(port),
            family=family
        )

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UdpDnsServerProtocol(nameservers, kitchen.DNSKitchen()),
        local_addr=(interface, int(port)),
        family=family
    )

    log.info("DNSChef is active", interface=interface, tcp=tcp, ipv6=ipv6, port=port, nameservers=nameservers)

    while True:
        await asyncio.sleep(1)
