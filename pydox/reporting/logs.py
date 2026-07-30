import logging
import pydox as do

logger = logging.getLogger("pydox")
logger.setLevel(logging.DEBUG)

# create file handler which regular logs, even debug messages
fh = logging.FileHandler("pydox.log")
fh.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
        datefmt="%I:%M:%S %p",
    )
)
logger.addHandler(fh)

# create console handler for users, with a filter to log only INFO and WARNING


class PydoxFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "PYDOX - %(asctime)s - %(message)s"
    # format = "%(levelname)s - %(message)s"
    # format = "%(levelname)s - %(message)s [%(name)s]"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%I:%M:%S")
        return formatter.format(record)


class PydoxFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.INFO:
            return True
        if record.levelno == logging.WARNING:
            return True
        return False


stream = logging.StreamHandler()
# stream.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
# stream.setFormatter(logging.Formatter("%(levelname)s - %(message)s [%(name)s]"))
stream.setFormatter(PydoxFormatter())
stream.addFilter(filter=PydoxFilter(name="pydox_filter"))

if do.get_params("pydox.screen_log"):
    logger.addHandler(stream)


class _print_log:
    def debug(self, msg: str = "", logger: logging.Logger = None, level: int = 0):
        if int(level) >= do.get_params("pydox.screen_log_level"):
            logger.debug(msg)

    def info(self, msg: str = "", logger: logging.Logger = None, level: int = 0):
        if int(level) >= do.get_params("pydox.screen_log_level"):
            logger.info(msg)

    def warning(self, msg: str = "", logger: logging.Logger = None, level: int = 0):
        if int(level) >= do.get_params("pydox.screen_log_level"):
            logger.warning(msg)


print_log = _print_log()
