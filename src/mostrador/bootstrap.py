import importlib
import os

from mostrador.adapters.demo import DemoIdentity, KeywordAssistant
from mostrador.adapters.sqlite import Database, SQLiteCommerce, SQLiteWorkflowStore
from mostrador.ports import Adapters


def demo_adapters(path: str) -> Adapters:
    database = Database(path)
    return Adapters(
        SQLiteCommerce(database),
        SQLiteWorkflowStore(database),
        DemoIdentity(),
        KeywordAssistant(),
        is_demo=True,
    )


def configured_adapters() -> Adapters:
    mode = os.getenv("COPILOT_MODE", "external")
    factory = os.getenv("COPILOT_ADAPTER_FACTORY")
    if mode not in {"demo", "external"}:
        raise RuntimeError("COPILOT_MODE must be demo or external")
    if factory:
        module_name, function_name = factory.split(":", 1)
        adapters = getattr(importlib.import_module(module_name), function_name)()
        if not isinstance(adapters, Adapters):
            raise RuntimeError("Factory must return Adapters")
        if mode == "external" and adapters.is_demo:
            raise RuntimeError("Demo adapters are forbidden in external mode")
        return adapters
    if mode == "demo":
        return demo_adapters(os.getenv("COPILOT_DB_PATH", ".local/mostrador.sqlite"))
    raise RuntimeError("External mode requires COPILOT_ADAPTER_FACTORY=module:factory")
