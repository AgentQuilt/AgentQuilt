"""The modules built on the kernel. Importing this package declares them.

`agentquilt catalog` and `serve` both import it, so an operation reaches the
registry by being imported here and nowhere else.
"""

from __future__ import annotations

from app.modules.governance import service as governance

__all__ = ["governance"]
