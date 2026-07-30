import logging
import datetime
from pathlib import Path

import pydox as do

logger = logging.getLogger("pydox")
logger.setLevel(logging.DEBUG)

# Create a file handler with regular logs, even debug messages
logfolder = Path(do.get_params("output.root")).joinpath("logs")
logfolder.mkdir(parents=True, exist_ok=True)

logfile = logfolder.joinpath(
    f"{do.tmp_root().name}.log"
)  # Use timestamp from tmp root, makes easier to link tmp files with log files.

fh = logging.FileHandler(logfile)
fh.setFormatter(
    logging.Formatter(
        "%(asctime)s - %(levelname)-7s - %(message)s",
        datefmt="%H:%M:%S",
    )
)
logger.addHandler(fh)

logfile = logfolder.joinpath(
    f"{do.tmp_root().name}-full.log"
)  # Use timestamp from tmp root, makes easier to link tmp files with log files.

fh = logging.FileHandler(logfile)
fh.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(levelname)s] %(threadName)s:%(name)s:%(lineno)d: %(message)s",
        datefmt="%H:%M:%S",
    )
)
logger.addHandler(fh)


class getLogger:

    def __init__(self, name: str, context_level: int = 0):

        self.log: logging.Logger = logging.getLogger(name)
        self.context_level = context_level
        self.pydox_level = do.get_params("pydox.screen_log_level")
        self.screen_log = do.get_params("pydox.screen_log")
        # if self.filtered:
        #     print(
        #         f"Logger '{name}' created with context_level={self.context_level} >= pydox_level={self.pydox_level}"
        #     )
        # else:
        #     print(
        #         f"Logger '{name}' created but context_level={self.context_level} < pydox_level={self.pydox_level}"
        #     )

    @property
    def filtered(self):
        return self.screen_log and self.context_level >= self.pydox_level

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "PYDOX - {asctime} - {message}"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def print(self, msg, levelno):
        # datefmt = "%Y%m%d%H%M%S%f"
        datefmt = "%Hh%M:%S"
        asctime = datetime.datetime.now(datetime.timezone.utc).strftime(datefmt)
        msg = self.FORMATS.get(levelno).format(message=msg, asctime=asctime)
        print(msg)

    def error(self, msg: str, *args, **kwargs):
        self.log.error(msg, *args, **kwargs)  # Regular logging to file
        if self.filtered:
            self.print(msg, levelno=logging.ERROR)  # Custom logging to std.out

    def warning(self, msg: str, *args, **kwargs):
        self.log.warning(msg, *args, **kwargs)  # Regular logging to file
        if self.filtered:
            self.print(msg, levelno=logging.WARNING)  # Custom logging to std.out

    def debug(self, msg: str, *args, **kwargs):
        self.log.debug(msg, *args, **kwargs)  # Regular logging to file
        if self.filtered:
            self.print(msg, levelno=logging.DEBUG)  # Custom logging to std.out

    def info(self, msg: str, *args, **kwargs):
        self.log.info(msg, *args, **kwargs)  # Regular logging to file
        if self.filtered:
            self.print(msg, levelno=logging.INFO)  # Custom logging to std.out
