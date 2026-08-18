批处理脚本说明
==============

本文说明代码根目录下批处理相关脚本的用途与用法。撰写语气与命名约定遵循 `7.14/重要原则.txt`：书面语、正式表述；产物名称与路径一经确定即持续沿用，不保留同义异名。

一、职责划分

根目录批处理脚本只负责「多样本编排、产物收集与指标汇总」，不合并算法步骤本身。巷道几何、标注挂接、设施识别等具体步骤仍分别位于 `5.29/` 与 `7.14/` 的独立脚本中，由流水线按既定顺序逐一调用。

整图与局部图严格分开：

| 入口 | 对象 | 整图专用步骤 |
|------|------|--------------|
| `run_full_drawing` | 仅整图 | 标注图例模板与识别规则；设施图例模板（不负责 DXF 提取） |
| `run_stats` | 仅局部图 | 不执行上述步骤；引用整图已写出的规则与设施模板 |
| `batch_export_test_input.py` | 整图或局部图 | 从 DXF 导出 JSON；须显式传入 `--cfg` |

二、强制规则

**同一系列图纸必须先完成该系列整图流水线，方可运行局部图批处理。**

若整图产物中缺少识别规则或设施图例模板，局部批处理将直接退出并提示先执行 `run_full_drawing`。不得在局部图上重复抽取图例或重新标定识别规则。

三、目录约定

| 路径 | 含义 |
|------|------|
| `test_input/` | 输入目录：整图与局部图 DXF，以及导出后的巷道、文字、设施 JSON；整图另含图例 JSON |
| `{图号}_output/` | 单图流水线全部产物根目录（默认写在代码根目录下） |
| `{整图图号}_output/714-stage1/{整图图号}-retrieval_rules.json` | 整图标定的标注识别规则（局部图共用） |
| `{整图图号}_output/714-stage2/{整图图号}-facility_templates.json` | 整图抽取的设施图例模板（局部图共用） |
| `{图号}_output/{图号}_pipeline_stats.json` | 单图流水线结束后汇总的阶段统计 |
| `统计表.txt` | 论文统计表模板（含整图指标与批处理可汇总项） |
| `chk/` | 人工核对用位图与统计结果的常用落点（可选） |

图号即 DXF 主文件名（不含扩展名），例如 `2.dxf` 对应产物目录 `2_output/`。

四、推荐执行顺序

1. 将本系列整图 DXF 与各局部图 DXF 放入约定位置（整图可用独立路径；局部图常用 `test_input/`）。
2. 用 `batch_export_test_input.py` 导出 JSON（须传 `--cfg`）：
   - 整图：`--src <整图路径> --cfg ... --with-legend`
   - 局部图：不传 `--src`，遍历 `test_input`，`--cfg ...`（勿加 `--with-legend`）
3. 对本系列整图运行 `run_full_drawing`（仅计算，不提取）。
4. 对本系列局部图运行 `run_stats --src <整图路径>`（仅计算，不提取）。
5. （可选）收集结构图核对位图。
6. （可选）汇总《统计表》中可由批处理统计文件计算的指标。

五、脚本用法

1. `batch_export_test_input.py` — 导出图元 JSON（提取步骤，与 bat 分离）

`--cfg` 必填（亦兼容 `--config`）。配置中 `layers` 为图层名子串，非全等；可选 `exclude_layer_keywords` 在已命中图层中再按关键词排除。传入 `--src` 时导出该整图；省略 `--src` 时遍历 `test_input/*.dxf`（局部图）。

```text
python batch_export_test_input.py --src 2026.1-2/2026.1-2.dxf --cfg test_input/2016_config.json --with-legend

python batch_export_test_input.py --cfg XJH/config.json

```

说明：`--src` 约定与 `run_full_drawing` 相同。JSON 默认写回 `test_input/`。整图须加 `--with-legend`；局部图勿加。文字导出后会自动调用 `7.14/utils/temp_clean_text_export.py`：剔除巷道描边，并为 INSERT 补包围盒/等效半径。

2. `run_full_drawing.bat` / `run_full_drawing.sh` — 整图专用计算流水线

对指定整图跑通 `5.29` 与 `7.14` 全部计算步骤（含标注图例模板、识别规则标定、设施图例模板）；写出 `{整图图号}_output` 与阶段统计。**不调用导出脚本**；须事先完成步骤 1 的整图导出（含图例）。

```text
.\run_full_drawing.bat --src XJH\XJH2025.9.30.dxf
run_full_drawing.bat --src XJH\XJH2025.9.30.dxf
run_full_drawing.bat --src 2026.1-2\2026.1-2 --output-root D:\自定义输出根目录

./run_full_drawing.sh --src 2026.1-1
./run_full_drawing.sh --src 2026.1-2/2026.1-2
./run_full_drawing.sh --src 2026.1-2/2026.1-2 --output-root /path/to/output_root
```

说明：`--src` 为相对代码根目录的 DXF 路径（可带或不带 `.dxf`），例如 `2026.1-2\2026.1-2` 对应 `2026.1-2\2026.1-2.dxf`；亦兼容 `test_input/{图号}.dxf`。脚本据此解析文件，向各 Python 步骤仅传入 `--stem=图名`（路径 basename）。缺少 `test_input/{图号}-巷道.json` 或图例 JSON 时直接退出并提示先导出。

3. `run_stats.bat` / `run_stats.sh` — 局部图批处理（仅计算）

扫描 `test_input/*.dxf`，自动跳过整图 DXF；对每张局部图调用几何与标注步骤，**不**运行标注图例抽取、识别规则标定、设施图例抽取；通过 `--rules-json` / `--templates-json` 引用整图产物。**不调用导出脚本**；局部图 JSON 须事先导出。

须显式传入 `--src <整图路径>`；省略则拒绝运行。

```text
.\run_stats.bat --src XJH\XJH2025.9.30.dxf
run_stats.bat --src 2026.1-2\2026.1-2
run_stats.bat --src 2026.1-1 --output-root D:\自定义输出根目录

./run_stats.sh --src 2026.1-1
./run_stats.sh --src 2026.1-2/2026.1-2
./run_stats.sh --src 2026.1-1 --output-root /path/to/output_root
```

说明：`--src` 为整图路径（与 `run_full_drawing` 相同约定）；图号取其 basename，用于定位识别规则与设施图例模板。须已存在对应产物，否则拒绝运行。向各 Python 步骤仅传入 `--stem=图名`。

局部图相对整图跳过的步骤：

- `7.14/step1a/1_extract_retrieval_templates.py`
- `7.14/step1a/2_retrieval_rules.py`
- `7.14/stage2/1_extract_facility_templates.py`

4. `collect_pipeline_stats.py` — 阶段统计收集

从 `{图号}_output` 读取各阶段摘要，写回 `{图号}_pipeline_stats.json`。整图与局部图流水线末尾均已自动调用单图模式。

无参数时：仅扫描当前工作目录下一层的 `*_output`（不递归），逐图重算并合并为当前目录下的 `output_summary.json`。

```text
python collect_pipeline_stats.py
python collect_pipeline_stats.py --stem 2 --output-root 2_output
python collect_pipeline_stats.py --root 2026.1-1 --summary-out 2026.1-1/output_summary.json
```

5. `collect_structure_png_to_chk.bat` — 收集结构图核对位图

将各 `{图号}_output/714-stage2/*-structure_graph_with_facilities.png` 复制到代码根目录 `chk/`。

```text
.\collect_structure_png_to_chk.bat
```

说明：仅扫描代码根目录下一层的 `*_output`；若产物写在子目录，请保证路径符合扫描范围，或改为在该批输出所在目录另行收集。

6. `compute_stats_table.py` — 汇总《统计表》批处理指标

递归收集 `{图号}_output/{图号}_pipeline_stats.json`，统计抽样样本数量，对计数类指标求和、对宽度类指标取算术平均。

```text
python compute_stats_table.py --root 2026.1-1
python compute_stats_table.py --root 2026.1-1 --out 2026.1-1/chk/统计表_批处理汇总.txt
```

说明：依赖整图中间产物、而未写入 `pipeline_stats` 的条目不在本脚本计算范围内。

六、与《重要原则》的对应关系

- 根目录脚本不替代步骤脚本：圆角规范化、方折处理、标注簇构建、设施挂接等仍分文件、分步骤运行。
- 整图专用逻辑与局部图批处理分属不同入口，避免在局部图上重复整图逻辑。
- 多样本编排仅串联既有步骤，不改变各步骤「一入一出逻辑拓扑图」的数据约定。
- 产物统一使用 `{图号}_output` 与 `{图号}_pipeline_stats.json` 命名，不再另设同义路径。
