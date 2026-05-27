"""Minimal LiteLLM compatibility layer for Agent Lightning imports.

This project only needs Agent Lightning's RL-related APIs. The installed
LiteLLM package in the environment is incomplete, so we provide a small local
shim that satisfies Agent Lightning's import-time dependencies without adding
new LLM packages.
"""

from . import utils  # noqa: F401

callbacks = []


class _LoggingCallbackManager:
    def _reset_all_callbacks(self):
        callbacks.clear()


logging_callback_manager = _LoggingCallbackManager()
