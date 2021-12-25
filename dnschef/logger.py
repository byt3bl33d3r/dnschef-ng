from rich.traceback import install

import logging
import logging.handlers
import structlog

install(show_locals=True)

capturer = structlog.testing.LogCapture()
timestamper = structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S")

plain_formatter = structlog.stdlib.ProcessorFormatter(
    processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        #structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(colors=False),
    ]
)

colored_formatter = structlog.stdlib.ProcessorFormatter(
    processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        #structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(colors=True, exception_formatter=structlog.dev.rich_traceback),
    ]
)

debug_formatter = structlog.stdlib.ProcessorFormatter(
    processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.stdlib.add_log_level,
        #structlog.stdlib.add_logger_name,
        structlog.dev.ConsoleRenderer(colors=True, exception_formatter=structlog.dev.rich_traceback),
    ]
)

json_capture_formatter = structlog.stdlib.ProcessorFormatter(
    processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        capturer,
        structlog.processors.JSONRenderer(),
    ]
)

sh = logging.StreamHandler()
sh.setFormatter(colored_formatter)

dnschef_logger = logging.getLogger("dnschef")
dnschef_logger.setLevel(logging.INFO)
dnschef_logger.addHandler(sh)

structlog.configure(
    processors=[
        #structlog.stdlib.filter_by_level,
        #structlog.stdlib.add_logger_name,
        #structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        #structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

log = structlog.get_logger("dnschef")
