"""Runtime hook: intercept scipy array_api_compat missing submodule imports.

scipy._external.array_api_compat.numpy tries to import fft and linalg submodules
that don't exist in newer scipy versions. This hook creates stub modules for them.
"""
import sys

def _create_stub_module(name):
    class StubModule:
        __name__ = name
        __package__ = '.'.join(name.split('.')[:-1])
        __path__ = []
        def __getattr__(self, attr):
            if attr.startswith('__'):
                raise AttributeError(f"{name!r} object has no attribute {attr!r}")
            return _create_stub_module(f"{name}.{attr}")
    m = StubModule()
    sys.modules[name] = m
    return m

_create_stub_module('scipy._external.array_api_compat.numpy.fft')
_create_stub_module('scipy._external.array_api_compat.numpy.linalg')
