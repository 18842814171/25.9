# 第二阶段：通风设施关联

目标：在图纸上识别「通风设施」图层符号（块参照与一般图元混合），组合为设施实例后，关联到第一阶段乙产出的带标注结构图。代码均位于本目录 `stage2/`，不另设甲乙子目录。阈值集中在 [`config.py`](config.py)。总体进度见 [`docs/01-architecture.md`](../docs/01-architecture.md)。

## 数据流概要

| 脚本 | 主输入 | 主产出 |
|------|--------|--------|
| 0 | 根目录 `{图号}-设施.json` | 设施图元图 |
| 2 | 设施图元图 | 设施实例图 |
| 3 | 带标注结构图（文字+巷道融合）；设施实例图 | 带设施结构图 + 核对图 |
| 4 | 设施实例图或带设施结构图 | 核对图（可单独重绘） |

关联底图路径须在命令行显式指定。与《重要原则》第 7 条尚有差距：脚本 0 以导出 JSON 为起点；脚本 2 读图元图；脚本 3 同时读结构图与设施实例图。

图纸须先由 `utils/entity_export.py`（配置见 `utils/entity_export_config.json`）按 `--mode facility` 写出 `{stem}-设施.json`；本阶段脚本不再直接读图纸。公共模块见 [`utils/使用方法.md`](../utils/使用方法.md)。

## 已运行命令

下列命令对应整图已落盘产物（工作目录为仓库根目录；导出前设定配置中的图纸路径）：

```text
python utils/entity_export.py --mode facility
python stage2/0_facility_primitives_graph.py --stem 2026.1-1
python stage2/2_build_facility_graph.py --stem 2026.1-1
python stage2/3_structure_graph_with_facilities.py --stem 2026.1-1 --structure-pkl step1b/output/2026.1-1-structure_graph_with_texts.pkl
python stage2/4_visualize.py --stem 2026.1-1
```

局部图按同序执行（与整图独立，不再依赖整图设施模板）：

```text
python utils/entity_export.py --mode facility --dxf_file_path dxf/2026.1-1part.dxf
python stage2/0_facility_primitives_graph.py --stem 2026.1-1part
python stage2/2_build_facility_graph.py --stem 2026.1-1part
python stage2/3_structure_graph_with_facilities.py --stem 2026.1-1part --structure-pkl step1b/output/2026.1-1part-structure_graph_with_texts.pkl
python stage2/4_visualize.py --stem 2026.1-1part
```

## 实现进度与限制

| 项目 | 现状 |
|------|------|
| 流水线 | 整图导出、建图、组合、关联、核对图均已跑通 |
| 设施分型 | 已移除图例模板匹配；实例统一标为「通风设施」 |
| 后续 | 拟采用深度学习目标检测或实例分割完成设施类型识别 |

## 计算要点

1. **抽取**：图层「通风设施」；类型含线、多段线、填充、圆弧、圆、块参照、文字。按端点容差加连接边；无开端点者并入最近线划，再以连通分量作为符号候选。
2. **实例**：按端点连通分量组合；识别与关联分属不同脚本。
3. **关联**：点到中心线垂足距离用统计阈值；只挂巷道类中心线；保留原图节点，仅增设施节点与关联边。

## 产物路径

均在 `stage2/output/`，图号记为 `{stem}`：

| 产物 | 文件 |
|------|------|
| 设施图元图 | `{stem}-facility_primitives_graph.pkl` / `.json` |
| 设施实例图 | `{stem}-facility_graph.pkl` / `.json` / `.png` |
| 带设施结构图 | `{stem}-structure_graph_with_facilities.pkl` / `.json` / `.png` |
