"""Per-stub semantic pipeline (graph edges only, cluster-independent)."""



from __future__ import annotations



from typing import Any



import networkx as nx



from stage4.config import Stage4Config
from step3B.residual_graph import (

  EDGE_CORRIDOR_STUB_PARALLEL,

  EDGE_STUB_STUB_PARALLEL,

  EDGE_STUB_STUB_TOUCH,

)



SEM_NICHE = "NICHE"

SEM_POSSIBLE_CORRIDOR_WALL = "POSSIBLE_CORRIDOR_WALL"

SEM_AUXILIARY_CORRIDOR = "AUXILIARY_CORRIDOR"

SEM_UNCLASSIFIED = "UNCLASSIFIED"



DETAIL_BY_SEMANTIC = {

  SEM_NICHE: "niche",

  SEM_POSSIBLE_CORRIDOR_WALL: "possible_corridor_wall",

  SEM_AUXILIARY_CORRIDOR: "auxiliary_corridor",

  SEM_UNCLASSIFIED: "unknown",

}



SRC_NICHE = "niche_shape"

SRC_POSSIBLE_WALL = "corridor_stub_parallel_wall"

SRC_AUXILIARY = "crossbar_shape"

SRC_UNCLASSIFIED = "unclassified"





def _stub_ids(graph: nx.Graph) -> list[str]:

  return sorted(

    str(nid)

    for nid, data in graph.nodes(data=True)

    if data.get("node_type") == "stub"

  )





def _edge_kind(graph: nx.Graph, a: str, b: str) -> str:

  if not graph.has_edge(a, b):

    return ""

  return str(graph[a][b].get("edge_kind", ""))





def _stub_touch(graph: nx.Graph, a: str, b: str) -> bool:

  return _edge_kind(graph, a, b) == EDGE_STUB_STUB_TOUCH





def _stub_length(graph: nx.Graph, handle: str) -> float:

  return float(graph.nodes[str(handle)].get("length", 0.0))





def _pair_width(edge_width: float, fallback_width: float) -> float:

  if edge_width > 0.0:

    return edge_width

  return fallback_width





def _is_long_parallel_leg(

  length: float,

  width: float,

  *,

  parallel_length_scale: float,

  length_tol: float,

) -> bool:

  """Leg length at least ``parallel_length_scale ×`` parallel spacing."""

  if width <= 0.0:

    return False

  return length + length_tol >= parallel_length_scale * width





def _both_long_parallel_legs(

  graph: nx.Graph,

  leg_a: str,

  leg_c: str,

  width: float,

  *,

  parallel_length_scale: float,

  length_tol: float,

) -> bool:

  len_a = _stub_length(graph, leg_a)

  len_c = _stub_length(graph, leg_c)

  return (

    _is_long_parallel_leg(

      len_a, width,
      parallel_length_scale=parallel_length_scale,
      length_tol=length_tol,

    )

    and _is_long_parallel_leg(

      len_c, width,
      parallel_length_scale=parallel_length_scale,
      length_tol=length_tol,

    )

  )





def _parallel_stub_pairs(graph: nx.Graph, pool: set[str]) -> list[tuple[str, str, float]]:

  seen: set[tuple[str, str]] = set()

  pairs: list[tuple[str, str, float]] = []

  for u, v, data in graph.edges(data=True):

    if str(data.get("edge_kind", "")) != EDGE_STUB_STUB_PARALLEL:

      continue

    su, sv = str(u), str(v)

    if su not in pool or sv not in pool:

      continue

    key = tuple(sorted((su, sv)))

    if key in seen:

      continue

    seen.add(key)

    pairs.append((su, sv, float(data.get("width") or 0.0)))

  return pairs





def _find_niche_triples(

  graph: nx.Graph,

  pool: set[str],

  *,

  parallel_length_scale: float,

  fallback_width: float,

  length_tol: float,

) -> list[dict[str, Any]]:

  """Parallel outer legs with a touch chain; exclude long crossbar leg pairs."""

  found: list[dict[str, Any]] = []

  used_keys: set[tuple[str, ...]] = set()



  for leg_a, leg_c, edge_width in _parallel_stub_pairs(graph, pool):

    width = _pair_width(edge_width, fallback_width)

    if _both_long_parallel_legs(

      graph, leg_a, leg_c, width,

      parallel_length_scale=parallel_length_scale,
      length_tol=length_tol,

    ):

      continue



    for mid in pool:

      if mid in (leg_a, leg_c):

        continue

      if not (_stub_touch(graph, leg_a, mid) and _stub_touch(graph, mid, leg_c)):

        continue

      chain = (leg_a, mid, leg_c)

      if chain in used_keys:

        continue

      used_keys.add(chain)

      found.append({

        "niche_chain": [leg_a, mid, leg_c],

        "parallel_pair": [leg_a, leg_c],

        "parallel_width": round(width, 4),

      })

  return found





def _find_crossbar_pairs(

  graph: nx.Graph,

  pool: set[str],

  *,

  parallel_length_scale: float,

  fallback_width: float,

  length_tol: float,

) -> list[dict[str, Any]]:

  """Parallel stub pair whose both legs meet the long-leg threshold."""

  found: list[dict[str, Any]] = []

  used: set[tuple[str, str]] = set()

  for leg_a, leg_c, edge_width in _parallel_stub_pairs(graph, pool):

    width = _pair_width(edge_width, fallback_width)

    if not _both_long_parallel_legs(

      graph, leg_a, leg_c, width,

      parallel_length_scale=parallel_length_scale,
      length_tol=length_tol,

    ):

      continue

    key = tuple(sorted((leg_a, leg_c)))

    if key in used:

      continue

    used.add(key)

    found.append({

      "parallel_pair": [leg_a, leg_c],

      "parallel_width": round(width, 4),

    })

  return found





def _is_collinear_with_known_wall(graph: nx.Graph, stub_id: str) -> bool:

  """``corridor-stub-parallel`` to an existing ``node_type == wall`` segment."""

  sid = str(stub_id)

  if not graph.has_node(sid):

    return False

  for nb, data in graph[sid].items():

    if str(data.get("edge_kind", "")) != EDGE_CORRIDOR_STUB_PARALLEL:

      continue

    if graph.nodes.get(nb, {}).get("node_type") == "wall":

      return True

  return False





def _label_record(

  semantic: str,

  *,

  source: str,

  cfg: Stage4Config,

  confidence: float | None = None,

  niche_chain: list[str] | None = None,

  parallel_pair: list[str] | None = None,

  parallel_width: float | None = None,

  reason: str | None = None,

) -> dict[str, Any]:

  return {

    "region_semantic": semantic,

    "detail_type": DETAIL_BY_SEMANTIC[semantic],

    "classification_source": source,

    "semantic_confidence": (
      cfg.default_confidence if confidence is None else confidence
    ),

    "niche_chain": niche_chain,

    "parallel_pair": parallel_pair,

    "parallel_width": parallel_width,

    "shape": (

      "niche" if semantic == SEM_NICHE

      else "crossbar" if semantic == SEM_AUXILIARY_CORRIDOR

      else None

    ),

    "guard_reason": reason,

  }





def classify_all_stubs(

  residual_graph: nx.Graph,

  *,

  median_corridor_width: float,

  cfg: Stage4Config | None = None,

) -> dict[str, dict[str, Any]]:

  """

  Global stub pipeline (cluster-independent):



  1. NICHE — touch chain stub1—stub2—stub3 with stub1 ∥ stub3

  2. POSSIBLE_CORRIDOR_WALL — corridor-stub-parallel to known wall

  3. AUXILIARY_CORRIDOR — parallel pair, both legs ≥ scale × pair width

  4. UNCLASSIFIED



  Long/short leg checks use ``stub-stub-parallel`` edge width, not global median.

  """

  cfg = cfg or Stage4Config()

  fallback_w = float(median_corridor_width)

  remaining = set(_stub_ids(residual_graph))

  labels: dict[str, dict[str, Any]] = {}



  for niche in _find_niche_triples(

    residual_graph,

    remaining,

    parallel_length_scale=cfg.parallel_length_scale,

    fallback_width=fallback_w,

    length_tol=cfg.length_tol,

  ):

    chain = [str(h) for h in niche["niche_chain"]]

    if any(h not in remaining for h in chain):

      continue

    rec = _label_record(

      SEM_NICHE,

      source=SRC_NICHE,

      cfg=cfg,

      niche_chain=chain,

      parallel_pair=list(niche["parallel_pair"]),

      parallel_width=niche.get("parallel_width"),

      reason="niche_touch_chain_parallel_legs",

    )

    for handle in chain:

      labels[handle] = {**rec, "shape_handles": chain}

      remaining.discard(handle)



  for handle in sorted(remaining):

    if _is_collinear_with_known_wall(residual_graph, handle):

      labels[handle] = {

        **_label_record(

          SEM_POSSIBLE_CORRIDOR_WALL,

          source=SRC_POSSIBLE_WALL,

          cfg=cfg,

          reason="corridor_stub_parallel_to_wall",

        ),

        "shape_handles": [handle],

      }

      remaining.discard(handle)



  for crossbar in _find_crossbar_pairs(

    residual_graph,

    remaining,

    parallel_length_scale=cfg.parallel_length_scale,

    fallback_width=fallback_w,

    length_tol=cfg.length_tol,

  ):

    pair = [str(h) for h in crossbar["parallel_pair"]]

    if any(h not in remaining for h in pair):

      continue

    rec = _label_record(

      SEM_AUXILIARY_CORRIDOR,

      source=SRC_AUXILIARY,

      cfg=cfg,

      parallel_pair=pair,

      parallel_width=crossbar.get("parallel_width"),

      reason="crossbar_parallel_legs_long",

    )

    for handle in pair:

      labels[handle] = {**rec, "shape_handles": pair}

      remaining.discard(handle)



  for handle in sorted(remaining):

    labels[handle] = {

      **_label_record(

        SEM_UNCLASSIFIED,

        source=SRC_UNCLASSIFIED,

        cfg=cfg,

        confidence=cfg.unclassified_confidence,

        reason="no_rule_matched",

      ),

      "shape_handles": [],

    }



  return labels


