# Expose subpackages for easy imports
import importlib

def __getattr__(name):
    if name == "kafka_translator":
        return importlib.import_module(f"services.{name}")
    raise AttributeError(name)
