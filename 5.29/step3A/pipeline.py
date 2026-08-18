"""Step 3A pipeline: wall pairs → candidates → centerline graph."""

from __future__ import annotations

from pathlib import Path

from stage2.io import graph_to_read_json, load_graph, load_json, save_graph, save_json
from step2B.paths import parallel_graph_pkl, straight_wall_geometry_json, step2b_output_dir
from step3A.centerline_graph import (
  build_centerline_graph,
  centerline_graph_summary,
  parallel_centerline_groups,
)
from step3A.config import CenterlineGraphConfig
from step3A.corridor_candidate import (
  build_candidates_from_pairs,
  candidates_to_json,
  deduplicate_candidates,
  wall_index_from_geometry,
)
from step3A.global_scale import compute_global_scale
from step3A.paths import (
  centerline_graph_json,
  centerline_graph_pkl,
  centerline_graph_summary_json,
  corridor_candidates_json,
  corridor_centerlines_png,
  step3a_output_dir,
)
from step3A.visualize import visualize_corridor_centerlines
from step3A.wall_pair import extract_wall_pairs


def run_corridor_candidates(
  stem: str,
  *,
  step2b_dir: Path | None = None,
  output_dir: Path | None = None,
  vis: bool = True,
  show_ids: bool = False,
) -> dict:
  step2b = step2b_output_dir(step2b_dir)
  out = step3a_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)

  walls_path = straight_wall_geometry_json(stem, step2b)
  graph_path = parallel_graph_pkl(stem, step2b)
  if not walls_path.is_file():
    raise FileNotFoundError(
      f"Missing {walls_path}; run step2B/run_straight_wall.py first.",
    )
  if not graph_path.is_file():
    raise FileNotFoundError(
      f"Missing {graph_path}; run step2B/build_parallel_graph.py first.",
    )

  wall_doc = load_json(walls_path)
  graph = load_graph(graph_path)
  wall_index = wall_index_from_geometry(wall_doc)

  pairs = extract_wall_pairs(graph)
  candidates = build_candidates_from_pairs(pairs, wall_index)
  candidates = deduplicate_candidates(candidates)
  scale = compute_global_scale(candidates)

  json_path = corridor_candidates_json(stem, out)
  save_json(
    candidates_to_json(candidates, source_stem=stem, global_scale=scale),
    json_path,
  )

  paths: dict[str, Path | None] = {"corridor_candidates_json": json_path}
  if vis:
    center_png = corridor_centerlines_png(stem, out, label=show_ids)
    cand_doc = candidates_to_json(candidates, source_stem=stem, global_scale=scale)
    visualize_corridor_centerlines(
      cand_doc,
      center_png,
      wall_doc=wall_doc,
      show_ids=show_ids,
      title=f"Step 3A corridor centerlines, n={len(candidates)}",
    )
    paths["corridor_centerlines_png"] = center_png

  return {
    "pair_count": len(pairs),
    "candidate_count": len(candidates),
    "candidates": candidates,
    "global_scale": scale,
    "wall_doc": wall_doc,
    "paths": paths,
  }


def run_centerline_graph(
  stem: str,
  *,
  output_dir: Path | None = None,
  cfg: CenterlineGraphConfig | None = None,
  candidates: list[dict] | None = None,
  global_scale: dict[str, float] | None = None,
  auto_scale: bool = True,
  vis: bool = True,
  show_ids: bool = False,
) -> dict:
  out = step3a_output_dir(output_dir)
  out.mkdir(parents=True, exist_ok=True)
  cfg = cfg or CenterlineGraphConfig.from_pipeline()

  if candidates is None:
    json_path = corridor_candidates_json(stem, out)
    if not json_path.is_file():
      raise FileNotFoundError(
        f"Missing {json_path}; run step3A/run_corridor_candidates.py first.",
      )
    doc = load_json(json_path)
    candidates = list(doc.get("candidates") or [])
    if global_scale is None:
      global_scale = doc.get("global_scale")

  if global_scale is None:
    global_scale = compute_global_scale(candidates)

  if auto_scale:
    cfg.apply_global_scale(global_scale)

  graph = build_centerline_graph(candidates, cfg)
  groups = parallel_centerline_groups(graph)
  graph.graph["parallel_groups"] = groups
  graph.graph["global_scale"] = global_scale

  pkl_path = centerline_graph_pkl(stem, out)
  json_path = centerline_graph_json(stem, out)
  summary_path = centerline_graph_summary_json(stem, out)
  save_graph(graph, pkl_path)
  save_json(graph_to_read_json(graph), json_path)
  summary_doc = centerline_graph_summary(
    graph,
    source_stem=stem,
    cfg=cfg,
    median_corridor_width=global_scale.get("median_corridor_width"),
  )
  save_json(summary_doc, summary_path)

  paths: dict[str, Path | None] = {
    "centerline_graph_pkl": pkl_path,
    "centerline_graph_json": json_path,
    "centerline_graph_summary_json": summary_path,
  }

  return {
    "corridor_count": graph.number_of_nodes(),
    "edge_count": graph.number_of_edges(),
    "endpoint_edge_count": summary_doc["endpoint_edge_count"],
    "parallel_edge_count": summary_doc["parallel_edge_count"],
    "parallel_group_count": len(groups),
    "global_scale": global_scale,
    "paths": paths,
  }


def run_step3a(
  stem: str,
  *,
  step2b_dir: Path | None = None,
  output_dir: Path | None = None,
  auto_scale: bool = True,
  vis: bool = True,
  show_ids: bool = False,
) -> dict:
  cand_result = run_corridor_candidates(
    stem,
    step2b_dir=step2b_dir,
    output_dir=output_dir,
    vis=vis,
    show_ids=show_ids,
  )
  cl_graph_result = run_centerline_graph(
    stem,
    output_dir=output_dir,
    candidates=cand_result["candidates"],
    global_scale=cand_result["global_scale"],
    auto_scale=auto_scale,
    vis=vis,
    show_ids=show_ids,
  )
  return {
    "pair_count": cand_result["pair_count"],
    "candidate_count": cand_result["candidate_count"],
    "centerline_graph_edges": cl_graph_result["edge_count"],
    "global_scale": cl_graph_result["global_scale"],
    "paths": {**cand_result["paths"], **cl_graph_result["paths"]},
  }
