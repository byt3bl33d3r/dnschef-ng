#!/usr/bin/env python3

#
# DNSChef is a highly configurable DNS Proxy for Penetration Testers 
# and Malware Analysts. Please visit http://thesprawl.org/projects/dnschef/
# for the latest version and documentation. Please forward all issues and
# concerns to iphelix [at] thesprawl.org.

# Copyright (C) 2019 Peter Kacherginsky, Marcello Salvati
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met: 
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer. 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its contributors
#    may be used to endorse or promote products derived from this software without 
#    specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from dnschef import kitchen
from dnschef.protocols import start_server

from dnschef.logger import log, plain_formatter, debug_formatter
from dnschef.utils import header, parse_config_file

from argparse import ArgumentParser

import asyncio
import logging
import logging.handlers
import sys

def main():
    # Parse command line arguments
    parser = ArgumentParser(usage = "dnschef.py [options]:\n" + header, description="DNSChef is a highly configurable DNS Proxy for Penetration Testers and Malware Analysts. It is capable of fine configuration of which DNS replies to modify or to simply proxy with real responses. In order to take advantage of the tool you must either manually configure or poison DNS server entry to point to DNSChef. The tool requires root privileges to run on privileged ports." )

    fakegroup = parser.add_argument_group("Fake DNS records:")
    fakegroup.add_argument('--fakeip', metavar="192.0.2.1", help='IP address to use for matching DNS queries. If you use this parameter without specifying domain names, then all \'A\' queries will be spoofed. Consider using --file argument if you need to define more than one IP address.')
    fakegroup.add_argument('--fakeipv6', metavar="2001:db8::1", help='IPv6 address to use for matching DNS queries. If you use this parameter without specifying domain names, then all \'AAAA\' queries will be spoofed. Consider using --file argument if you need to define more than one IPv6 address.')
    fakegroup.add_argument('--fakemail', metavar="mail.fake.com", help='MX name to use for matching DNS queries. If you use this parameter without specifying domain names, then all \'MX\' queries will be spoofed. Consider using --file argument if you need to define more than one MX record.')
    fakegroup.add_argument('--fakealias', metavar="www.fake.com", help='CNAME name to use for matching DNS queries. If you use this parameter without specifying domain names, then all \'CNAME\' queries will be spoofed. Consider using --file argument if you need to define more than one CNAME record.')
    fakegroup.add_argument('--fakens', metavar="ns.fake.com", help='NS name to use for matching DNS queries. If you use this parameter without specifying domain names, then all \'NS\' queries will be spoofed. Consider using --file argument if you need to define more than one NS record.')
    fakegroup.add_argument('--file', help="Specify a file containing a list of DOMAIN=IP pairs (one pair per line) used for DNS responses. For example: google.com=1.1.1.1 will force all queries to 'google.com' to be resolved to '1.1.1.1'. IPv6 addresses will be automatically detected. You can be even more specific by combining --file with other arguments. However, data obtained from the file will take precedence over others.")

    mexclusivegroup = parser.add_mutually_exclusive_group()
    mexclusivegroup.add_argument('--fakedomains', metavar="thesprawl.org,google.com", help='A comma separated list of domain names which will be resolved to FAKE values specified in the the above parameters. All other domain names will be resolved to their true values.')
    mexclusivegroup.add_argument('--truedomains', metavar="thesprawl.org,google.com", help='A comma separated list of domain names which will be resolved to their TRUE values. All other domain names will be resolved to fake values specified in the above parameters.')

    rungroup = parser.add_argument_group("Optional runtime parameters.")
    rungroup.add_argument("--logfile", metavar="FILE", help="Specify a log file to record all activity")
    rungroup.add_argument("--nameservers", metavar="8.8.8.8#53 or 4.2.2.1#53#tcp or 2001:4860:4860::8888", default='8.8.8.8', help='A comma separated list of alternative DNS servers to use with proxied requests. Nameservers can have either IP or IP#PORT format. A randomly selected server from the list will be used for proxy requests when provided with multiple servers. By default, the tool uses Google\'s public DNS server 8.8.8.8 when running in IPv4 mode and 2001:4860:4860::8888 when running in IPv6 mode.')
    rungroup.add_argument("-i","--interface", metavar="127.0.0.1 or ::1", default="127.0.0.1", help='Define an interface to use for the DNS listener. By default, the tool uses 127.0.0.1 for IPv4 mode and ::1 for IPv6 mode.')
    rungroup.add_argument("-t","--tcp", action="store_true", default=False, help="Use TCP DNS proxy instead of the default UDP.")
    rungroup.add_argument("-6","--ipv6", action="store_true", default=False, help="Run in IPv6 mode.")
    rungroup.add_argument("-p","--port", metavar=53, default=53, type=int, help='Port number to listen for DNS requests.')
    rungroup.add_argument("-v", "--verbose", action="store_true", dest="verbose", default=False, help="Run in verbose mode")

    options = parser.parse_args()

    # Print program header
    print(header)

    if options.verbose:
        log.setLevel(logging.DEBUG)
        log.handlers[0].setFormatter(debug_formatter)
        log.debug("running in verbose mode")

    if not (options.fakeip or options.fakeipv6) and (options.fakedomains or options.truedomains):
        log.error("you have forgotten to specify which IP to use for fake responses")
        sys.exit(0)

    # Adjust defaults for IPv6
    if options.ipv6:
        if options.interface == "127.0.0.1":
            options.interface = "::1"

        if options.nameservers == "8.8.8.8":
            options.nameservers = "2001:4860:4860::8888"

    # Use alternative DNS servers
    if options.nameservers:
        nameservers = options.nameservers.split(',')

    # External file definitions
    if options.file:
        kitchen.CONFIG = parse_config_file(options.file)

    # DNS Record and Domain Name definitions
    if options.fakeip or options.fakeipv6 or options.fakemail or options.fakealias or options.fakens:
        fakeip     = options.fakeip
        fakeipv6   = options.fakeipv6
        fakemail   = options.fakemail
        fakealias  = options.fakealias
        fakens     = options.fakens

        if options.fakedomains:
            for domain in options.fakedomains.split(','):

                # Make domain case insensitive
                domain = domain.lower()
                domain = domain.strip()

                if fakeip:
                    kitchen.CONFIG["A"][domain] = fakeip
                    log.info(f"cooking A replies to point to {options.fakeip} matching: {domain}")

                if fakeipv6:
                    kitchen.CONFIG["AAAA"][domain] = fakeipv6
                    log.info(f"cooking AAAA replies to point to {options.fakeipv6} matching: {domain}")

                if fakemail:
                    kitchen.CONFIG["MX"][domain] = fakemail
                    log.info(f"cooking MX replies to point to {options.fakemail} matching: {domain}")

                if fakealias:
                    kitchen.CONFIG["CNAME"][domain] = fakealias
                    log.info(f"cooking CNAME replies to point to {options.fakealias} matching: {domain}")

                if fakens:
                    kitchen.CONFIG["NS"][domain] = fakens
                    log.info(f"cooking NS replies to point to {options.fakens} matching: {domain}")

        elif options.truedomains:
            for domain in options.truedomains.split(','):

                # Make domain case insensitive
                domain = domain.lower()
                domain = domain.strip()

                if fakeip:
                    kitchen.CONFIG["A"][domain] = False
                    log.info(f"cooking A replies to point to {options.fakeip} not matching: {domain}")
                    kitchen.CONFIG["A"]['*'] = fakeip

                if fakeipv6:
                    kitchen.CONFIG["AAAA"][domain] = False
                    log.info(f"cooking AAAA replies to point to {options.fakeipv6} not matching: {domain}")
                    kitchen.CONFIG["AAAA"]['*'] = fakeipv6

                if fakemail:
                    kitchen.CONFIG["MX"][domain] = False
                    log.info(f"cooking MX replies to point to {options.fakemail} not matching: {domain}")
                    kitchen.CONFIG["MX"]['*'] = fakemail

                if fakealias:
                    kitchen.CONFIG["CNAME"][domain] = False
                    log.info(f"cooking CNAME replies to point to {options.fakealias} not matching: {domain}")
                    kitchen.CONFIG["CNAME"]['*'] = fakealias

                if fakens:
                    kitchen.CONFIG["NS"][domain] = False
                    log.info(f"cooking NS replies to point to {options.fakens} not matching: {domain}")
                    kitchen.CONFIG["NS"]['*'] = fakealias

        else:
            if fakeip:
                kitchen.CONFIG["A"]['*'] = fakeip
                log.info(f"cooking all A replies to point to {fakeip}")

            if fakeipv6:
                kitchen.CONFIG["AAAA"]['*'] = fakeipv6
                log.info(f"cooking all AAAA replies to point to {fakeipv6}")

            if fakemail:
                kitchen.CONFIG["MX"]['*'] = fakemail
                log.info(f"cooking all MX replies to point to {fakemail}")

            if fakealias:
                kitchen.CONFIG["CNAME"]['*'] = fakealias
                log.info(f"cooking all CNAME replies to point to {fakealias}")

            if fakens:
                kitchen.CONFIG["NS"]['*'] = fakens
                log.info(f"cooking all NS replies to point to {fakens}")

    # Proxy all DNS requests
    if not options.fakeip and not options.fakeipv6 and not options.fakemail and not options.fakealias and not options.fakens and not options.file:
        log.info("running in full proxy mode as no parameters were specified")

    if options.logfile:
        fh = logging.handlers.WatchedFileHandler(options.logfile)
        fh.setFormatter(plain_formatter)
        fh.setLevel(
            logging.INFO
            if not options.verbose 
            else logging.DEBUG
        )
        log.addHandler(fh)

    # Launch DNSChef
    asyncio.run(start_server(
        interface=options.interface,
        nameservers=nameservers,
        tcp=options.tcp,
        ipv6=options.ipv6,
        port=options.port
    ))

if __name__ == "__main__":
    main()
