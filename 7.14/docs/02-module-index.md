# 模块索引

按现行目录与脚本职责列出入口文件。阈值位置见各目录顶层配置；命令见各目录说明文档。组合、分类与评分公式的正式表述见 [`03-formulas-clustering-scoring.md`](03-formulas-clustering-scoring.md)。

## 公共工具（`utils/`）

| 文件 | 职责 |
|------|------|
| `entity_export_config.json` | 图纸路径；各 mode 的 `entity_types`、图层子串与输出文件名 |
| `entity_export.py` | 仓库内唯一直接读取图纸文件的入口；写出根目录 JSON |
| `indep_json.py` | 各图元类型属性序列化 |
| `entities_filter.py` | 按类型、图层筛选模型空间 |
| `entity_json.py` | 读取已导出 JSON，转为各阶段建图用记录 |
| `fix_export_positions.py` | 将异常块参照插入点改为变换后包围盒中心 |
| `paths.py` | 仓库根路径、相对路径解析 |
| `graph_io.py` | 拓扑图读写公共辅助 |
| `attach_geometry.py` | 点到线段距离、最近中心线 |
| `attach_centerlines.py` | 中心线目录、关联距离阈值推断 |
| `text_clean.py` | 文字清洗、多行文字明文 |
| `stats.py` | 字高中位数等统计 |
| `plot_font.py` | 核对图中文字体 |

## 第一阶段甲（`step1a/`）

| 文件 | 职责 |
|------|------|
| `config.py` | 本阶段全部阈值与产物路径 |
| `0_retrieved_elements_graph.py` | 文字 JSON → 标注关系图；建链核对后暂停 |
| `1_extract_retrieval_templates.py` | 图例 JSON → 标注用图例模板 |
| `2_retrieval_rules.py` | 标注关系图 + 图例模板 → 识别规则 |
| `3_apply_retrieval_rules.py` | 标注关系图 + 识别规则 → 候选组图 |
| `4_final_clusters.py` | 候选组图 → 最终组图 |
| `graph_nodes.py` | 标注节点与邻接、绑定边构建 |
| `geometry_fingerprint.py` | 图例几何与距离辅助 |
| `text_roles.py` | 文字角色与图例标题分类 |
| `candidate_scoring.py` | 候选成员打分 |
| `filter_candidates.py` | 候选到最终组的独占过滤 |
| `graph_io.py` | 本阶段图读写与可读摘要 |
| `visualize_clusters.py` | 建链与组核对图 |

## 第一阶段乙（`step1b/`）

| 文件 | 职责 |
|------|------|
| `config.py` | 关联统计阈值与产物路径 |
| `0_structure_graph_with_texts.py` | 中心线结构图 + 最终组图 → 带标注结构图 |
| `1_visualize.py` | 带标注结构图核对图 |
| `build_fusion.py` | 组与巷道名称关联实现 |
| `graph_io.py` | 本阶段图读写 |
| `visualize.py` | 绘图实现 |

## 第二阶段（`stage2/`）

| 文件 | 职责 |
|------|------|
| `config.py` | 本阶段全部阈值与产物路径 |
| `0_facility_primitives_graph.py` | 设施 JSON → 设施图元图 |
| `2_build_facility_graph.py` | 设施图元图 → 设施实例图 |
| `3_structure_graph_with_facilities.py` | 带标注结构图 + 设施实例图 → 带设施结构图与核对图 |
| `4_visualize.py` | 设施实例图与带设施结构图核对图（可单独重绘） |
| `endpoint_connect.py` | 端点连接与孤立图元并入 |
| `cluster_facilities.py` | 组合与实例指纹 |
| `build_attach.py` | 设施关联到中心线 |
| `dxf_primitives.py` | 设施尺度与图元几何辅助（读 JSON 记录，不读图纸） |
| `graph_io.py` | 本阶段图读写 |
| `visualize.py` | 绘图实现 |

说明：`stage2/shuoming.txt` 为第二阶段运行说明的纯文本副本，内容应与 `stage2/readme.md` 及现行脚本一致。

## 第一阶段总述与其它

| 路径 | 说明 |
|------|------|
| `stage1/readme.md` | 第一阶段甲、乙计算逻辑与设计动机（不含操作命令细节） |
| `stage1/nodes.py` 等 | 早期邻接实验；不参与现行主数据流 |
| `example_code_from_5.29/` | 历史参考代码；非现行入口 |

## 逻辑拓扑图与附属文件

完整步骤的主产物为逻辑拓扑图（二进制与可读摘要）。下列文件为附属标定结果，不是拓扑图，但现行脚本会读写：

- 标注用图例模板、识别规则（第一阶段甲）

关联类完整步骤当前同时读入「底图拓扑」与「待关联拓扑」，与《重要原则》第 7 条尚有差距，见 `docs/01-architecture.md` 第六节。
