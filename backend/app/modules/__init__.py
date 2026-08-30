"""The modules built on the kernel. Importing this package declares them.

`agentquilt catalog` and `serve` both import it, so an operation reaches the
registry, and a surface reaches the prefix, by being imported here and nowhere
else. `memory` is not here: in Phase 1 it declares nothing and registers nothing.
"""

from __future__ import annotations

from app.modules.governance import service as governance
from app.modules.skills import service as skills
from app.modules.surfaces import service as surfaces

__all__ = ["governance", "skills", "surfaces"]
