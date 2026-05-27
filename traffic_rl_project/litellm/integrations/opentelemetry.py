"""Minimal OpenTelemetry shim used by Agent Lightning imports."""

from dataclasses import dataclass

from .custom_logger import CustomLogger


@dataclass
class OpenTelemetryConfig:
    exporter: object | None = None


class OpenTelemetry(CustomLogger):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    @staticmethod
    def set_attributes(*args, **kwargs):
        return None
