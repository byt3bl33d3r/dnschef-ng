from rich.traceback import install

import logging
import logging.handlers
import structlog

install(show_locals=True)

capturer = structlog.testing.LogCapture()
timestamper = structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S")

pre_chain = [
    # Add the log level and a timestamp to the event_dict if the log entry
    # is not from structlog.
    structlog.stdlib.add_log_level,
    # Add extra attributes of LogRecord objects to the event dictionary
    # so that values passed in the extra parameter of log methods pass
    # through to log output.
    structlog.stdlib.ExtraAdder(),
    timestamper,
]

plain_formatter = structlog.stdlib.ProcessorFormatter(
    processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    foreign_pre_chain = pre_chain
)

colored_formatter = structlog.stdlib.ProcessorFormatter(
    processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(colors=True, exception_formatter=structlog.dev.rich_traceback),
    ],
    foreign_pre_chain = pre_chain
)

json_capture_formatter = structlog.stdlib.ProcessorFormatter(
    processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        capturer,
        structlog.processors.JSONRenderer(),
    ],
    foreign_pre_chain = pre_chain
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
