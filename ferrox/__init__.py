"""Ferrox - Cross-platform AI CLI Tool"""

__version__ = "0.1.0"
__author__ = "Ferrox Team"

# Lazy imports to avoid dependency conflicts
def __getattr__(name):
    if name == "JsonMode":
        from instructor import JsonMode
        return JsonMode
    elif name == "Graph":
        from langgraph.graph import Graph
        return Graph
    elif name == "Mirascope":
        from mirascope import Mirascope
        return Mirascope
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__version__ = "0.1.0"
__author__ = "Ferrox Team"