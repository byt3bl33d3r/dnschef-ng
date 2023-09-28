from dnschef import __version__
from dnschef.kitchen import nametodns
from dnschef.logger import log
from configparser import ConfigParser


header  = "          _                _          __  \n"
header += "         | | version {}  | |        / _| \n".format(__version__)
header += "       __| |_ __  ___  ___| |__   ___| |_ \n"
header += "      / _` | '_ \/ __|/ __| '_ \ / _ \  _|\n"
header += "     | (_| | | | \__ \ (__| | | |  __/ |  \n"
header += "      \__,_|_| |_|___/\___|_| |_|\___|_|  \n"
header += "                @iphelix // @byt3bl33d3r  \n"


def parse_config_file(config_file: str = "dnschef.ini"):
    log.debug("Parsing config file", path=config_file)
    config = ConfigParser()
    config.read(config_file)
    for section in config.sections():

        if section in nametodns:
            for domain, record in config.items(section):

                # Make domain case insensitive
                domain = domain.lower()

                nametodns[section][domain] = record
                log.info("cooking replies", section=section, domain=domain, record=record)
        else:
            log.warning(f"DNS record '{section}' is not supported. Ignoring section contents.")
