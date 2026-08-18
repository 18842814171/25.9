# stage2 — 共用几何库

本目录仅包含 **step2A / step2B 共用的 Python 模块**，不提供命令行入口。运行脚本请使用各步骤目录下的 `run_*.py`。

## Step 2A / Step 2B 概述

Step 2A 与 Step 2B 构成巷道几何的结构化预处理两阶段。Step 2A 因原始 CAD 图元混有圆弧与直线、折角信息隐于弧端连接而设立，目标为检测并记录方折，对圆角弧段进行置信度分类后仅对高可信 fillet 消弧裁端，将几何统一为直线段并建立端点邻接图；识别与修改分步执行，连续墙合并留待下游。Step 2B 承接上述产物，针对墙线仍以局部碎片存在、缺乏宏观巷道骨架的问题，通过近共线链合并直墙、分流残余线段，并依据墙间距与投影重叠建立逻辑连接图、划分平行墙组；本步不涉及洞室、横档等细部语义。最终产出直墙几何、残余几何及平行图三类结构化结果，供 Step 3 开展细节识别并与主线衔接。

---

## 目录结构

```text
stage2/
├── geometry.py       # 图元提取、端点连接图、wall_lines 转换
├── graph_usage.py    # 端点图段列表、碎线提取
├── io.py             # JSON / 图持久化
└── visualize.py      # 墙线、碎线聚类绘图（供库调用）
```

---

## 命令行入口（唯一路径）

| 步骤 | 脚本 |
|------|------|
| Step 2A 初始化图 | `python step2A/run_init_graph.py --geo ... --stem ...` |
| Step 2A 方折检测 | `python step2A/square_bend.py --stem ...` |
| Step 2A 圆角检测 | `python step2A/arc_bend_detect.py --stem ...` |
| Step 2A 圆角裁端 | `python step2A/arc_normalize.py --stem ...` |
| Step 2A 总览图 | `python step2A/run_overview.py --stem ...` |
| Step 2B 碎线聚类 |` |
| Step 2B 墙线可视化 |  |

详细说明见 `step2A/README.md`、`step2B/README.md`。
