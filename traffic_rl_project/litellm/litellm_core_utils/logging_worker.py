"""Minimal logging worker shim used by Agent Lightning."""


class LoggingWorker:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


GLOBAL_LOGGING_WORKER = LoggingWorker()
