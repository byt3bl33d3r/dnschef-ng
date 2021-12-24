import logging

handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter(
        style="{",
        fmt="[{name}:{filename}] {levelname} - {message}"
    )
)

log = logging.getLogger("dnschef_n")
log.setLevel(logging.INFO)
log.addHandler(handler)
