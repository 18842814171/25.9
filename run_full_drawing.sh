#!/usr/bin/env bash
# 整图专用计算流水线：不负责 DXF 提取、不输出核对 PNG。须事先导出 JSON，例如：
#   python batch_export_test_input.py --src 2026.1-1 --cfg test_input/2016_config.json --with-legend
# 局部图批处理见 run_stats.sh，二者严格分开。
#
# 用法：
#   ./run_full_drawing.sh --src 2026.1-1
#   ./run_full_drawing.sh --src 2026.1-2/2026.1-2
#   ./run_full_drawing.sh --src 2026.1-2/2026.1-2 --output-root /path/to/out
#
# --src：相对代码根目录的 DXF 路径（可带或不带 .dxf）；亦兼容 test_input/{图号}.dxf。
# 传给 Python 的仅为 --stem=图名（basename）。产物默认：{图号}_output/

set -euo pipefail

CODE_ROOT="$(cd "$(dirname "$0")" && pwd)"
TEST_INPUT="${CODE_ROOT}/test_input"
SRC=""
OUTPUT_ROOT=""

usage() {
  echo "Usage: ./run_full_drawing.sh --src <path> [--output-root DIR]"
  echo "Example: ./run_full_drawing.sh --src 2026.1-1"
  echo "Example: ./run_full_drawing.sh --src 2026.1-2/2026.1-2"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Missing value for --src"
        usage
        exit 1
      fi
      SRC="$2"
      shift 2
      ;;
    --output-root)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Missing value for --output-root"
        usage
        exit 1
      fi
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$SRC" ]]; then
  usage
  exit 1
fi

if [[ ! -d "$TEST_INPUT" ]]; then
  echo "Missing folder: ${TEST_INPUT}"
  exit 1
fi

REL="${SRC//\\//}"
REL="${REL%.dxf}"
REL="${REL%.DXF}"

DXF=""
if [[ -f "${CODE_ROOT}/${REL}.dxf" ]]; then
  DXF="${CODE_ROOT}/${REL}.dxf"
elif [[ -f "${CODE_ROOT}/${REL}.DXF" ]]; then
  DXF="${CODE_ROOT}/${REL}.DXF"
elif [[ -f "${TEST_INPUT}/${REL}.dxf" ]]; then
  DXF="${TEST_INPUT}/${REL}.dxf"
elif [[ -f "${TEST_INPUT}/${REL}.DXF" ]]; then
  DXF="${TEST_INPUT}/${REL}.DXF"
fi
if [[ -z "$DXF" ]]; then
  echo "Missing DXF: ${CODE_ROOT}/${REL}.dxf"
  echo "Also tried: ${TEST_INPUT}/${REL}.dxf"
  exit 1
fi

STEM="$(basename "$DXF")"
STEM="${STEM%.*}"

if [[ -z "$OUTPUT_ROOT" ]]; then
  OUT="${CODE_ROOT}/${STEM}_output"
else
  OUT="${OUTPUT_ROOT}/${STEM}_output"
fi

LEGEND_JSON="${TEST_INPUT}/${STEM}-图例.json"
GEO_JSON="${TEST_INPUT}/${STEM}-巷道.json"
TEXT_JSON="${TEST_INPUT}/${STEM}-文字.json"
FACILITY_JSON="${TEST_INPUT}/${STEM}-设施.json"

if [[ ! -f "$GEO_JSON" ]]; then
  echo "Missing ${GEO_JSON}"
  echo "Export first: python batch_export_test_input.py --src ${REL} --cfg <export-config.json> --with-legend"
  exit 1
fi
if [[ ! -f "$LEGEND_JSON" ]]; then
  echo "Missing legend JSON: ${LEGEND_JSON}"
  echo "Export first: python batch_export_test_input.py --src ${REL} --cfg <export-config.json> --with-legend"
  exit 1
fi

echo
echo "========== FULL DRAWING ${STEM} (${REL}) -> ${OUT} =========="

S529_2="${OUT}/529-stage2"
S2A_RAW="${S529_2}/step2A/raw"
S2A_OUT="${S529_2}/step2A/output"
S2B_OUT="${S529_2}/step2B/output"
S529_3="${OUT}/529-stage3"
S3A_OUT="${S529_3}/step3A/output"
S3B_OUT="${S529_3}/step3B/output"
S529_4="${OUT}/529-stage4"
S714_1="${OUT}/714-stage1"
S714_2="${OUT}/714-stage2"
STRUCTURE_PKL="${S529_4}/${STEM}_structure_graph.pkl"
TEXTS_PKL="${S714_1}/${STEM}-structure_graph_with_texts.pkl"

mkdir -p "$S2A_RAW" "$S2A_OUT" "$S2B_OUT" "$S3A_OUT" "$S3B_OUT" "$S529_4" "$S714_1" "$S714_2"

echo "[1/2] 5.29 geometry pipeline"
cd "${CODE_ROOT}/5.29"

python step2A/run_init_graph.py --geo "$GEO_JSON" --stem="$STEM" --raw "$S2A_RAW"
python step2A/square_bend.py --stem="$STEM" --raw "$S2A_RAW" --output "$S2A_OUT"
python step2A/arc_bend_detect.py --stem="$STEM" --raw "$S2A_RAW" --output "$S2A_OUT"
python step2A/arc_normalize.py --stem="$STEM" --raw "$S2A_RAW" --output "$S2A_OUT"
python step2A/merge_normalized_geometry.py --stem="$STEM" --output "$S2A_OUT"
python step2A/build_normalized_graph.py --stem="$STEM" --output "$S2A_OUT"
# 整图跳过核对位图（局部图 run_stats 仍出图）

python step2B/run_straight_wall.py --stem="$STEM" --step2a "$S2A_OUT" --output "$S2B_OUT" --no-vis
python step2B/build_parallel_graph.py --stem="$STEM" --step2a "$S2A_OUT" --output "$S2B_OUT" --no-vis

python step3A/run_corridor_candidates.py --stem="$STEM" --step2b "$S2B_OUT" --output "$S3A_OUT" --no-vis
python step3A/build_centerline_graph.py --stem="$STEM" --output "$S3A_OUT"

python step3B/build_residual_graph.py --stem="$STEM" --step2b "$S2B_OUT" --step2a "$S2A_OUT" --output "$S3B_OUT" --no-vis
python step3B/pick_corridor_wall_candidates.py --stem="$STEM" --centerline-dir "$S3A_OUT" --output "$S3B_OUT" --no-vis
python step3B/fix_centerlines.py --stem="$STEM" --centerline-dir "$S3A_OUT" --output "$S3B_OUT" --no-vis

python step4A/classify_attached_regions.py --stem="$STEM" --step3b "$S3B_OUT" --centerline "$S3A_OUT" --output "$S529_4" --no-vis
python step4B/build_corrected_centerlines.py --stem="$STEM" --step3b "$S3B_OUT" --step4A "$S529_4" --output "$S529_4" --no-vis

echo "[2/2] 7.14 annotation + facility (含整图专用：标注图例模板与识别规则)"
cd "${CODE_ROOT}/7.14"

python step1a/0_retrieved_elements_graph.py --stem="$STEM" --text-json "$TEXT_JSON" --corridor-json "$GEO_JSON" --output-dir "$S714_1" --no-png
python step1a/1_extract_retrieval_templates.py --stem="$STEM" --legend-json "$LEGEND_JSON" --output-dir "$S714_1"
python step1a/2_retrieval_rules.py --stem="$STEM" --output-dir "$S714_1"
python step1a/3_apply_retrieval_rules.py --stem="$STEM" --corridor-json "$GEO_JSON" --output-dir "$S714_1" --no-png
python step1a/4_final_clusters.py --stem="$STEM" --corridor-json "$GEO_JSON" --output-dir "$S714_1" --no-png

python step1b/0_structure_graph_with_texts.py --stem="$STEM" --structure-pkl "$STRUCTURE_PKL" --step1a-output-dir "$S714_1" --output-dir "$S714_1"

python stage2/0_facility_primitives_graph.py --stem="$STEM" --facility-json "$FACILITY_JSON" --output-dir "$S714_2"
python stage2/2_build_facility_graph.py --stem="$STEM" --output-dir "$S714_2"
python stage2/3_structure_graph_with_facilities.py --stem="$STEM" --structure-pkl "$TEXTS_PKL" --output-dir "$S714_2" --corridor-json "$GEO_JSON" --no-png

cd "${CODE_ROOT}"
python collect_pipeline_stats.py --stem="$STEM" --output-root "$OUT"

echo
echo "Full drawing finished: ${STEM}"
echo "Rules:     ${S714_1}/${STEM}-retrieval_rules.json"
echo "Next: ./run_stats.sh --src ${REL}"
