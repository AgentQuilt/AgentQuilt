"""Naming lint over the migration sources (naming-conventions.md:93).

Regex over the text, not an import: a migration is only ever read here, and the
chain must lint before it is safe to run.
"""

from __future__ import annotations

import re
from pathlib import Path

VERSIONS = Path(__file__).parent / "versions"

TABLE_RE = re.compile(r"""create_table\(\s*["']([^"']+)["']""")
NAMED_RE = re.compile(
    r"""(create_index|create_unique_constraint|create_foreign_key"""
    r"""|create_check_constraint)\(\s*["']([^"']+)["']"""
)
# Singular last words that end in s, and irregular plurals that do not.
SINGULAR_ENDING_IN_S = {"status", "address", "alias", "access", "basis", "analysis"}
IRREGULAR_PLURALS = {
    "people", "children", "men", "women", "data", "criteria", "media", "indices",
}
PREFIXES = {
    "create_index": "ix_",
    "create_unique_constraint": "uq_",
    "create_foreign_key": "fk_",
    "create_check_constraint": "ck_",
}


def check_source(name: str, source: str) -> list[str]:
    """Violations in one migration file, as `file: what is wrong` lines."""
    problems: list[str] = []
    for table in TABLE_RE.findall(source):
        last = table.split("_")[-1]
        plural_s = last.endswith("s") and last not in SINGULAR_ENDING_IN_S
        if plural_s or last in IRREGULAR_PLURALS:
            problems.append(
                f"{name}: table '{table}' reads as plural; table names are singular"
                " (a singular word ending in s goes in SINGULAR_ENDING_IN_S)"
            )
    for op_name, obj in NAMED_RE.findall(source):
        prefix = PREFIXES[op_name]
        if not obj.startswith(prefix):
            problems.append(
                f"{name}: '{obj}' from {op_name} needs the '{prefix}' prefix"
            )
    return problems


def check_migrations() -> list[str]:
    return [
        problem
        for path in sorted(VERSIONS.glob("*.py"))
        for problem in check_source(path.name, path.read_text(encoding="utf-8"))
    ]
