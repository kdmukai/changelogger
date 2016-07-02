import logging
from .models import ChangeLogTracker

logger = logging.getLogger(__name__)



class ChangeLoggerMiddleware(object):

    def process_request(self, request):
        try:
            ChangeLogTracker.thread.request = request
        except Exception as e:
            logger.error(e)

