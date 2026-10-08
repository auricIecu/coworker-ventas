"""Runnable injection example. This remains DEMO, never a production connector."""

import os

from mostrador.bootstrap import demo_adapters
from mostrador.domain import SearchIntent
from mostrador.ports import Adapters


class ExactSearchAssistant:
    def interpret(self, message: str) -> SearchIntent:
        return SearchIntent(message.strip())


def build_adapters() -> Adapters:
    adapters = demo_adapters(os.getenv("COPILOT_DB_PATH", ".local/custom.sqlite"))
    adapters.assistant = ExactSearchAssistant()
    return adapters
