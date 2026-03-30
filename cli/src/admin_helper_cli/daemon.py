import multiprocessing
import time

from admin_helper_cli.console import console
from admin_helper_cli.logger import logger



class Daemon:
    def __init__(self):
        logger.debug("Starting daemon")
        self.services = [        ]
        
        self.loop()

    def loop(self):
        # Start all services
        for service in self.services:
            service.start()
            
        try:
            while True:
                logger.debug("loop")
                time.sleep(1)
        except KeyboardInterrupt:
            logger.debug("exiting")