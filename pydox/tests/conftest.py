import sys
import os
import logging
import shutil


log = logging.getLogger("pydox.tests.conftests")


def pytest_sessionstart(session):
    log.debug("Starting tests session")
    log.debug("Initial session state: %s" % session)
    pass


def pytest_sessionfinish(session, exitstatus):
    # try:
    #     shutil.rmtree(os.getenv('FTP_HOME'))
    # except:
    #     pass
    log.debug("Ending tests session")
    log.debug("Final session state: %s" % session)
    pass