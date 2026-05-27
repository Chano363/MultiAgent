"""Minimal FastAPI proxy app stub used by Agent Lightning."""


class _AppStub:
    def __init__(self):
        self.user_middleware = []

    def add_middleware(self, *args, **kwargs):
        return None


app = _AppStub()


def save_worker_config(*args, **kwargs):
    return None
