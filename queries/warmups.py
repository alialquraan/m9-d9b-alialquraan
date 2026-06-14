"""Cypher warm-ups against the M9B recipe vocabulary.

Each function returns a Cypher query **string** (and, where indicated, a
parameter dict). The autograder runs them against `recipes_mini.cypher`
and compares row sets against gold.

Use parameterized Cypher (`$param`) whenever a value comes from outside
the query. Do not interpolate user-supplied values into the query text.
"""


def q1_list_recipes() -> str:
    """Q1 — Return every recipe in the graph by name.

    Result-set shape: rows with a single column named `name`. One row per
    :Recipe node. Order is not asserted.
    """
    # TODO: Return a Cypher string that matches every :Recipe and returns
    #       its name column.
    return """
    MATCH (r:Recipe)
    RETURN r.name AS name
    """


def q2_filter_by_cuisine(cuisine_name: str) -> tuple[str, dict]:
    """Q2 — Return recipe names whose direct cuisine matches `cuisine_name`.

    Result-set shape: rows with a single column `name`. Match the cuisine
    on its `name` property; no hierarchy traversal in this warm-up.

    Returns: (cypher_string, params_dict). Use $cuisine in the Cypher.
    """
    # TODO: Build a parameterized Cypher that joins :Recipe to :Cuisine via
    #       :OF_CUISINE and filters Cuisine.name to the $cuisine parameter.
    #       Return the query and {"cuisine": cuisine_name} together.
    query = """
    MATCH (r:Recipe)-[:OF_CUISINE]->(c:Cuisine {name: $cuisine})
    RETURN r.name AS name
    """
    
    params = {
        "cuisine": cuisine_name
    }

    return query, params


def q3_subclass_traversal(cuisine_name: str) -> tuple[str, dict]:
    """Q3 — Return recipe names whose cuisine equals `cuisine_name` OR is a
    descendant of it via the :SUBCLASS_OF hierarchy.

    Example: cuisine_name="Chinese" should also pick up recipes tagged
    :Sichuan (because Sichuan -[:SUBCLASS_OF]-> Chinese).

    Result-set shape: rows with a single column `name`.

    Returns: (cypher_string, params_dict). Use $cuisine in the Cypher.
    """
    # TODO: Use [:SUBCLASS_OF*0..] so a recipe's direct cuisine OR any
    #       ancestor cuisine can match the $cuisine parameter.
    query = """
    MATCH (r:Recipe)-[:OF_CUISINE]->(:Cuisine)-[:SUBCLASS_OF*0..]->(:Cuisine {name: $cuisine})
    RETURN r.name AS name
    """
    
    params = {
        "cuisine": cuisine_name
    }

    return query, params
