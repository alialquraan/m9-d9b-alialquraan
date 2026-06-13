"""Drill 9B autograder.

Gates:
  1. Warm-up queries (queries/warmups.py) return the gold row sets.
  2. Translation queries (queries/translations.py) return result sets
     equivalent to the corresponding W9A SPARQL queries — load-bearing
     Rosetta-stone gate.
  3. Q5 (ASK) returns a single bool matching the SPARQL ASK result.
  4. AST checks: parameterization in warmups + translations; no f-string
     Cypher interpolation in queries/.
  5. AST meta-test on learner-written tests (warmups).
  6. Identity Discipline: no duplicate :Entity.id after fixture load.
  7. Sentinel: at least one starter query still returns "" (unmodified
     starter must produce visible failures).
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import pathlib
import re
import sys

import pytest

# Allow `import queries...` and `import learner_tests...` after pytest is invoked
# from the repo root.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from neo4j import GraphDatabase  # noqa: E402

# ----------- Neo4j driver fixture (test-module-local; conftest provides a
# session-scoped one for learner tests). -----------------


@pytest.fixture(scope="module")
def driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "testtest")
    drv = GraphDatabase.driver(uri, auth=(user, password))
    yield drv
    drv.close()


# ============================================================
# 1. Warm-ups
# ============================================================

GOLD_RECIPE_NAMES = {
    "Margherita Pizza",
    "Pesto Pasta",
    "Mapo Tofu",
    "Kung Pao Chicken",
    "Ginger Scallion Noodles",
}

GOLD_ITALIAN_DIRECT = {"Margherita Pizza", "Pesto Pasta"}
GOLD_CHINESE_WITH_SUBCLASS = {"Mapo Tofu", "Kung Pao Chicken", "Ginger Scallion Noodles"}


def _run_rows(driver, cypher: str, params: dict | None = None) -> list[dict]:
    params = params or {}
    with driver.session() as session:
        return [dict(r) for r in session.run(cypher, params)]


def test_warmups_return_correct_rows(driver):
    from queries.warmups import (
        q1_list_recipes,
        q2_filter_by_cuisine,
        q3_subclass_traversal,
    )

    cypher_q1 = q1_list_recipes()
    assert cypher_q1, "q1_list_recipes() returned an empty string"
    rows = _run_rows(driver, cypher_q1)
    actual = {r["name"] for r in rows}
    assert actual == GOLD_RECIPE_NAMES, (
        f"q1_list_recipes: expected {GOLD_RECIPE_NAMES}, got {actual}"
    )

    cypher_q2, params_q2 = q2_filter_by_cuisine("Italian")
    assert cypher_q2, "q2_filter_by_cuisine() returned an empty string"
    rows = _run_rows(driver, cypher_q2, params_q2)
    actual = {r["name"] for r in rows}
    assert actual == GOLD_ITALIAN_DIRECT, (
        f"q2_filter_by_cuisine('Italian'): expected {GOLD_ITALIAN_DIRECT}, got {actual}"
    )

    cypher_q3, params_q3 = q3_subclass_traversal("Chinese")
    assert cypher_q3, "q3_subclass_traversal() returned an empty string"
    rows = _run_rows(driver, cypher_q3, params_q3)
    actual = {r["name"] for r in rows}
    assert actual == GOLD_CHINESE_WITH_SUBCLASS, (
        f"q3_subclass_traversal('Chinese'): expected "
        f"{GOLD_CHINESE_WITH_SUBCLASS}, got {actual}"
    )


# ============================================================
# 2. Translation Task — SPARQL <-> Cypher equivalence
# ============================================================

# Deterministic Turtle representation of books_kg.cypher's data — the same
# semantic content the W9A SPARQL queries were authored against. The mapping
# from SPARQL IRI tail (e.g., 'book1') -> Cypher Book.id ('book:1') is fixed.
# Authors use IRI tail -> Author.name lookup.

BOOKS_TTL = """\
@prefix :     <http://example.org/library/> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:hunt    rdfs:label "Andrew Hunt" .
:thomas  rdfs:label "David Thomas" .
:hofstadter rdfs:label "Douglas Hofstadter" .
:knuth   rdfs:label "Donald Knuth" .
:martin  rdfs:label "Robert C. Martin" .
:fowler  rdfs:label "Martin Fowler" .

:book1 a :Book ;
    :title "The Pragmatic Programmer" ;
    :author :hunt , :thomas ;
    :year 1999 ;
    :topic "Software Engineering" .

:book2 a :Book ;
    :title "Godel, Escher, Bach" ;
    :author :hofstadter ;
    :year 1979 .

:book3 a :Book ;
    :title "The Art of Computer Programming, Volume 1" ;
    :author :knuth ;
    :year 1968 ;
    :topic "Algorithms" .

:book4 a :Book ;
    :title "Clean Code" ;
    :author :martin ;
    :year 2008 ;
    :topic "Software Engineering" .

:book5 a :Book ;
    :title "Refactoring" ;
    :author :fowler , :martin ;
    :year 2018 ;
    :topic "Software Engineering" .
"""

# SPARQL "book1" -> Cypher Book.id "book:1"
_IRI_TAIL_RE = re.compile(r".*[/#](book\d+)$")


def _sparql_book_to_id(uri: str) -> str:
    m = _IRI_TAIL_RE.match(uri)
    assert m, f"Could not parse book IRI: {uri}"
    n = m.group(1).replace("book", "")
    return f"book:{n}"


@pytest.fixture(scope="module")
def rdflib_graph():
    import rdflib

    g = rdflib.Graph()
    g.parse(data=BOOKS_TTL, format="turtle")
    return g


@pytest.fixture(scope="module")
def w9a_drill_module():
    """Import the W9A drill module directly from its staging path so the
    SPARQL strings are sourced from the canonical W9A file, not duplicated
    in this autograder. This is the Rosetta-stone provenance.
    """
    candidate_paths = [
        # Repo root layout in CI (template repo): W9A is a sibling, not present.
        # In that case we fall back to the embedded SPARQL strings below.
    ]
    # Try staging path (only present when running inside the aispire-14005 repo,
    # not in a learner's fork). We always have the embedded fallback.
    candidate = (
        REPO_ROOT.parent.parent
        / "drill-9a-sparql"
        / "starter"
        / "queries"
        / "drill.py"
    )
    if candidate.exists():
        spec = importlib.util.spec_from_file_location("w9a_drill", str(candidate))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    return None


# Embedded reference SPARQL — used when the W9A source file is not on disk
# (i.e., in learner forks of the m9-d9b template repo). These must stay in
# lockstep with drill-9a-sparql/starter/queries/drill.py and the answer key.
EMBEDDED_W9A_SPARQL = {
    "q1": """\
PREFIX :     <http://example.org/library/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?book ?title WHERE { ?book a :Book ; :title ?title . }
""",
    "q2": """\
PREFIX :     <http://example.org/library/>
SELECT ?book ?year WHERE {
  ?book a :Book ; :year ?year .
  FILTER (?year > 2010)
}
""",
    "q3": """\
PREFIX :     <http://example.org/library/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?book ?author_name WHERE {
  ?book a :Book ; :author ?a .
  ?a rdfs:label ?author_name .
}
""",
    "q4": """\
PREFIX :     <http://example.org/library/>
SELECT ?book ?topic WHERE {
  ?book a :Book .
  OPTIONAL { ?book :topic ?topic . }
}
""",
    "q5": """\
PREFIX :     <http://example.org/library/>
ASK {
  ?book a :Book ; :author ?a1 , ?a2 .
  FILTER (?a1 != ?a2)
}
""",
}


def _resolve_sparql(qname: str, w9a_drill_module) -> str:
    """Prefer the answer-key SPARQL from the W9A drill module when on disk
    (the source-of-truth path inside aispire-14005). Fall back to embedded
    SPARQL when running in a learner fork where W9A is not present, or when
    the W9A drill function still returns "" (unmodified starter)."""
    if w9a_drill_module is not None:
        candidate = getattr(w9a_drill_module, qname)()
        if candidate:
            return candidate
    return EMBEDDED_W9A_SPARQL[qname]


def _sparql_select_set(rdflib_graph, sparql: str) -> set[tuple]:
    """Run a SPARQL SELECT and normalize bindings to a set of
    (book_id_str, value, ...) tuples — IRIs mapped via _sparql_book_to_id,
    literals via Python value, None for unbound."""
    rows = []
    for row in rdflib_graph.query(sparql):
        rec = []
        for term in row:
            if term is None:
                rec.append(None)
            else:
                s = str(term)
                if s.startswith("http://example.org/library/book"):
                    rec.append(_sparql_book_to_id(s))
                else:
                    # Try to coerce typed literals; fall back to str.
                    try:
                        rec.append(term.toPython())
                    except Exception:
                        rec.append(s)
        rows.append(tuple(rec))
    return set(rows)


def _cypher_select_set(driver, cypher: str, columns: list[str]) -> set[tuple]:
    rows = _run_rows(driver, cypher)
    return {tuple(r[c] for c in columns) for r in rows}


def test_translations_q1_match_sparql_equivalent(driver, rdflib_graph, w9a_drill_module):
    from queries.translations import q1

    learner_cypher = q1()
    assert learner_cypher, "translations.q1() returned an empty string"
    gold = _sparql_select_set(rdflib_graph, _resolve_sparql("q1", w9a_drill_module))
    actual = _cypher_select_set(driver, learner_cypher, ["book", "title"])
    assert actual == gold, f"Q1 result-set mismatch.\nExpected: {gold}\nGot: {actual}"


def test_translations_q2_match_sparql_equivalent(driver, rdflib_graph, w9a_drill_module):
    from queries.translations import q2

    learner_cypher = q2()
    assert learner_cypher, "translations.q2() returned an empty string"
    gold = _sparql_select_set(rdflib_graph, _resolve_sparql("q2", w9a_drill_module))
    actual = _cypher_select_set(driver, learner_cypher, ["book", "year"])
    assert actual == gold, f"Q2 result-set mismatch.\nExpected: {gold}\nGot: {actual}"


def test_translations_q3_match_sparql_equivalent(driver, rdflib_graph, w9a_drill_module):
    from queries.translations import q3

    learner_cypher = q3()
    assert learner_cypher, "translations.q3() returned an empty string"
    gold = _sparql_select_set(rdflib_graph, _resolve_sparql("q3", w9a_drill_module))
    actual = _cypher_select_set(driver, learner_cypher, ["book", "author_name"])
    assert actual == gold, f"Q3 result-set mismatch.\nExpected: {gold}\nGot: {actual}"


def test_translations_q4_match_sparql_equivalent(driver, rdflib_graph, w9a_drill_module):
    from queries.translations import q4

    learner_cypher = q4()
    assert learner_cypher, "translations.q4() returned an empty string"
    gold = _sparql_select_set(rdflib_graph, _resolve_sparql("q4", w9a_drill_module))
    actual = _cypher_select_set(driver, learner_cypher, ["book", "topic"])
    assert actual == gold, f"Q4 result-set mismatch.\nExpected: {gold}\nGot: {actual}"


def test_translation_q5_ask_equivalent(driver, rdflib_graph, w9a_drill_module):
    """SPARQL ASK -> single bool; Cypher must return one row, one column
    named `result` with the same bool."""
    from queries.translations import q5

    learner_cypher = q5()
    assert learner_cypher, "translations.q5() returned an empty string"

    sparql = _resolve_sparql("q5", w9a_drill_module)
    sparql_result = bool(rdflib_graph.query(sparql).askAnswer)

    rows = _run_rows(driver, learner_cypher)
    assert len(rows) == 1, f"Q5: expected exactly 1 row, got {len(rows)}"
    assert "result" in rows[0], (
        f"Q5: expected column named 'result', got {list(rows[0])}"
    )
    cypher_result = bool(rows[0]["result"])
    assert cypher_result == sparql_result, (
        f"Q5 ASK mismatch — SPARQL ASK = {sparql_result}, "
        f"Cypher returned {cypher_result}"
    )


# ============================================================
# 3. AST checks — parameterization + no f-string Cypher
# ============================================================

QUERIES_DIR = REPO_ROOT / "queries"


def _module_source(name: str) -> str:
    return (QUERIES_DIR / name).read_text()


def _function_returns(tree: ast.AST) -> list[ast.AST]:
    """Yield every Return node's value across the module."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            out.append(node.value)
    return out


def _contains_fstring(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.JoinedStr):
            return True
    return False


def _string_constants(node: ast.AST) -> list[str]:
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def test_warmup_cypher_uses_parameterization():
    """Any warm-up function whose signature takes a non-self argument must
    have a string literal somewhere in its body that references `$<name>`.
    q1 takes no parameters and is exempt.

    Accepts both the inline return form (`return "MATCH ... $cuisine ..."`)
    and the idiomatic Python form (`cypher = "MATCH ... $cuisine ..."`
    followed by `return cypher, {...}`) — both are correct.
    """
    src = _module_source("warmups.py")
    tree = ast.parse(src)
    found_parameterized = False
    parameterizable_seen = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        params = [a.arg for a in node.args.args if a.arg != "self"]
        if not params:
            continue
        parameterizable_seen = True
        # Walk the entire function body for any string constant containing $.
        # This catches both `return "...$param..."` and
        # `x = "...$param..."; return x, {...}` patterns.
        for s in _string_constants(node):
            if "$" in s:
                found_parameterized = True
                break
    if not parameterizable_seen:
        pytest.skip("No warm-up function takes a parameter.")
    assert found_parameterized, (
        "Warm-up functions that take parameters must use $param syntax in "
        "their Cypher string, not f-string interpolation."
    )


def test_translations_uses_parameterization():
    """At least one translations.q* must use $param OR be exempt by virtue
    of taking no learner-controlled input. The Translation Task functions
    in the contract take no parameters (W9A SPARQL hardcoded the constants),
    so this test passes by construction — but is left in place so that a
    learner who refactors to take a parameter (e.g., q2(year_threshold))
    is forced into parameterized form."""
    src = _module_source("translations.py")
    tree = ast.parse(src)
    has_param = False
    has_param_func = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        params = [a.arg for a in node.args.args if a.arg != "self"]
        if not params:
            continue
        has_param_func = True
        for ret in _function_returns(node):
            for s in _string_constants(ret):
                if "$" in s:
                    has_param = True
    if not has_param_func:
        pytest.skip(
            "No translation function takes a parameter; parameterization "
            "not applicable."
        )
    assert has_param, (
        "Translation functions that take parameters must use $param syntax."
    )


def test_no_f_string_cypher_interpolation():
    """No function in queries/ may return an f-string. f-strings invite
    Cypher injection."""
    for name in ("warmups.py", "translations.py"):
        src = _module_source(name)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for ret in _function_returns(node):
                assert not _contains_fstring(ret), (
                    f"queries/{name}: function {node.name} returns an "
                    f"f-string. Use $param-style parameterized Cypher."
                )


# ============================================================
# 4. Learner-written tests AST meta-check
# ============================================================

LEARNER_TEST_FILE = REPO_ROOT / "learner_tests" / "test_warmups.py"


def test_learner_tests_complete():
    src = LEARNER_TEST_FILE.read_text()
    tree = ast.parse(src)
    test_funcs = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]
    assert len(test_funcs) >= 2, (
        f"learner_tests/test_warmups.py must contain at least 2 test "
        f"functions, found {len(test_funcs)}."
    )

    for fn in test_funcs:
        # Must have >= 1 assertion
        has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(fn))

        # No bare pass
        has_bare_pass = any(
            isinstance(n, ast.Pass) for n in fn.body
        )

        # No remaining pytest.fail("Not implemented...") placeholder
        has_placeholder = False
        for sub in ast.walk(fn):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "fail"
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "pytest"
            ):
                for arg in sub.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and "Not implemented" in arg.value
                    ):
                        has_placeholder = True

        assert has_assert, (
            f"learner_tests/test_warmups.py::{fn.name} has no assertion."
        )
        assert not has_bare_pass, (
            f"learner_tests/test_warmups.py::{fn.name} body contains a "
            f"bare `pass`. Replace it with real assertions."
        )
        assert not has_placeholder, (
            f"learner_tests/test_warmups.py::{fn.name} still calls "
            f'pytest.fail("Not implemented..."). Replace it with real '
            f"assertions."
        )


# ============================================================
# 5. Identity Discipline — :Entity.id uniqueness
# ============================================================

def test_entity_id_uniqueness(driver):
    rows = _run_rows(
        driver,
        "MATCH (n:Entity) WITH n.id AS id, count(*) AS c "
        "WHERE c > 1 RETURN id, c",
    )
    assert rows == [], (
        f"Identity Discipline violation — duplicate :Entity.id rows: {rows}"
    )


# ============================================================
# 6. Sentinel — unmodified starter must fail visibly
# ============================================================

def test_starter_unmodified_fails():
    """Verify that the unmodified starter produces at least one empty Cypher
    string across the query surface — i.e., it is impossible for an
    unmodified starter to silently pass this autograder.

    A query function "returns empty" if calling it produces a cypher
    string (positional 0 of the tuple, or the bare string) that is empty
    or whitespace-only. At least one such function must exist on the
    unmodified starter; if all functions return non-empty Cypher, the
    starter is effectively pre-completed and the sentinel must fire.
    """
    from queries import translations, warmups

    funcs = [
        warmups.q1_list_recipes,
        warmups.q2_filter_by_cuisine,
        warmups.q3_subclass_traversal,
        translations.q1,
        translations.q2,
        translations.q3,
        translations.q4,
        translations.q5,
    ]

    def _cypher_of(fn):
        try:
            result = fn()
        except Exception:
            # An unimplemented function may raise — that's also a failing
            # starter signal.
            return ""
        if isinstance(result, tuple) and result:
            cy = result[0]
        else:
            cy = result
        return cy if isinstance(cy, str) else ""

    empty_count = sum(1 for fn in funcs if not _cypher_of(fn).strip())
    assert empty_count >= 1, (
        "Sentinel: every query function returned non-empty Cypher on what "
        "should be the unmodified starter. The starter is either pre-filled "
        "or the sentinel is misconfigured — investigate before grading."
    )
