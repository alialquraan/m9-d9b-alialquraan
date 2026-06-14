"""Learner-written tests for queries/warmups.py.

You write at least 2 tests here. The autograder verifies each test
function contains at least one assertion and is not left as the
placeholder `pytest.fail("Not implemented")`.

A driver fixture (`driver`) is provided via conftest.py — it points at
the same Neo4j instance the autograder uses, with the drill fixtures
already loaded. Run a Cypher string in a session like:

    with driver.session() as session:
        rows = list(session.run(cypher_str, params))

Test ideas:
  - Confirm `q1_list_recipes()` returns exactly the 5 recipe names you
    expect from `recipes_mini.cypher`.
  - Confirm `q2_filter_by_cuisine("Italian")` returns the two Italian
    recipes only — no Chinese or Sichuan recipes.
  - Confirm `q3_subclass_traversal("Chinese")` includes Sichuan recipes
    (via :SUBCLASS_OF) but `q2_filter_by_cuisine("Chinese")` does not.
"""

import pytest

from queries.warmups import q1_list_recipes, q2_filter_by_cuisine, q3_subclass_traversal


def test_q1_list_recipes_returns_all_five(driver):
    """Replace this body with your own assertion(s)."""
    cypher = q1_list_recipes()

    with driver.session() as session:
        rows = list(session.run(cypher))

    assert len(rows) == 5


def test_q3_traversal_picks_up_subclasses(driver):
    """Replace this body with your own assertion(s)."""
    cypher = q3_subclass_traversal("Chinese")

    with driver.session() as session:
        rows = list(session.run(cypher))

    assert len(rows) > 0