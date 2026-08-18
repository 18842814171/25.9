# 第一阶段甲：由图例归纳测点与钻孔规则并识别

本目录完成：由文字导出建立标注关系图，由图例导出归纳模板，由整图标定识别规则，再按「更近优先」在目标图上聚簇。各脚本分步单独运行，不设总控入口。阈值一律写在 [`config.py`](config.py)。总体进度见 [`docs/01-architecture.md`](../docs/01-architecture.md)。

## 脚本运行逻辑

整图用于归纳模板与标定规则；局部图只建标注关系图，并引用整图已标定的规则完成聚簇。

```text
【整图】
  utils/entity_export.py --mode text
      输入：图纸（见 utils/entity_export_config.json）
      输出：根目录 {图号}-文字.json
  utils/entity_export.py --mode legend
      输入：图纸
      输出：根目录 {图号}-图例.json
  0_retrieved_elements_graph.py
      输入：根目录文字 JSON
      输出：标注关系图
  1_extract_retrieval_templates.py
      输入：根目录图例 JSON
      输出：图例模板（独立可读文件）
  2_retrieval_rules.py
      输入：标注关系图、图例模板
      输出：识别规则（独立可读文件）
  3_apply_retrieval_rules.py
      输入：标注关系图、识别规则
      输出：候选簇图
  4_final_clusters.py
      输入：候选簇图
      输出：最终簇图

【局部图】
  utils/entity_export.py --mode text（配置中图纸改为局部图）
      输出：根目录局部文字 JSON
  0_retrieved_elements_graph.py
      输出：局部标注关系图与建链核对图（建链后暂停）
  3_apply_retrieval_rules.py --rules-from-stem <整图图号>
      识别规则取自整图；输出候选簇图
  4_final_clusters.py
      输出：最终簇图
```

## 已运行命令

下列命令对应仓库内已落盘产物（图号 `2026.1-1` / `2026.1-1part`）。工作目录为仓库根目录；导出前在 `utils/entity_export_config.json` 中设定 `dxf_file_path`。

```text
# 整图导出与甲步
python utils/entity_export.py --mode text --stem 2026.1-1
python utils/entity_export.py --mode legend --stem 2026.1-1
python step1a/0_retrieved_elements_graph.py --stem 2026.1-1
python step1a/1_extract_retrieval_templates.py --stem 2026.1-1
python step1a/2_retrieval_rules.py --stem 2026.1-1
python step1a/3_apply_retrieval_rules.py --stem 2026.1-1
python step1a/4_final_clusters.py --stem 2026.1-1

# 局部图（配置中图纸改为局部图后导出文字）
python utils/entity_export.py --mode text
python step1a/0_retrieved_elements_graph.py --stem 2026.1-1part
python step1a/3_apply_retrieval_rules.py --stem 2026.1-1part --rules-from-stem 2026.1-1
python step1a/4_final_clusters.py --stem 2026.1-1part
```

说明：

- 唯一读图纸的入口为 `utils/entity_export.py`。写出文字 JSON 后，本目录各脚本只读该 JSON（及本阶段产物）。
- 仅脚本 0 建立文字与圆或块的邻接边、文字邻近边与朝向边后，立即按邻近且同朝向建立字与值、值与值的绑定链条（选圆之前），并画出建链核对图后暂停（不挂圆）。
- 脚本 3 测点：绑定组与圆一对一就近分配；争夺同一圆时，较远组改挂次近空闲圆，不因距离更远而整组丢弃。
- 测点标号规则：图层名含「控制点」且文字不是纯数值时，一律视为测点标号候选。
- 参数 `--rules-from-stem` 指定读取哪一图号下的识别规则；省略时默认与 `--stem` 相同。
- 脚本 3、4 均绘制核对图并叠加巷道线，巷道数据取自项目根目录 `{图号}-巷道.json`。

## 实现进度

| 图号 | 产物 | 状态 |
|------|------|------|
| `2026.1-1` | 标注关系图、图例模板、识别规则、候选簇图、最终簇图及核对图 | 已落盘 |
| `2026.1-1part` | 标注关系图、候选簇图、最终簇图及核对图（规则引自整图） | 已落盘 |

整图最终簇约 958 个（控制点约 900、钻孔约 58）。方法依赖文字语义与圆或块锚点，在本图上可用。

## 产物一览

| 英文名 | 中文名 | 说明 |
|--------|--------|------|
| `retrieved_elements_graph` | 标注关系图 | 标注节点，并按距离邻近加上文字—符号邻接边；不含规则与簇 |
| `retrieval_templates` | 图例模板 | 从图例区归纳的样板；独立可读文件 |
| `retrieval_rules` | 识别规则 | 由整图共现统计得到；独立可读文件 |
| `candidate_cluster` | 候选簇图 | 脚本 3：多对多候选成员，尚未独占归属 |
| `final_cluster` | 最终簇图 | 脚本 4：过滤后的独占成员簇图 |

磁盘路径（均在 `step1a/output/`，图号记为 `{stem}`）：

| 产物 | 文件 |
|------|------|
| 标注关系图 | `{stem}-retrieved_elements_graph.pkl`、`.json`；建链核对图 `{stem}-bind_chains.png` |
| 图例模板 | `{stem}-retrieval_templates.json` |
| 识别规则 | `{stem}-retrieval_rules.json` |
| 候选簇图 | `{stem}-candidate_cluster.pkl`、`.json`、`.png`；锚点核对图 `{stem}-cluster_centers.png` |
| 最终簇图 | `{stem}-final_cluster.pkl`、`.json`、`.png`；锚点核对图 `{stem}-cluster_centers.png`（覆盖候选阶段同名产物） |

## 标注关系图要点

图级属性除图号、来源文字 JSON、图例图层外，另含字高中位数、邻接半径及其相对字高倍数、邻接边条数等。邻接边连接文字节点与圆或块参照节点；另保留文字邻近边、朝向一致边；测点的字与值绑定由专用绑定边完成。簇图阶段另增成员边。

## 拓扑图可读摘要总结构

| 字段 | 含义 |
|------|------|
| `graph` | 图级属性 |
| `summary` | 节点数、边数、边类型计数、分组计数等 |
| `summary.grouping` | 无簇时按实体类型，有簇时按簇类型 |
| `groups` | 按分组列出的节点或簇明细 |

图例模板与识别规则为独立文档，无上述外壳。

## 图级属性与节点字段

| 字段 | 出现阶段 | 含义 |
|------|----------|------|
| `graph_name` | 全程 | `retrieved_elements_graph`、`candidate_cluster` 或 `final_cluster` |
| `stem` | 全程 | 图号 |
| `source_text_json` | 建图起 | 建图所用根目录文字导出 JSON 路径 |
| `template_layer` | 建图起 | 图例图层名（默认「图例」） |
| `step1a_config` | 建图起 | 运行时顶层配置快照 |
| `cluster_summary` | 簇图 | 聚簇结果计数 |

标注节点含句柄、实体类型、图层、文字、坐标、字高、旋转、半径、块名等；归入簇后另有角色、簇编号与簇类型。簇节点含簇编号、类型（控制点或钻孔）、置信度、成员列表。

## 图例模板与识别规则

图例模板含图例样例与合并后的符号、字段槽；识别规则含搜索半径、图层到角色的映射、每簇角色上限等。套用时以邻接边为候选范围。测点：小圆为锚；标号取控制点类图层上非纯数值文字；标高取控制点类图层上的数值。钻孔优先以块参照为锚。

## 核对图颜色含义

建链阶段（脚本 0）：每链一色表示同一绑定组；灰为未入链文字及圆或块；绿为巷道线（若存在对应巷道 JSON）。簇阶段（脚本 3、4）：蓝绿系为测点簇，红色系为钻孔簇，灰为未归入簇的标注，绿为巷道线。锚点核对图 `{stem}-cluster_centers.png` 着色规则与建链图相同，并额外以实心圆标出已识别为簇心的 point-like 锚点；未作锚点的符号仍为灰色。

## 原则符合情况（摘要）

分步脚本、同目录模块、参数集中于顶层配置、产物一名一义，均已按此目录实现。说明文档在阶段性结果稳定后维护。

关于逻辑拓扑图输入输出：脚本 0 以根目录文字导出 JSON 为起点；脚本 1 以图例 JSON 为起点；脚本 2、3 在拓扑图之外另依赖模板或规则文件。与《重要原则》第 7 条「完整步骤只输入一个逻辑拓扑图」相比，甲步内部仍属多文件数据流；对外主产物为最终簇图。
