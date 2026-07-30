import logging
import datetime
from pathlib import Path
import sys

import pydox as do

logger = logging.getLogger("pydox")
logger.setLevel(logging.DEBUG)

logfolder = Path(do.get_params("output.root")).joinpath("logs")
logfolder.mkdir(parents=True, exist_ok=True)

# Create a file handler for debug purposes:
logfile = logfolder.joinpath(
    f"{do.tmp_root().name}.log"
)  # Use timestamp from tmp root, making easier to link tmp files with log files.
fh = logging.FileHandler(logfile)
fh.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(levelname)s] %(threadName)s:%(name)s:%(lineno)d: %(message)s",
        datefmt="%H:%M:%S",
    )
)
logger.addHandler(fh)


# Create another file handler just with messages (no thread, logger or file name, nore line number)

logfile = logfolder.joinpath(
    f"{do.tmp_root().name}-small.log"
)  # Use timestamp from tmp root, makes easier to link tmp files with log files.
fh = logging.FileHandler(logfile)
fh.setFormatter(
    logging.Formatter(
        "%(asctime)s - %(levelname)-7s - %(message)s",
        datefmt="%H:%M:%S",
    )
)
logger.addHandler(fh)


class getLogger:
    """A class to be used for logging and user feedbacks

    We use this custom logging system to be able to easily filter messages to be displayed on screen for user feedbacks.

    Log messages are sent to 3 channels:
    - 1 log file with exhaustive information for Pydox developers at: <"output.root">/logs/<"%Y%m%d%H%M%S%f">.log
    - 1 log file only with messages for Pydox developers at: <"output.root">/logs/<"%Y%m%d%H%M%S%f">-small.log
    - stdout for Pydox users (screen).

    The pydox setting "pydox.logging_level" can be used to filter messages along the `standard logging library value <https://docs.python.org/3/library/logging.html#logging-levels>`_ (eg: 'DEBUG', 'INFO', 'WARNING', 'ERROR').
    This setting applies to all channels (files and stdout).

    The pydox setting "pydox.screen_log_context_level" is used to filter along where in the code a message is logged.
    This setting only applies to the stdout channel (screen).

    Therefore, and for instance, it is possible to print 'INFO' messages only at high-levels in the library (eg: `Calibration.fit()`), while low-level routines can also log 'INFO' messages.

    Examples
    --------
    ..code-block :: python
        ..caption: Internal use

        from pydox.reporting.logs import getLogger

        # Get a logger for messages with a 20 local context level:
        log = getLogger("pydox.calibration.methods.in_air.spec", context_level=20) # High-level context

        # Log anything on screen:
        log.info("I just happened to be doing this")
        log.error("Damned it !")
        log.debug("")
        log.warning("Be careful about this !")

    """

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "PYDOX - {asctime} - {level} - {message}"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    LEVEL = {
        0: "NOTSET",
        10: "DEBUG",
        20: "INFO",
        30: "WARNING",
        40: "ERROR",
        50: "CRITICAL",
    }

    def __init__(self, name: str, context_level: int = 0):
        """

        Parameters
        ----------
        name: str
            Typically a string-dotted form of the module the logger is called from.
            Eg: "pydox.calibration.methods.in_air.spec"
        context_level: int
            Expected values:
             - >=0: low-level APIs,
             - >=10: intermediate-level APIs,
             - >=20: high-level APIs.
        """

        self.log: logging.Logger = logging.getLogger(name)
        self.log.setLevel(getattr(logging, do.get_params("pydox.logging_level")))
        self.min_context_level = do.get_params("pydox.screen.min_context_level")
        self.screen_log = do.get_params("pydox.screen.log")
        self.context_level = context_level

    @property
    def filtered(self):
        """Return True if a message should be displayed

        This depends on:
         - the "pydox.screen.log" setting, must be True,
         - the "pydox.screen.min_context_level" setting the minimum level of logger context to display messages from,
         - the context level for which this logger was created (must be higher or equal to "pydox.screen.min_context_level").

        """
        return self.screen_log and self.context_level >= self.min_context_level

    def print(self, msg: str, levelno: int):
        if self.filtered:
            datefmt = "%Hh%M:%S"
            asctime = datetime.datetime.now(datetime.timezone.utc).strftime(datefmt)
            msg = self.FORMATS.get(levelno).format(
                message=msg, asctime=asctime, level=self.LEVEL[levelno]
            )
            print(msg, file=sys.stdout)

    def debug(self, msg: str, *args, **kwargs):
        self.log.debug(msg, *args, **kwargs)  # Regular logging to file handlers
        self.print(msg, levelno=logging.DEBUG)  # Custom logging to std.out

    def info(self, msg: str, *args, **kwargs):
        self.log.info(msg, *args, **kwargs)  # Regular logging to file handlers
        self.print(msg, levelno=logging.INFO)  # Custom logging to std.out

    def warning(self, msg: str, *args, **kwargs):
        self.log.warning(msg, *args, **kwargs)  # Regular logging to file handlers
        self.print(msg, levelno=logging.WARNING)  # Custom logging to std.out

    def error(self, msg: str, *args, **kwargs):
        self.log.error(msg, *args, **kwargs)  # Regular logging to file handlers
        self.print(msg, levelno=logging.ERROR)  # Custom logging to std.out

    def critical(self, msg: str, *args, **kwargs):
        self.log.info(msg, *args, **kwargs)  # Regular logging to file handlers
        self.print(msg, levelno=logging.CRITICAL)  # Custom logging to std.out
