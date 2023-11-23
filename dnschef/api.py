from dnschef import __version__
from dnschef import kitchen
from dnschef.protocols import start_server
from dnschef.utils import header, parse_config_file
from dnschef.logger import (
    log,
    plain_formatter,
    json_capture_formatter,
    capturer
)

from enum import Enum
from typing import Optional, List

from fastapi import FastAPI
from pydantic_settings import BaseSettings
from pydantic import BaseModel, FilePath #,IPvAnyAddress
from dnslib import RDMAP

import logging
import logging.handlers
import asyncio

DnsQueryType = Enum("DnsQueryType", {r:r for r in RDMAP.keys()})

class Record(BaseModel):
    type: DnsQueryType
    domain: str
    value: str

class Settings(BaseSettings):
    interface: str = "127.0.0.1"
    nameservers: List[str] = [ "8.8.8.8" ]
    ipv6: bool = False
    tcp: bool = False
    port: int = 53
    configfile: FilePath = "dnschef.toml"

settings = Settings()
app = FastAPI(
    title='DNSChef-NG',
    version=__version__
)

@app.on_event("startup")
async def startup_event():
    print(header)
    kitchen.CONFIG = parse_config_file(settings.configfile)

    # Log to file
    fh = logging.handlers.WatchedFileHandler("dnschef.log")
    fh.setFormatter(plain_formatter)
    log.addHandler(fh)

    # This will effectively duplicate all logs and save them in capturer.entries in JSON format
    jh = logging.StreamHandler()
    jh.setFormatter(json_capture_formatter)
    log.addHandler(jh)

    # Launch DNSChef
    asyncio.create_task(
        start_server(
            interface=settings.interface,
            nameservers=settings.nameservers,
            tcp=settings.tcp,
            ipv6=settings.ipv6,
            port=settings.port
        )
    )

"""
@app.on_event("shutdown")
async def shutdown_event():
    dns_chef_coroutine.cancel()
    log.debug("Shutting down DNSChef API")
"""

@app.put("/")
async def add_record(record: Record):
    kitchen.CONFIG[record.type.value][record.domain] = record.value
    return 200


@app.delete("/")
async def delete_record(record: Record):
    del kitchen.CONFIG[record.type.value][record.domain]
    return 200


@app.get("/")
async def get_records():
    return kitchen.CONFIG


@app.get("/logs")
async def get_logs(type: Optional[DnsQueryType] = None, name: Optional[str] = None):
    events = ['cooking response', 'proxying response']

    if not type and not name:
        return capturer.entries

    if type and name:
        filter_expression = lambda l: l['event'] in events and l['type'] == type.value and name in l['name']
    elif type:
        filter_expression = lambda l: l['event'] in events and l['type'] == type.value
    elif name:
        filter_expression = lambda l: l['event'] in events and name in l['name']

    return list(
        filter(
            filter_expression,
            capturer.entries
        )
    )
