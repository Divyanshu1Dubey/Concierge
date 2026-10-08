"""
Core middleware for HeyJarvis.
"""
import time
import logging

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """Log request timing and info."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration = (time.time() - start) * 1000

        if duration > 1000:
            logger.warning(f"Slow request: {request.method} {request.path} took {duration:.0f}ms")

        return response
