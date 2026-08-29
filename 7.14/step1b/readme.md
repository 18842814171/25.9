# 第一阶段乙：结构图与标注组融合

本目录将几何结构图与第一阶段甲产出的最终组图关联，得到带标注的结构图。结构图路径须在命令行用参数显式指定，代码内不写跨目录默认路径。阈值只在 [`config.py`](config.py) 中配置。总体进度见 [`docs/01-architecture.md`](../docs/01-architecture.md)。

## 输入与输出

| 角色 | 说明 |
|------|------|
| 结构图 | 由调用方传入二进制图文件路径（例如几何流水线产出的巷道结构图） |
| 最终组图 | 默认读取 `step1a/output/{图号}-final_cluster.pkl`；可用参数覆盖 |
| 产物 | `step1b/output/{图号}-structure_graph_with_texts` 的二进制图、可读摘要与核对图 |

按《重要原则》第 7 条，完整步骤宜只输入一个逻辑拓扑图。本步当前同时读入结构图与最终组图，与该条尚有差距。

## `build_fusion.py`（融合核心，非 CLI）

本文件是关联逻辑库，**不能**直接 `python step1b/build_fusion.py`。命令行入口是 `0_structure_graph_with_texts.py`，它读入结构图与最终组图后调用本库，再写出产物。

| 符号 | 作用 |
|------|------|
| `build_structure_graph_with_texts(structure, clusters, cfg)` | 深拷贝结构图；把组节点与未入组文字挂到最近中心线；写回 `attach_threshold` / `attach_summary` |
| `collect_isolated_text_nodes(clusters, cfg)` | 收集最终组图中未入组的 `TEXT`/`MTEXT`，一律当作巷道名称候选 |

关联行为要点：

- 仅向配置中的中心线角色关联（默认 `corridor`、`auxiliary`）。
- 关联距离阈值由候选点到最近中心线距离的统计量推断（分位数、离群上界、回退倍数见 `config.py`）。
- 组与成员以 `member` 边相连；挂到中心线的边为 `on-centerline`。
- 超出阈值或缺少坐标的节点记入 `attach_summary.skipped`，不删节点。

在代码中调用示例：

```python
from build_fusion import build_structure_graph_with_texts
from config import Step1bConfig
from graph_io import load_graph

cfg = Step1bConfig()
structure = load_graph("2026.1-1part-巷道_structure_graph.pkl")
clusters = load_graph("step1a/output/2026.1-1part-final_cluster.pkl")
fused = build_structure_graph_with_texts(structure, clusters, cfg)
```

日常跑图请用脚本 0（工作目录为仓库根目录），参数会落到本库：

```text
python step1b/0_structure_graph_with_texts.py ^
  --stem 2026.1-1part ^
  --structure-pkl "2026.1-1part-巷道_structure_graph.pkl"

# 覆盖最终组路径或产物目录
python step1b/0_structure_graph_with_texts.py ^
  --stem 2026.1-1part ^
  --structure-pkl "2026.1-1part-巷道_structure_graph.pkl" ^
  --clusters-pkl "step1a/output/2026.1-1part-final_cluster.pkl" ^
  --output-dir path/to/714-stage1
```

| 参数 | 说明 |
|------|------|
| `--structure-pkl` | 必填；结构图 `.pkl`，无跨目录默认路径 |
| `--clusters-pkl` | 可选；最终组图路径。省略时读 `step1a/output/{stem}-final_cluster.pkl` |
| `--step1a-output-dir` | 可选；未指定 `--clusters-pkl` 时，在该目录下找最终组图 |
| `--output-dir` | 可选；产物目录，默认 `step1b/output` |

## 已运行命令

对应已落盘的带标注结构图（工作目录为仓库根目录）：

```text
python step1b/0_structure_graph_with_texts.py --stem 2026.1-1 --structure-pkl "2026.1-1-巷道_structure_graph.pkl"
python step1b/1_visualize.py --stem 2026.1-1

python step1b/0_structure_graph_with_texts.py --stem 2026.1-1part --structure-pkl "2026.1-1part-巷道_structure_graph.pkl"
python step1b/1_visualize.py --stem 2026.1-1part
```

## 实现进度

| 图号 | 产物 | 状态 |
|------|------|------|
| `2026.1-1` | 带标注结构图（二进制与可读摘要） | 已落盘 |
| `2026.1-1part` | 带标注结构图及核对图 | 已落盘 |

本步不重新分类测点与钻孔，只做空间关联；未入组文字一律视为巷道名称并尝试关联。关联距离由候选点到最近中心线距离的统计量推断（分位数、离群上界、回退倍数等均在顶层配置）。
