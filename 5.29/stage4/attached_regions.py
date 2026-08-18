"""Build semantic residual graph and attached-regions summary."""

from __future__ import annotations

from collections import Counter
from typing import Any

import networkx as nx

from stage4.config import Stage4Config
from stage4.residual_component import build_region_records, rc_v1_for_validation
from stage4.stub_classify import classify_all_stubs
from step3B.corridor_mapping import augment_corridor_mapping


def annotate_residual_graph_semantic(
  residual_graph: nx.Graph,
  *,
  cfg: Stage4Config | None = None,
  median_corridor_width: float | None = None,
) -> tuple[nx.Graph, list[dict[str, Any]]]:
  """
  Classify every stub via the global pipeline, then attach RC metadata.

  Pipeline order (cluster-independent): niche → possible wall → auxiliary
  corridor (crossbar) → unclassified.
  """
  cfg = cfg or Stage4Config()

  graph = residual_graph.copy()
  median_w = float(median_corridor_width or cfg.median_corridor_width or 0.0)
  stub_labels = classify_all_stubs(
    graph,
    median_corridor_width=median_w,
    cfg=cfg,
  )

  handle_to_rc: dict[str, str] = {}
  rc_by_id: dict[str, dict[str, Any]] = {}
  for region in build_region_records(graph):
    rc_id = str(region["rc_id"])
    rc_by_id[rc_id] = region
    for handle in region.get("handles") or []:
      handle_to_rc[str(handle)] = rc_id

  classified_stubs: list[dict[str, Any]] = []
  stub_semantics: list[str] = []

  for handle in sorted(stub_labels):
    label = stub_labels[handle]
    rc_id = handle_to_rc.get(handle, "")
    record = {
      "handle": handle,
      "rc_id": rc_id,
      **label,
    }
    classified_stubs.append(record)

    attrs = {
      **label,
      "rc_id": rc_id,
      "shape_member": bool(label.get("shape_handles")),
    }
    if graph.has_node(handle):
      graph.nodes[handle].update(attrs)
      stub_semantics.append(str(label["region_semantic"]))

  counts = Counter(stub_semantics)
  graph.graph["kind"] = "residual_graph_semantic"
  graph.graph["schema_version"] = 8
  graph.graph["semantic_counts"] = dict(sorted(counts.items()))
  graph.graph["rc_view_primary"] = "RC_v2"
  graph.graph["rc_v1_count"] = len(rc_v1_for_validation(graph))
  graph.graph["rc_v2_count"] = len(rc_by_id)
  graph.graph["stub_count"] = len(classified_stubs)
  return graph, classified_stubs


def attached_regions_summary(
  classified_stubs: list[dict[str, Any]],
  *,
  source_stem: str,
) -> dict[str, Any]:
  """JSON-serializable per-stub summary."""
  rows = sorted(classified_stubs, key=lambda r: str(r.get("handle", "")))
  counts = Counter(r["region_semantic"] for r in classified_stubs)
  return {
    "kind": "attached_regions_summary",
    "schema_version": 8,
    "source_stem": source_stem,
    "stub_count": len(rows),
    "semantic_counts": dict(sorted(counts.items())),
    "stubs": rows,
  }


def prepare_mapped_residual_graph(
  residual_graph: nx.Graph,
  cand_wall_to_id: dict[str, str],
) -> nx.Graph:
  """Ensure corridor-stub-touch edges carry corridor_id."""
  if residual_graph.graph.get("corridor_mapping_augmented"):
    return residual_graph
  return augment_corridor_mapping(residual_graph, cand_wall_to_id)
