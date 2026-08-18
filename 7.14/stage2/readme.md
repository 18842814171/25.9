# 第二阶段：通风设施挂接

目标：在图纸上识别「通风设施」图层符号（块参照与一般图元混合），按图例分型后，挂接到第一阶段乙产出的带标注结构图。代码均位于本目录 `stage2/`，不另设甲乙子目录。阈值集中在 [`config.py`](config.py)。总体进度见 [`docs/01-architecture.md`](../docs/01-architecture.md)。

## 数据流概要

| 脚本 | 主输入 | 主产出 |
|------|--------|--------|
| 0 | 根目录 `{图号}-设施.json` | 设施图元图 |
| 1 | 根目录 `{图号}-图例.json` | 设施图例模板 |
| 2 | 设施图元图；图例模板 | 设施实例图 |
| 3 | 带标注结构图（文字+巷道融合）；设施实例图 | 带设施结构图 + 核对图 |
| 4 | 设施实例图或带设施结构图 | 核对图（可单独重绘） |

挂接底图路径须在命令行显式指定。与《重要原则》第 7 条尚有差距：脚本 0、1 以导出 JSON 为起点；脚本 2 同时读图元图与模板；脚本 3 同时读结构图与设施实例图。

图纸须先由 `utils/entity_export.py`（配置见 `utils/entity_export_config.json`）按 `--mode facility` / `--mode legend` 写出对应 JSON；本阶段脚本不再直接读图纸。公共模块见 [`utils/使用方法.md`](../utils/使用方法.md)。

## 已运行命令

下列命令对应整图已落盘产物（工作目录为仓库根目录；导出前设定配置中的图纸路径）：

```text
python utils/entity_export.py --mode facility
python utils/entity_export.py --mode legend
python stage2/0_facility_primitives_graph.py --stem 2026.1-1
python stage2/1_extract_facility_templates.py --stem 2026.1-1
python stage2/2_build_facility_graph.py --stem 2026.1-1
python stage2/3_structure_graph_with_facilities.py --stem 2026.1-1 --structure-pkl step1b/output/2026.1-1-structure_graph_with_texts.pkl
python stage2/4_visualize.py --stem 2026.1-1
```

局部图若需复用整图模板（当前仓库以整图产物为主；局部图按同序执行，脚本 2 加 `--templates-from-stem`）：

```text
python utils/entity_export.py --mode facility --dxf_file_path dxf/2026.1-1part.dxf
python stage2/0_facility_primitives_graph.py --stem 2026.1-1part
python stage2/2_build_facility_graph.py --stem 2026.1-1part --templates-from-stem 2026.1-1
python stage2/3_structure_graph_with_facilities.py --stem 2026.1-1part --structure-pkl step1b/output/2026.1-1part-structure_graph_with_texts.pkl
python stage2/4_visualize.py --stem 2026.1-1part
```

## 实现进度与限制

| 项目 | 现状 |
|------|------|
| 流水线 | 整图导出、建图、抽模板、成簇分型、挂接、核对图均已跑通 |
| 图例模板 | 五类已写出：调节风窗、自动风门、风桥、永久密闭、行车风门 |
| 整图实例 | 设施簇约 2254 个；其中「未分型」约 2250 个，真正分上型约 4 个 |

分型几乎失败，并非标题对不上，而是候选簇本身往往不是完整符号：

1. 图面大量孤立实心填充，端点连边稀疏，多数填充无法并入线划连通分量，形成「一簇一个填充」。
2. 模板以线划为主、实例常仅为填充时，类型直方图硬规则直接判为不匹配。
3. 图例符号尺度与图面实例可差一个数量级，尺寸分也很低。

与第一阶段甲对比：甲步靠「锚点 + 文字语义」定类型；本步靠「几何碎片拼符号再比模板」，在填充多、线少、画法不一的图上更脆。由于同一设施在实例中常无法形成完整几何结构，模板匹配方法受限。后续拟采用深度学习目标检测或实例分割完成统一识别；在方法替换前，仍保留本目录现行实现与产物。

## 计算要点

1. **抽取**：图层「通风设施」；类型含线、多段线、填充、圆弧、圆、块参照、文字。按端点容差加连接边；无开端点者并入最近线划，再以连通分量作为符号候选。
2. **模板**：图例标题近旁取端点连通分量；指纹含类型直方图、尺寸、长短边比等，旋转不敏感。
3. **实例**：按端点连通分量成簇并分型；识别与挂接分属不同脚本。
4. **挂接**：点到中心线垂足距离用统计阈值；只挂巷道类中心线；保留原图节点，仅增设施节点与挂接边。

## 产物路径

均在 `stage2/output/`，图号记为 `{stem}`：

| 产物 | 文件 |
|------|------|
| 设施图元图 | `{stem}-facility_primitives_graph.pkl` / `.json` |
| 图例模板 | `{stem}-facility_templates.json` |
| 设施实例图 | `{stem}-facility_graph.pkl` / `.json` / `.png` |
| 带设施结构图 | `{stem}-structure_graph_with_facilities.pkl` / `.json` / `.png` |


