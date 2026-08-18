# Step 2A — 局部折角识别与圆弧标准化

Step 2A 从原始几何（LINE + ARC）出发，完成两件事：

1. **方折记录**（`square_bend.json`）：检测 LINE–LINE 直角折点，**不改几何**。
2. **圆角 fillet 识别 + 消弧**（`arc_bend.json` → `arc_line_normalize.json`）：
   - 先对每个 ARC 做 **置信度分类**（fillet / unknown）；
   - 仅对高置信度 fillet 删弧、裁端。

**识别与几何修改分离**：`arc_bend_detect` 只写 JSON；`arc_normalize` 只消费检测结果做裁端。

**本步不做**：连续墙合并、共线合并、链构建（留待 Step 2B）、墙网拓扑修复。

本步末尾产出 **标准化几何** 与 **标准化连接图**，供 Step 2B 读取。

---

## 流水线

```text
run_init_graph
      ↓
square_bend              # 方折，只记录
      ↓
arc_bend_detect          # 圆角分类 + 折点坐标（不改几何）
      ↓
arc_normalize            # 按检测结果裁端、删弧
      ↓
merge_normalized_geometry    # 合并为 normalized_geometry.json
      ↓
build_normalized_graph     # 建 normalized_graph（仅 LINE）
      ↓
run_overview             # 检查用总览图（须在 merge 之后）
```

---

## 目录结构

```text
step2A/
├── raw/                              # run_init_graph 写入
│   ├── {stem}.json                   # 原始几何副本
│   ├── {stem}_init-graph.pkl
│   └── {stem}_init-graph.json
├── output/
│   ├── {stem}_square_bend.json
│   ├── {stem}_arc_bend.json          # arc_bend_detect 写入，arc_normalize 读取
│   ├── {stem}_arc_line_normalize.json
│   ├── {stem}_unmodified_elements.json
│   ├── {stem}_normalized_geometry.json
│   ├── {stem}_normalized_graph.pkl
│   ├── {stem}_normalized_graph.json
│   └── {stem}_step2a_overall.png
├── run_init_graph.py
├── square_bend.py
├── arc_bend_detect.py
├── arc_normalize.py
├── merge_normalized_geometry.py
├── build_normalized_graph.py
├── run_overview.py
├── init_graph.py
├── normalized_geometry.py
├── normalized_graph.py
├── bend_layer.py
├── bends.py
├── paths.py
└── visualize.py
```

---

## 运行命令

以下以仓库根目录为当前路径，示例数据 `part2-巷道.json`。

### 0. 一键顺序执行（PowerShell）

```powershell
$stem = "2026.1-1part-巷道"

python step2A/run_init_graph.py --geo "2026.1-1part-巷道.json" --stem $stem
python step2A/square_bend.py --stem $stem
python step2A/arc_bend_detect.py --stem $stem
python step2A/arc_normalize.py --stem $stem
python step2A/merge_normalized_geometry.py --stem $stem
python step2A/build_normalized_graph.py --stem $stem
python step2A/run_overview.py --stem $stem
```

### 1. 构建 init-graph（必须先完成）

```powershell
python step2A/run_init_graph.py `
  --geo part2-巷道.json `
  --stem part2-巷道
```

| 参数 | 默认 | 含义 |
|------|------|------|
| `--geo` | `stage2/in/2026.1-1tmp-巷道.json` | 输入几何 JSON（LINE / ARC 列表） |
| `--stem` | geo 文件名（不含扩展名） | 输出前缀 |
| `--raw` | `step2A/raw/` | raw 产物目录 |
| `--endpoint-link-gap` | `8.0` | 端点吸附半径（米） |

产物：`raw/{stem}.json`、`raw/{stem}_init-graph.{pkl,json}`。

init-graph 边上含 `endpoint_gap`、`angle_deg`、`is_para`、`is_ortho` 等邻接属性，**不做折角判断**。

### 2. 方折检测

```powershell
python step2A/square_bend.py --stem part2-巷道
```

| 参数 | 默认 | 含义 |
|------|------|------|
| `--stem` | （必填） | 与 init-graph 一致的 stem |
| `--raw` | `step2A/raw/` | raw 目录 |
| `--output` | `step2A/output/` | 输出目录 |
| `--endpoint-link-gap` | `8.0` | 与 init-graph 保持一致 |

只读 `raw/{stem}_init-graph.pkl`，写出 `output/{stem}_square_bend.json`。

### 3. 圆角检测（arc_bend_detect）

```powershell
python step2A/arc_bend_detect.py --stem part2-巷道
```

| 参数 | 默认 | 含义 |
|------|------|------|
| `--stem` | （必填） | 与 init-graph 一致的 stem |
| `--fillet-threshold` | `0.75` | `confidence ≥ 阈值` 标为 `status=fillet` |
| `--endpoint-link-gap` | `8.0` | 与 init-graph 保持一致 |

读 `init-graph.pkl` + `raw/{stem}.json`，写出 `output/{stem}_arc_bend.json`（**不改几何**）。

### 4. 圆角消弧（arc_normalize）

```powershell
python step2A/arc_normalize.py --stem part2-巷道
```

| 参数 | 默认 | 含义 |
|------|------|------|
| `--stem` | （必填） | 与上一步一致 |
| `--fillet-threshold` | `0.75` | 须与 `arc_bend_detect` 相同 |

读 `arc_bend.json`，对 `status=fillet` 且 `signals.clip_ok=1` 的 ARC 裁端删弧，写出：

- `output/{stem}_arc_line_normalize.json` — 被裁端的 LINE
- `output/{stem}_unmodified_elements.json` — 剩余图元（含 unknown ARC）

**前置条件**：必须先跑 `arc_bend_detect.py`。

### 5. 合并标准化几何（merge_normalized_geometry）

```powershell
python step2A/merge_normalized_geometry.py --stem part2-巷道
```

读 `arc_line_normalize.json` 与 `unmodified_elements.json`，合并为 `output/{stem}_normalized_geometry.json`。

规则：

- 仅保留 **LINE**（未消弧的 ARC 不写入）；
- 同一 `handle` 以 `arc_line_normalize` 中的裁端结果为准。

### 6. 建标准化连接图（build_normalized_graph）

```powershell
python step2A/build_normalized_graph.py --stem part2-巷道
```

| 参数 | 默认 | 含义 |
|------|------|------|
| `--stem` | （必填） | 与上一步一致 |
| `--endpoint-link-gap` | `8.0` | 须与 init-graph 保持一致 |

读 `normalized_geometry.json`，写出：

- `output/{stem}_normalized_graph.pkl`
- `output/{stem}_normalized_graph.json`

与 `raw/{stem}_init-graph` 的区别：

| 图 | 节点 | 用途 |
|----|------|------|
| init-graph | LINE + ARC | 方折 / 圆角检测 |
| normalized_graph | 仅 LINE | Step 2B 连续墙识别 |

**前置条件**：必须先跑 `merge_normalized_geometry.py`。

### 7. 总览图

```powershell
python step2A/run_overview.py --stem part2-巷道
```

读 `normalized_geometry.json` 与 square / arc_bend 折点，写出 `output/{stem}_step2a_overall.png`。

---

## 圆角分类逻辑（概要）

### ARC 两侧 LINE 配对（`step2A/bend_layer.py`）

每个 ARC 端点先取**距离带内**的局部 LINE 候选，再双侧枚举，按联合几何评分选最优 pair：

1. 两侧贴弧（`d0 + d1` 最小）
2. 切线交点靠近弧中点
3. 夹角接近 90°（`-|acute - 90°|`）

不使用「全组合最大锐角」配对（易跨结构误配洞室）。

### 置信度信号（`bends.detect_arc_bends`）

| 信号 | 含义 |
|------|------|
| `localness` | 两侧 LINE 贴弧程度 |
| `ix_near_arc` | 交点与弧中点距离 |
| `angle` | 夹角是否接近 90° |
| `corner_plausible` | 弧弦是否在 LINE 夹角处 |
| `neighborhood` | 端点邻域复杂度（≥3 条线时 ×0.5，**降权不一票否决**） |
| `clip_ok` | 裁端几何是否可行 |

加权合成 `confidence`；`≥ fillet_threshold`（默认 0.75）→ `status=fillet`，否则 `unknown`。

`arc_normalize` 额外要求 `clip_ok=1` 才实际改几何。

---

## JSON 格式

### `square_bend.json`

```json
{
  "kind": "square_bend",
  "schema_version": 1,
  "source_stem": "part2-巷道",
  "bends": [
    {
      "id": "Y0001",
      "kind": "square",
      "bend_point": [1555.0, 795.38],
      "line1": "2E4",
      "line2": "2D7",
      "source_arc": null
    }
  ]
}
```

### `arc_bend.json`（schema_version 2）

由 `arc_bend_detect` 写出，含全部 ARC 分类结果：

```json
{
  "kind": "arc_bend",
  "schema_version": 2,
  "source_stem": "part2-巷道",
  "fillet_threshold": 0.75,
  "arcs": [
    {
      "arc_handle": "2D8",
      "status": "fillet",
      "confidence": 0.8911,
      "bend_point": [1561.5, 795.17],
      "line1": "2E3",
      "line2": "2D7",
      "signals": {
        "localness": 1.0,
        "ix_near_arc": 0.7643,
        "angle": 1.0,
        "corner_plausible": 1.0,
        "neighborhood": 0.5,
        "clip_ok": 1.0
      }
    },
    {
      "arc_handle": "2F8",
      "status": "unknown",
      "confidence": 0.0
    }
  ],
  "bends": [
    {
      "id": "Y0001",
      "kind": "fillet",
      "bend_point": [1561.5, 795.17],
      "line1": "2E3",
      "line2": "2D7",
      "source_arc": "2D8",
      "confidence": 0.8911
    }
  ]
}
```

- `arcs[]`：每条 ARC 一条记录（fillet + unknown 均有）
- `bends[]`：仅 `status=fillet` 的折点列表，供可视化与 Step 2B

### `arc_line_normalize.json`

仅含**端点被改过**的 LINE：

```json
{
  "kind": "arc_line_normalize",
  "schema_version": 1,
  "source_stem": "part2-巷道",
  "elements": [
    {
      "handle": "2D7",
      "type": "LINE",
      "attributes": { "start": [...], "end": [...] }
    }
  ]
}
```

### `unmodified_elements.json`

未被 normalize 改动的图元：unknown ARC、未裁端的 LINE 等。

### `normalized_geometry.json`

合并后的 **LINE 全集**（供 Step 2B 与 `build_normalized_graph` 使用）：

```json
{
  "kind": "normalized_geometry",
  "schema_version": 1,
  "source_stem": "part2-巷道",
  "elements": [
    {
      "handle": "2D6",
      "type": "LINE",
      "attributes": { "start": [...], "end": [...] }
    }
  ]
}
```

### `normalized_graph`

`build_normalized_graph` 写出 `output/{stem}_normalized_graph.{pkl,json}`，节点仅 LINE，边属性同 init-graph。

---

## 总览图 `{stem}_step2a_overall.png`

| 图层 | 颜色 | 来源 |
|------|------|------|
| 归一化 LINE | 蓝色 | `normalized_geometry.json` |
| 方折折点 | 蓝点 + `Y` 编号 | `square_bend.json` |
| fillet 折点 | 红点 + `Y` 编号 | `arc_bend.json` → `bends[]` |

仅用于检查，**不做**连续线段连接或拓扑修复。

---

## 代码入口

| 模块 | 作用 |
|------|------|
| `run_init_graph.py` | 原始 JSON → init-graph |
| `init_graph.py` | `build_init_graph` |
| `square_bend.py` | init-graph → 方折 JSON |
| `arc_bend_detect.py` | init-graph → 圆角分类 JSON |
| `arc_normalize.py` | arc_bend.json → 裁端线段 + unmodified |
| `merge_normalized_geometry.py` | 合并 → `normalized_geometry.json` |
| `build_normalized_graph.py` | `normalized_geometry` → `normalized_graph` |
| `run_overview.py` | 汇总 PNG |
| `bend_layer.py` | 端点邻接、ARC 配对、切线交点 |
| `bends.py` | `detect_square_bends`、`detect_arc_bends`、`normalize_arcs_from_detect` |
| `stage2/geometry.py` | 图元提取、`build_endpoint_graph`（共用） |
| `stage2/io.py` | JSON / 图持久化（共用） |

---

## 下游

| 步骤 | 读取 |
|------|------|
| **Step 2B** | 读取 `normalized_graph.pkl`、`normalized_geometry.json`；连续墙与墙链识别 |
| **Step 3** | Step 2B 过滤候选 |
