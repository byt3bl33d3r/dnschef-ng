import asyncio
import socket
import re
import random
import functools
from typing import List
from dnschef.logger import log

from dnschef import kitchen

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
async def proxy_request(request, host, port=53, protocol="udp"):
    loop = asyncio.get_running_loop()
    on_con_lost = loop.create_future()

    if protocol == "udp":
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
        self.nameservers = nameservers
        self.dns_kitchen = dns_kitchen

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        logger = log.bind(address=addr[0], proto="udp")

        def _cooked_cb(future):
            response = future.result()
            if response:
                logger.debug("dns packet", packet=response.pack())
                self.transport.sendto(response.pack(), addr)
            else:
                logger.info("proxying response")
                nameserver_tuple = re.split('[:#]', random.choice(self.nameservers))

                task = asyncio.create_task(proxy_request(data, *nameserver_tuple, protocol='udp'))
                task.add_done_callback(functools.partial(lambda c, t, a: t.sendto(c.result(), a), t=self.transport, a=addr))

        task = asyncio.create_task(self.dns_kitchen.we_cookin(logger, data, addr))
        task.add_done_callback(_cooked_cb)

class TcpDnsServerProtocol(asyncio.Protocol):
    def __init__(self, nameservers, dns_kitchen):
        self.nameservers = nameservers
        self.dns_kitchen = dns_kitchen

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        addr = self.transport.get_extra_info('peername')
        logger = log.bind(address=addr[0], proto="tcp")

        def _cooked_cb(future):
            response = future.result()
            if response:
                logger.debug("dns packet", packet=response.pack())
                self.transport.write(
                    len(response.pack()).to_bytes(2, byteorder='big') + response.pack()
                )
            else:
                logger.info("proxying response")
                nameserver_tuple = re.split('[:#]', random.choice(self.nameservers))

                task = asyncio.create_task(proxy_request(data, *nameserver_tuple, protocol='tcp'))
                task.add_done_callback(functools.partial(lambda c, t: t.write(c.result()), t=self.transport))

        task = asyncio.create_task(self.dns_kitchen.we_cookin(logger, data[2:], addr))
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
