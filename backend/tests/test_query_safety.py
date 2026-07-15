"""Read-only guards for generated graph queries (anti-hallucination /
anti-injection defence in depth): Cypher write/admin denylist and Gremlin
lambda/closure rejection."""
import pytest

from app.clients.graph_gremlin import GremlinGraphStore
from app.services.text_to_cypher import UnsafeQueryError, assert_read_only


# -- Cypher ---------------------------------------------------------------
@pytest.mark.parametrize(
    "cypher",
    [
        "CREATE (n:Process {code:'X'})",
        "MATCH (n) DETACH DELETE n",
        "MATCH (n) SET n.name = 'x'",
        "CALL db.labels()",
        "CALL dbms.components()",
        "CALL apoc.load.json('file:///etc/passwd')",
        "CALL apoc.periodic.iterate('MATCH (n) RETURN n', 'DELETE n', {})",
        "CALL apoc.cypher.run('MATCH (n) DELETE n', {})",
        "USING PERIODIC COMMIT LOAD CSV FROM 'x' AS row RETURN row",
    ],
)
def test_cypher_denylist_blocks_writes_and_admin(cypher):
    with pytest.raises(UnsafeQueryError):
        assert_read_only(cypher)


@pytest.mark.parametrize(
    "cypher",
    [
        "MATCH (p:Process {level:2}) RETURN p.code, p.name LIMIT 200",
        "MATCH (f:Process)-[:HAS_SUB_PROCESS*]->(c:Process) WHERE toLower(f.name)='finance' RETURN c LIMIT 50",
        "MATCH (p:Process {level:1}) RETURN apoc.convert.fromJsonMap(p.process_flow_json) LIMIT 1",
    ],
)
def test_cypher_denylist_allows_reads(cypher):
    assert_read_only(cypher)  # must not raise


# -- Gremlin ---------------------------------------------------------------
@pytest.mark.parametrize(
    "traversal",
    [
        "g.V().map{it.get().value('name')}",                 # closure
        "g.V().filter {true}.valueMap()",                    # closure
        "g.V().has('name','x').drop()",                      # mutation
        "g.V().addV('Process')",                             # mutation
        "g.V(); g.V().valueMap()",                           # multi-statement
        "g.V().property('name','x')",                        # mutation
        "g.V().has('a', lambda: it)",                        # lambda keyword
        "x.V().valueMap()",                                  # wrong root
        "g.V().inject('a').valueMap()",                      # inject
    ],
)
def test_gremlin_guard_blocks_unsafe(traversal):
    with pytest.raises(ValueError):
        GremlinGraphStore._assert_read_only(traversal)


@pytest.mark.parametrize(
    "traversal",
    [
        "g.V().has('name_lc','finance').repeat(out('HAS_SUB_PROCESS')).emit().has('level',2).valueMap('code','name','level')",
        "g.V().has('level',1).has('name_lc','procure to pay').values('process_flow_json')",
        "g.V().hasLabel('Process').count()",
    ],
)
def test_gremlin_guard_allows_read_traversals(traversal):
    GremlinGraphStore._assert_read_only(traversal)  # must not raise
