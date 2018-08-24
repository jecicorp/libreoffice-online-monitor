import logging
from multiprocessing import Process

from .options import configs
from .LoolMonitor import LoolMonitor
from .AlfrescoHandler import AlfrescoHandler


ch = logging.StreamHandler()
# FORMAT = '%(asctime)-15s %(message)s'
# logging.basicConfig(format=FORMAT)
ch.setLevel(logging.DEBUG)

logger = logging.getLogger('websockets')
logger.setLevel(logging.WARN)
logger.addHandler(ch)

logger = logging.getLogger('LoolMonitor')
logger.setLevel(logging.DEBUG)
logger.addHandler(ch)

logger = logging.getLogger('AlfrescoHandler')
logger.setLevel(logging.DEBUG)
logger.addHandler(ch)


def start_monitor(host=None, port=8765):
    monitor = LoolMonitor(host, port)
    alfHandler = AlfrescoHandler(
                    configs['user'],
                    configs['password'],
                    configs['webscript']
    )
    alfHandler.start()
    monitor.work_handler.append(alfHandler)
    monitor.start()


if __name__ == '__main__':
    Process(target=start_monitor).start()
    logger.info("Monitor is started")