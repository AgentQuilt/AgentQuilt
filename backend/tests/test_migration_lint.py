from lint import check_migrations, check_source

BAD = """
op.create_table("runs")
op.create_index("run_org_idx", "run", ["org_id"])
op.create_unique_constraint("uq_run_key", "run", ["org_id"])
"""


def test_migration_chain_names_are_clean() -> None:
    assert check_migrations() == []


def test_lint_catches_plural_tables_and_missing_prefixes() -> None:
    problems = check_source("0001_bad.py", BAD)
    assert len(problems) == 2
    assert "plural" in problems[0]
    assert "'ix_' prefix" in problems[1]


def test_singular_word_ending_in_s_is_not_plural() -> None:
    assert check_source("0002_ok.py", 'op.create_table("status")') == []


def test_irregular_plural_is_caught() -> None:
    assert len(check_source("0003_bad.py", 'op.create_table("people")')) == 1
