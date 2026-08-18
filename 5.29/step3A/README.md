# Step 3A — 巷道候选线提取

> **输入**：直墙几何 + 平行逻辑图（来自 Step 2B）  
> **输出**：巷道候选列表 + 巷道候选网络  
> **不做**：主巷判断、横档/洞室等细节语义（留给 Step 3B）

---

## 1. 输入与输出

### 输入

| 文件 | 来源 | 说明 |
|------|------|------|
| `{stem}_straight_wall_geometry.json` | `step2B/output/` | 合并后的直墙段几何 |
| `{stem}_parallel_graph.pkl` | `step2B/output/` | 直墙与碎线的逻辑连接图 |
| `{stem}_parallel_graph_summary.json` | `step2B/output/` | 可选；平行墙组索引，仅用于搜索加速 |

### 输出

| 文件 | 说明 |
|------|------|
| `{stem}_corridor_candidates.json` | 巷道候选列表 |
| `{stem}_corridor_network.pkl` | 候选之间的延续/交叉网络 |
| `{stem}_global_scale.json` | 全图巷道宽度尺度与建网解析阈值 |

产物目录：`step3A/output/`。

---

## 2. Step 2B 上游回顾

### 2.1 图节点

直墙节点（`node_type == "wall"`）：

```python
{
    "node_id": "WS001",       # wall_segment_id
    "node_type": "wall",
    "start": [x, y],
    "end": [x, y],
    "length": ...,
    "direction": [dx, dy],
    "members": [...],         # 原始图元 handle 列表
}
```

碎线节点（`node_type == "stub"`）参与端点邻接，**不参与** Step 3A 候选生成。

### 2.2 图边

**端点邻接边**（本步不使用）：

```python
{
    "edge_kind": "endpoint",
    "endpoint_gap": ...,
    "angle_deg": ...,
    "is_parallel": bool,
    "is_ortho": bool,
}
```

**平行边**（本步输入来源）：

```python
{
    "edge_kind": "is_parallel",       # 或 "endpoint_parallel"
    "is_parallel": True,
    "width": 5.42,                    # 墙间距（米）
    "overlap_ratio": 0.92,            # 投影重叠比
    # endpoint_parallel 时还含 endpoint_gap、angle_deg
}
```

字段以 Step 2B 实际写入为准。边上**没有** `width_mean`、`width_std`；若候选需要，在 Step 3A 从墙几何计算。

### 2.3 平行墙组（PG）

`parallel_graph_summary.json` 中的 `PG001`、`PG002`… 是 `is_parallel` 边的**连通分量**，仅作搜索加速索引：

- 不是候选
- 不是巷道
- 不是网络节点

首版遍历全部平行边即可，不依赖平行墙组。

---

## 3. 首版流水线

```text
Step 3A-1   平行边 → 墙对（WallPair）
Step 3A-2   墙对 → 重叠区间 → 中心线 → 巷道候选（CorridorCandidate）
Step 3A-3   候选去重（可选，须在建网之前）
Step 3A-4   候选 → 巷道候选网络（CorridorNetwork）
```

总结：

```text
wall
  ↓
wall pair
  ↓
corridor candidate
  ↓
corridor network
```

---

## 4. Step 3A-1 — 提取墙对

从 `parallel_graph.pkl` 中枚举满足以下条件的边：

```python
data.get("is_parallel") is True
# edge_kind 为 "is_parallel" 或 "endpoint_parallel"
# 两端 node_type 均为 "wall"
```

每条边生成一个 `WallPair`：

```python
{
    "pair_id": "WP001",
    "wall_a": "WS001",          # 字典序较小者，见 §5.3
    "wall_b": "WS005",          # 字典序较大者
    "width": 5.42,              # 继承自边属性
    "overlap_ratio": 0.92,      # 继承自边属性
}
```

**不从平行墙组出发**；平行墙组至多用于缩小枚举范围。

---

## 5. Step 3A-2 — 构造巷道候选

对每个 `WallPair`，按以下**固定顺序**处理：

```text
WallPair → 投影重叠区间 → 中心线 → CorridorCandidate
```

### 5.1 投影重叠区间

在较长墙的朝向上，取两墙线段的投影重叠区间 `[t0, t1]`。  
区间长度即 `corridor_length` 的几何基础。

### 5.2 中心线

在重叠区间内，中心线为两墙对应点的中点连线：

```text
wall A  ========================
wall B  ========================
        ------------------------   ← centerline
```

中心线写入候选后，**成为唯一几何基准**（见 §7）。

```python
"centerline": {
    "start": [x, y],
    "end": [x, y],
    "direction": [dx, dy],    # 归一化，起点 → 终点
    "length": 128.4,
}
```

### 5.3 左右墙定义（数据协议，必须遵守）

墙对命名（与图边 `u/v` 顺序无关）：

```text
wall_a = min(wall_id_1, wall_id_2)   # 字典序
wall_b = max(wall_id_1, wall_id_2)
```

方向与左右：

```text
dir = centerline.direction
vec = midpoint(wall_b) - midpoint(wall_a)

若 cross(dir, vec) > 0：
    left_wall_id  = wall_b
    right_wall_id = wall_a
否则：
    left_wall_id  = wall_a
    right_wall_id = wall_b
```

其中 `cross(a, b) = a.x * b.y - a.y * b.x`（二维叉积）。

### 5.4 候选结构

首版每个保留墙对对应**一条**候选（一对墙，不是墙组）：

```python
{
    "corridor_id": "CC001",
    "pair_id": "WP001",

    "left_wall_id": "WS005",
    "right_wall_id": "WS001",

    "centerline": { ... },

    "corridor_length": 128.4,
    "width": 5.42,              # 首版：继承平行边 width
    "overlap_ratio": 0.92,

    "confidence": 0.92,         # 首版：可直接取 overlap_ratio
}
```

---

## 6. Step 3A-3 — 候选去重

在建网**之前**执行。

### 6.1 归一化墙对

`(WS001, WS005)` 与 `(WS005, WS001)` 视为同一墙对，保留一条。

### 6.2 重复候选

若同一墙对因不同路径出现多次（后续版本可能出现），保留 `overlap_ratio` 较高者。

Step 2B 当前每对直墙至多一条平行边，首版去重主要是墙对顺序归一化。

---

## 7. Step 3A-4 — 构建巷道候选网络

### 7.1 原则

候选生成后，网络构造**全部基于** `candidate.centerline`，**不使用**墙端点距离。

原因：Step 2B 合并后墙可能断裂，但中心线仍应连续；用墙端点会漏连。

### 7.2 节点

每个 `CorridorCandidate` 对应一个网络节点（`corridor_id`）。

### 7.3 边类型

#### 延续（`continue`）

两候选中心线端点接近且方向一致：

```python
centerline_end_gap < continue_gap_th      # 默认 2.0 m
centerline_angle_diff < continue_angle_th # 默认 5.0°
```

```text
--------   ------
```

#### 交叉（`junction`）

两候选中心线相交（含容差内的 T 字、十字）：

```python
centerline_intersection within junction_tol
```

```text
    |
----+----
```

#### 互斥规则

同一对候选节点，**延续与交叉互斥**；若同时满足，**优先标为交叉**。

### 7.4 边结构

```python
{
    "edge_type": "continue",    # 或 "junction"
    "gap": 0.8,                 # continue 时：中心线端点间距
    "angle_diff": 2.1,          # continue 时：方向夹角（度）
    "intersection": [x, y],     # junction 时：交点坐标
}
```

---

## 8. 输出格式

### 8.1 `corridor_candidates.json`

```json
{
  "kind": "corridor_candidates",
  "schema_version": 1,
  "source_stem": "part1-巷道",
  "candidates": [
    {
      "corridor_id": "CC001",
      "pair_id": "WP001",
      "left_wall_id": "WS005",
      "right_wall_id": "WS001",
      "centerline": {
        "start": [100.0, 200.0],
        "end": [228.4, 200.0],
        "direction": [1.0, 0.0],
        "length": 128.4
      },
      "corridor_length": 128.4,
      "width": 5.42,
      "overlap_ratio": 0.92,
      "confidence": 0.92
    }
  ]
}
```

### 8.2 `corridor_network.pkl`

NetworkX 图，`graph["kind"] = "corridor_network"`。

- 节点：`corridor_id` + 候选摘要字段  
- 边：`edge_type`、`continue` / `junction` 属性  

同步写出可读的 `{stem}_corridor_network.json`（可选）。

---

## 9. 阈值与全图尺度

建网阈值**默认相对当前图纸**，不由固定米数写死。候选生成后统计墙间距：

```python
global_scale = {
    median_corridor_width,
    p25_width,
    p75_width,
}
```

据此解析建网参数：

| 尺度系数 | 默认值 | 解析规则 |
|----------|--------|----------|
| `continue_gap_scale` | `1.5` | 延续间隙上限 = 系数 × `median_corridor_width` |
| `continue_lateral_scale` | `0.5` | 共线延续横向容差 = 系数 × 两候选较小 `width` |
| `junction_tol_scale` | `0.2` | 交叉容差 = 系数 × `median_corridor_width` |
| `continue_angle_th` | `5.0`° | 延续方向夹角（绝对值） |
| `junction_angle_th` | `15.0`° | 交叉最小夹角；近平行不标交叉 |

`global_scale` 写入候选列表与独立尺度文件，供 Step 3B 的延续、交叉、横档、硐室判断共用。

平行筛选（宽度带宽、重叠比、夹角）已在 Step 2B 完成；Step 3A **不**以宽度剔除候选。横档、硐室、封闭区域等语义留给 Step 3B（参见 `Advice.md`）。

---

## 10. 后续版本 — 候选竞争（首版不做）

并排双巷等场景下，同一面墙可合法出现在多个候选中（例如 A–B 与 B–C 共用 B）。  
**不能**仅凭「共用墙」判定冲突。

后续版本在候选间建立竞争关系，冲突条件为**三者同时满足**：

```python
share_wall
and longitudinal_overlap > overlap_th
and abs(centerline_offset) < offset_th
```

即：两候选在解释**同一空间带**时才竞争。  
解决方式：冲突图上求**最大权独立集**（或等价加权选集），权重可参考 `overlap_ratio × corridor_length / width_std`。

首版跳过此步，先把候选与网络跑通。

---

## 11. 后续版本 — 候选合并（首版不做）

共线、等宽、小间隙的相邻候选可合并为 `CorridorChain`，供 Step 3B 主巷提取使用。  
首版保留分段候选 + 延续边即可。

---

## 12. 与 Step 3B 的边界

| 步骤 | 职责 |
|------|------|
| **Step 3A** | 平行边 → 墙对 → 候选（含中心线）→ 候选网络 |
| **Step 3B** | 主巷提取；碎线 + 候选网络 → 横档/洞室等细节语义 |

Step 3A 完成后，下游可读取：

```text
corridor_candidates.json
corridor_network.pkl
global_scale.json
residual_geometry.json        # 碎线，Step 3B 使用
```

---

## 13. 运行命令

```powershell
python step3A/run_corridor_candidates.py --stem $stem
python step3A/run_corridor_candidates.py --stem $stem --label
```

**前置条件**：已运行 `step2B/run_straight_wall.py` 与 `step2B/build_parallel_graph.py`。

### 检查图

| 文件 | 内容 |
|------|------|
| `{stem}_primary_wall_pairs.png` | 主墙对（巷道候选）：每个候选的左右墙同色 |
| `{stem}_corridor_centerlines.png` | 巷道中心线图：每条候选中心线一色 |
| `{stem}_centerline_graph.png` | 中心线逻辑图：端点/平行连边 |

---

## 14. 代码模块

| 模块 | 作用 |
|------|------|
| `run_corridor_candidates.py` | 平行边 → 候选 + 候选墙图/中心线图 |
| `build_centerline_graph.py` | 候选 → 中心线逻辑图 + 图可视化 |
| `pipeline.py` | 流水线逻辑 |
| `wall_pair.py` | 平行边枚举、墙对归一化 |
| `corridor_candidate.py` | 重叠区间、中心线、左右墙 |
| `centerline_graph.py` | 中心线端点/平行连边 |
| `global_scale.py` | 全图宽度统计与相对阈值解析 |
| `config.py` | 尺度系数配置 |
| `paths.py` | 产物路径 |
| `visualize.py` | 检查图 |

共享库：`stage2/io.py`（JSON / 图持久化）。
