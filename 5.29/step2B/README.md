# Step 2B — 直墙识别与巷道配对

从 Step 2A 标准化结果中识别直墙段，建立直墙与残余线段的逻辑连接图，并完成平行墙配对与主巷道识别。

本步不负责洞室、横档、台阶、设备间等细节语义分类；上述图元在残余几何中保留，供后续步骤使用。

**状态：本步已完成。**

---

## 流水线

须按顺序分别运行三个脚本（禁止合并为总脚本）：

```text
run_straight_wall.py       # 共线直墙识别、几何合并、检查图
        ↓
build_parallel_graph.py    # 直墙与残余线段逻辑连接图、平行墙组检查图


### 运行示例（PowerShell）

```powershell
python step2B/run_straight_wall.py --stem $stem
python step2B/build_parallel_graph.py --stem $stem
python step2B/run_straight_wall.py --stem $stem --label
```

产物目录：`step2B/output/`。

---

## 1. 输入

### 1.1 直墙识别（来自 `step2A/output/`）

| 文件 | 说明 |
|------|------|
| `{stem}_normalized_geometry.json` | 标准化后的线段全集 |
| `{stem}_normalized_graph.pkl` | 端点邻接图 |

直墙合并**仅**读取邻接边上的 `endpoint_gap`、`angle_deg`，不读取独立折点标记文件。

| 条件 | 配置字段 | 默认值 | 含义 |
|------|----------|--------|------|
| 端点邻接 | `endpoint_link_gap`（Step 2A 构图） | `1.0` | 米；直墙合并不再单独设 gap |
| 近共线 | `continuity_angle_deg` | `5.0` | 度 |
| 横向偏移 | `continuity_lateral_tol` | `1.0` | 米 |

### 1.2 平行图与巷道（来自本步上一步产物）

| 文件 | 说明 |
|------|------|
| `{stem}_straight_wall_geometry.json` | 直墙合并几何 |
| `{stem}_residual_geometry.json` | 未归入直墙的残余线段 |

平行配对先以松半径建边，再按边宽中位数定巷道带宽并裁剪（见第 2 节）。

---

## 2. 阈值配置

统一入口：

```python
from stage2.geometry import CorridorPipelineConfig
from step2B.config import StraightWallConfig, ParallelGraphConfig, CorridorDetectConfig
```

| 配置类 | 用于 | 主要字段 |
|--------|------|----------|
| `StraightWallConfig` | 直墙共线合并 | `continuity_angle_deg`、`continuity_lateral_tol` |
| `ParallelGraphConfig` | 逻辑连接图 | `endpoint_link_gap`、`angle_th_deg`、`min_width`、`max_width`、`min_overlap_ratio` |


### 巷道宽度（平行边后置分位数）

`build_parallel_graph.py` 默认：

1. 用松搜索半径（默认 `probe_max_width=20`）按近平行 + 投影重叠建边；
2. 对已建平行边的间距取中位数 `median`；
3. 设 `min_width = median × 0.5`，`max_width = median × 1.6`，删掉带外过远/过近边。

不再做全图两两前置估宽。手动指定 `--min-width` / `--max-width` 或 `--no-auto-width` 时，直接用该带宽搜索，不做分位数裁剪。

---

## 3. `run_straight_wall.py`

**职责**：在 `normalized_graph` 上识别共线直墙链，合并几何，写出检查图。

直墙编号：`WS001`、`WS002`、…

### 输出

| 文件 | 说明 |
|------|------|
| `{stem}_wall_segment.json` | 直墙组（识别结果，含短段） |
| `{stem}_straight_wall_geometry.json` | 合并后直墙线段 |
| `{stem}_residual_geometry.json` | 残余线段 |
| `{stem}_straight_wall.png` | 检查图（彩色直墙、灰色残余；标注图元句柄） |

短单段是否写入直墙几何，由长度阈值判定（约为图幅估计巷道宽度的 5 倍）。

**前置条件**：Step 2A 已生成 `normalized_geometry.json`、`normalized_graph.pkl`。

---

## 4. `build_parallel_graph.py`

**职责**：在直墙与残余线段上建立逻辑连接图。

### 图结构

| 项目 | 说明 |
|------|------|
| 节点 `wall` | 直墙段，编号为 `WS***` |
| 节点 `stub` | 残余线段，编号为图元句柄 |
| 边 `endpoint` | 端点距离 ≤ `endpoint_link_gap` |
| 边 `is_parallel` | 两直墙平行、间距在带宽内、投影重叠 ≥ `min_overlap_ratio` |

端点邻接与平行关系保存在同一图中，边类型字段区分语义。

### 输出

| 文件 | 说明 |
|------|------|
| `{stem}_parallel_graph.pkl` | 逻辑连接图（管道输入） |
| `{stem}_parallel_graph.json` | 可读图结构 |
| `{stem}_parallel_graph_summary.json` | 平行墙组列表与统计 |
| `{stem}_parallel_graph.png` | 检查图：平行墙组各色、残余灰色、直墙标注 `WS***` |

**前置条件**：已运行 `run_straight_wall.py`。

---

## 6. 产物索引

```text
step2B/output/
├── {stem}_wall_segment.json
├── {stem}_straight_wall_geometry.json
├── {stem}_residual_geometry.json
├── {stem}_straight_wall.png
├── {stem}_parallel_graph.pkl
├── {stem}_parallel_graph.json
├── {stem}_parallel_graph_summary.json
├── {stem}_parallel_graph.png

```

---

## 7. 本步结束状态

```text
直墙几何（straight_wall_geometry.json）
+ 残余几何（residual_geometry.json）
+ 逻辑连接图（parallel_graph.pkl / .json / _summary.json）

```

下游 Step 3 可在此基础上开展细节识别，并将细节连接到巷道主线。

---

## 8. 代码模块

| 模块 | 作用 |
|------|------|
| `run_straight_wall.py` | 直墙识别与合并入口 |
| `straight_wall.py` | 共线链检测、几何分流 |
| `build_parallel_graph.py` | 逻辑连接图入口 |
| `parallel_graph.py` | 建图与平行墙组划分 |
| `width_estimate.py` | 按图幅估算巷道宽度带宽 |
| `config.py` | 阈值配置类 |
| `paths.py` | 产物路径 |
| `visualize.py` | 检查图 |

共享库：`stage2/geometry.py`、`stage2/io.py`、`stage2/graph_usage.py`。
