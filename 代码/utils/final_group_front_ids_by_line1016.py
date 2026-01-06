import json
import numpy as np
from collections import defaultdict
from typing import List, Dict, Any

from utils.pair_circle_and_line_ids_0103 import parse_ids
from utils.dim_utils_1128 import (
    calculate_line_orientation,
    vector_distance_to_line,
)

# ============================
# CONFIGURATION
# ============================

LABEL_LINE_TOL = 300.0        # 增大容差，适应示意性标注
MIN_STRONG_LABELS = 2         # 形成强组的最小标签数
SLOT_TOL_VERTICAL = 100.0     # 增大Y槽位容差
SLOT_TOL_DIAGONAL = 88.0     
FALLBACK_SCORE_THR = 0.3      # 降低备选阈值
DOMINANCE_RATIO = 1.2         # 降低优势比要求


# ============================
# 增强的几何函数
# ============================
def calculate_global_y_range(labels):
    """
    计算所有标签的全局Y值范围。
    使用分位数避免极端值影响。
    """
    if not labels:
        return 1000, 2000  # 默认范围
    
    y_values = [label["point"][1] for label in labels]
    y_values.sort()
    
    # 使用10%-90%分位数避免离群值
    n = len(y_values)
    lower_idx = max(0, n // 10)      # 10%分位
    upper_idx = min(n-1, n * 9 // 10) # 90%分位
    
    y_min = y_values[lower_idx]
    y_max = y_values[upper_idx]
    
    # 确保最小高度
    if y_max - y_min < 200:
        y_min = min(y_values)
        y_max = max(y_values)
    
    return y_min, y_max


def project_to_line_param(pt, start, end) -> float:
    """投影点到线的参数t在[0, length]范围内"""
    v = end - start
    if np.linalg.norm(v) < 1e-6:
        return 0.0
    v_unit = v / np.linalg.norm(v)
    return np.dot(pt - start, v_unit)


def vector_distance_to_line_signed(pt, start, end):
    """
    计算点到直线的有符号距离。
    正数表示在直线右侧（相对于从start到end的方向）。
    """
    line_vec = end - start
    to_pt_vec = pt - start
    # 二维向量的叉积 (z分量)
    cross_product = line_vec[0] * to_pt_vec[1] - line_vec[1] * to_pt_vec[0]
    # 直线长度
    line_length = np.linalg.norm(line_vec)
    if line_length < 1e-6:
        return 0.0
    # 有符号距离 = 叉积 / 直线长度
    return cross_product / line_length


def is_label_on_correct_side(label_point, line):
    """
    检查标签是否在线的正确一侧。
    规则：右倾线标签在线右边，垂直线和左倾线标签在线左边
    """
    start, end = line["start"], line["end"]
    orientation = line["orientation"]
    
    if orientation == "vertical":
        # 垂直线：标签应在左侧（假设坐标系X向右增大）
        line_x = start[0]
        label_x = label_point[0]
        return label_x < line_x  # True表示在左侧
    
    elif orientation == "diagonal":
        # 判断是左倾还是右倾线
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        
        if dx == 0:  # 实际上是垂直线
            line_x = start[0]
            label_x = label_point[0]
            return label_x < line_x
        
        # 计算有符号距离
        signed_dist = vector_distance_to_line_signed(label_point, start, end)
        
        # 判断线的倾斜方向
        is_right_leaning = (dx > 0 and dy < 0) or (dx < 0 and dy > 0)
        
        if is_right_leaning:  # 右倾线
            return signed_dist > 0  # 标签应在右侧（正距离）
        else:  # 左倾线
            return signed_dist < 0  # 标签应在左侧（负距离）
    
    return True  # 水平线或其他情况，默认通过


def calculate_line_leaning(start, end):
    """判断线的倾斜方向：'left'（左倾）, 'right'（右倾）, 'vertical'（垂直）"""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    
    if abs(dx) < 1.0:
        return "vertical"
    
    # 右倾线：从左下到右上 或 从右上到左下
    # 左倾线：从左上到右下 或 从右下到左上
    if (dx > 0 and dy < 0) or (dx < 0 and dy > 0):
        return "right"
    else:
        return "left"


# ============================
# 数据收集
# ============================

def collect_lines_and_labels(entities):
    lines = []
    labels = []

    for ent in entities:
        if ent["type"] == "LINE" and ent.get("layer") == "15104尾巷图":
            # 检查是否有 linetype 属性
            linetype = ent["attributes"].get("linetype", "BYLAYER")
            if linetype != "BYLAYER":
                continue
            start = np.array(ent["attributes"]["start"][:2])
            end = np.array(ent["attributes"]["end"][:2])
            ori = calculate_line_orientation(start, end)

            if ori == "horizontal":
                continue
            
            # 计算线的倾斜方向
            leaning = calculate_line_leaning(start, end)

            lines.append({
                "handle": ent["handle"],
                "orientation": ori,
                "leaning": leaning,  # 新增：线的倾斜方向
                "start": start,
                "end": end,
                "entity": ent,
                "slots": [],          # 占用的位置
                "assigned": [],       # 已分配的标签
                "candidates": [],     # 候选标签（稍后填充）
                "x_coord": start[0] if ori == "vertical" else None,  # 垂直线的X坐标
            })

        elif ent["type"] == "MTEXT":
            ids = parse_ids(ent["attributes"].get("text", ""))
            if not ids:
                continue

            pt = np.array(ent["attributes"]["insert_point"][:2])
            for idv in ids:
                labels.append({
                    "id": idv,
                    "point": pt,
                    "entity": ent,
                    "assigned": False,
                })

    return lines, labels


# ============================
# STEP 1 — 为每条线收集候选标签，应用方位规则筛选
# ============================

def collect_line_candidates(lines, labels):
    """为每条线收集候选标签，并立即应用方位规则进行初筛"""
    for ln in lines:
        ln["candidates"] = []
        ln["valid_candidates"] = []  # 符合方位规则的候选
        
        for lbl in labels:
            d = vector_distance_to_line(
                lbl["point"],
                ln["start"],
                ln["end"],
            )

            if d <= LABEL_LINE_TOL:
                candidate = {
                    "label": lbl,
                    "distance": d,
                    "param": (
                        lbl["point"][1] if ln["orientation"] == "vertical"
                        else project_to_line_param(lbl["point"], ln["start"], ln["end"])
                    )
                }
                
                # 检查方位规则
                if is_label_on_correct_side(lbl["point"], ln):
                    candidate["side_ok"] = True
                    ln["valid_candidates"].append(candidate)
                else:
                    candidate["side_ok"] = False
                
                ln["candidates"].append(candidate)
        
        # 优先排序有效候选（符合方位规则的）
        ln["valid_candidates"].sort(key=lambda x: x["distance"])
        ln["candidates"].sort(key=lambda x: x["distance"])


# ============================
# 槽位冲突检查（增强版）
# ============================

def slot_conflict(line, param):
    """检查槽位冲突，考虑线的类型"""
    if line["orientation"] == "vertical":
        tol = SLOT_TOL_VERTICAL
    else:
        tol = SLOT_TOL_DIAGONAL
    
    for p in line["slots"]:
        if abs(p - param) <= tol:
            return True
    return False


def occupy_slot(line, param):
    """占用槽位"""
    line["slots"].append(param)


# ============================
# STEP 2 — 强分配（增强版，尽早应用潜规则）
# ============================
def assign_vertical_line_labels(line, labels):
    """
    垂直线专用分配逻辑：确保上下均衡分布
    原则：1. 优先找Y值最大和最小的两个标签（上下占位）
         2. 然后填充中间
         3. 拒绝只有上端或只有下端的分配
    """
    if line["orientation"] != "vertical":
        return False
    
    # 获取所有未分配的候选标签，按Y值排序
    candidates = []
    for c in line["valid_candidates"]:
        if not c["label"]["assigned"]:
            candidates.append(c)
    
    if len(candidates) < 2:
        return False
    
    
    # 按Y值排序
    candidates.sort(key=lambda x: x["label"]["point"][1])
    
    # 策略1：尝试找到上下均衡的一对
    # 计算所有可能的上下组合
    best_pair = None
    best_score = -1
    
    for i in range(len(candidates)):
        for j in range(i+1, len(candidates)):
            bottom_candidate = candidates[i]
            top_candidate = candidates[j]
            # 修复这里：使用正确的路径
            top_candidate_y = top_candidate["label"]["point"][1]
            bottom_candidate_y = bottom_candidate["label"]["point"][1]
            
            # 计算这对组合的"均衡度"
            y_gap =  top_candidate_y-bottom_candidate_y
            y_min, y_max = calculate_global_y_range(labels)
    
            # 理想的Y间隙应该在全局范围的60%以上
            #y_min, y_max = line["global_y_range"]
            ideal_gap = (y_max - y_min) * 0.6
            
            gap_score = 1.0 - min(1.0, abs(y_gap - ideal_gap) / ideal_gap)
            
            # 综合得分：间隙大小 + 距离远近
            avg_distance = (bottom_candidate["distance"] + top_candidate["distance"]) / 2
            distance_score = max(0, 1.0 - avg_distance / LABEL_LINE_TOL)
            
            total_score = gap_score * 0.7 + distance_score * 0.3
            
            if total_score > best_score:
                best_score = total_score
                best_pair = (bottom_candidate, top_candidate)
    
    # 如果找到合适的上下组合，先分配这两个
    if best_pair and best_score > 0.5:
        bottom_c, top_c = best_pair
        
        # 分配底部标签
        if not slot_conflict(line, bottom_c["param"]):
            bottom_c["label"]["assigned"] = True
            line["assigned"].append({
                "id": bottom_c["label"]["id"],
                "label_data": bottom_c["label"]["entity"],
                "mode": "vertical_bottom",
                "param": bottom_c["param"],
                "y": bottom_c["label"]["point"][1],
            })
            occupy_slot(line, bottom_c["param"])
        
        # 分配顶部标签
        if not slot_conflict(line, top_c["param"]):
            top_c["label"]["assigned"] = True
            line["assigned"].append({
                "id": top_c["label"]["id"],
                "label_data": top_c["label"]["entity"],
                "mode": "vertical_top",
                "param": top_c["param"],
                "y": top_c["label"]["point"][1],
            })
            occupy_slot(line, top_c["param"])
        
        # 现在尝试填充中间标签
        fill_vertical_line_middle(line, candidates, bottom_c["label"]["point"][1], top_c["label"]["point"][1])
        
        return True
    
    return False
def fill_vertical_line_middle(line, candidates, bottom_y, top_y):
    """
    为垂直线填充中间标签
    """
    y_range = top_y - bottom_y
    if y_range < 200:  # Y范围太小，不需要中间标签
        return
    
    # 寻找在bottom_y和top_y之间的候选
    middle_candidates = []
    for c in candidates:
        if c["label"]["assigned"]:
            continue
        
        y = c["label"]["point"][1]
        if bottom_y < y < top_y:
            # 计算在范围内的相对位置
            y_ratio = (y - bottom_y) / y_range
            
            # 优先选择接近1/3和2/3位置的标签
            ideal_positions = [0.33, 0.5, 0.67]
            position_score = max(1.0 - abs(y_ratio - pos) / 0.2 for pos in ideal_positions)
            
            middle_candidates.append((position_score, c))
    
    # 按位置得分排序
    middle_candidates.sort(key=lambda x: x[0], reverse=True)
    
    # 根据Y范围大小决定填充几个中间标签
    if y_range > 600:  # 范围很大，可以填2-3个
        target_count = min(3, len(middle_candidates))
    elif y_range > 300:  # 中等范围，填1-2个
        target_count = min(2, len(middle_candidates))
    else:  # 小范围，填0-1个
        target_count = min(1, len(middle_candidates))
    
    for i in range(target_count):
        _, candidate = middle_candidates[i]
        if not slot_conflict(line, candidate["param"]):
            candidate["label"]["assigned"] = True
            line["assigned"].append({
                "id": candidate["label"]["id"],
                "label_data": candidate["label"]["entity"],
                "mode": "vertical_middle",
                "param": candidate["param"],
                "y": candidate["label"]["point"][1],
            })
            occupy_slot(line, candidate["param"])


# ============================
# 修改strong_assign函数
# ============================

def strong_assign(lines):
    """强分配，垂直线使用专用逻辑"""
    # 第一阶段：先处理所有垂直线
    for ln in lines:
        if ln["orientation"] == "vertical":
            success = assign_vertical_line_labels(ln, labels)
            if success:
                print(f"垂直线 {ln['handle']}: 分配了{len(ln['assigned'])}个标签")
    
    # 第二阶段：处理斜线
    for ln in lines:
        if ln["orientation"] == "diagonal" and len(ln["valid_candidates"]) >= 2:
            assign_diagonal_line_labels(ln)


def assign_diagonal_line_labels(line):
    """斜线专用分配逻辑"""
    candidates = []
    for c in line["valid_candidates"]:
        if not c["label"]["assigned"]:
            candidates.append(c)
    
    if len(candidates) < 2:
        return
    
    # 斜线：按沿线投影参数排序
    candidates.sort(key=lambda x: x["param"])
    
    # 尝试分配一组标签，要求它们在沿线方向上分布均匀
    assigned_count = 0
    param_values = []
    
    for c in candidates:
        if assigned_count >= 5:  # 斜线最多4个标签
            break
            
        if c["label"]["assigned"]:
            continue
            
        # 检查与已分配标签的参数间隔
        if param_values:
            min_gap = min(abs(c["param"] - p) for p in param_values)
            if min_gap < 100:  # 太近了
                continue
        
        if slot_conflict(line, c["param"]):
            continue
        
        c["label"]["assigned"] = True
        line["assigned"].append({
            "id": c["label"]["id"],
            "label_data": c["label"]["entity"],
            "mode": "diagonal",
            "param": c["param"],
            "distance": c["distance"],
        })
        occupy_slot(line, c["param"])
        param_values.append(c["param"])
        assigned_count += 1



def extend_strong_group(line):
    """扩展强组，添加更多符合规则的标签"""
    if len(line["assigned"]) == 0:
        return
    
    # 获取已分配标签的Y值范围
    assigned_params = [a["param"] for a in line["assigned"]]
    min_param, max_param = min(assigned_params), max(assigned_params)
    param_range = max_param - min_param
    
    # 寻找可以填补空白的候选
    for c in line["valid_candidates"]:
        if c["label"]["assigned"]:
            continue
        
        param = c["param"]
        
        # 检查是否在已有范围内或可以合理扩展
        if min_param <= param <= max_param:
            # 在范围内，检查是否太靠近已有标签
            min_gap = min(abs(param - p) for p in assigned_params)
            if min_gap < SLOT_TOL_VERTICAL * 0.7:  # 太近了
                continue
        else:
            # 在范围外，检查扩展是否合理
            if param < min_param:
                gap = min_param - param
            else:
                gap = param - max_param
            
            if gap > param_range * 0.5:  # 扩展太大
                continue
        
        if slot_conflict(line, param):
            continue
        
        # 分配这个标签
        c["label"]["assigned"] = True
        line["assigned"].append({
            "id": c["label"]["id"],
            "label_data": c["label"]["entity"],
            "mode": "strong_extension",
            "param": param,
            "distance": c["distance"],
        })
        occupy_slot(line, param)
        
        # 最多扩展到5个标签
        if len(line["assigned"]) >= 5:
            break


# ============================
# STEP 3 — 备选分配（增强版，考虑方位规则）
# ============================

def fallback_assign(lines, labels):
    """备选分配，优先处理底部未分配标签"""
    y_min, y_max = calculate_global_y_range(labels)
    
    # 获取未分配标签并按 Y 坐标排序
    unassigned = [l for l in labels if not l["assigned"]]
    unassigned.sort(key=lambda l: l["point"][1])
    
    for lbl in unassigned:
        scores = []
        lbl_point = lbl["point"]
        lbl_y = lbl_point[1]
        
        # 【重要】在这里重新计算每个标签的属性，修复原代码 Bug
        is_bottom_label = lbl_y < y_min + 200 
        
        for ln in lines:
            # 基础距离过滤
            d = vector_distance_to_line(lbl_point, ln["start"], ln["end"])
            if d > LABEL_LINE_TOL:
                continue
            
            param = (
                lbl_point[1] if ln["orientation"] == "vertical"
                else project_to_line_param(lbl_point, ln["start"], ln["end"])
            )
            
            if slot_conflict(ln, param):
                continue
            
            # 1. 基础距离得分
            Sd = max(0.0, 1.0 - d / LABEL_LINE_TOL)
            
            # 2. 方位规则得分
            if is_label_on_correct_side(lbl_point, ln):
                Sside = 1.0
            else:
                Sside = 0.1  # 维持对方位错误的严厉惩罚
            
            # 3. 【弱分配核心修改】：调整 Sl 权重
            if ln["assigned"]:
                # 已有标签的线获得累加奖励
                Sl = 1.0 + 0.1 * len(ln["assigned"])
                Sx = 1.0 # 这里可以保留原有的 X 相似度逻辑
            else:
                # 弱分配逻辑：给空线条一个合理的基础分，不再是 0.4
                # 0.8 表示虽然没有“强关联”，但依然是一个非常具有竞争力的候选
                Sl = 0.8 
                Sx = 1.0
            
            # 4. 底部标签对垂直线的“弱分配”强引导
            S_bottom = 1.0
            if is_bottom_label and ln["orientation"] == "vertical":
                # 如果垂直线还是空的，给予极高权重的引导
                if not ln["assigned"]:
                    S_bottom = 1.8  # 引导底部标签优先激活空白垂直线
                else:
                    S_bottom = 1.2
            # 4. Y值分布合理性
            Sy = 1.0
            if ln["assigned"]:
                assigned_ys = []
                for assigned in ln["assigned"]:
                    assigned_label = next(
                        (l for l in labels if l["id"] == assigned["id"]), 
                        None
                    )
                    if assigned_label:
                        assigned_ys.append(assigned_label["point"][1])
                
                if assigned_ys:
                    current_y = lbl_point[1]
                    min_y, max_y = min(assigned_ys), max(assigned_ys)
                    
                    if current_y < min_y:
                        gap = min_y - current_y
                        if gap > 250:  # 扩展太大
                            Sy = 0.6
                    elif current_y > max_y:
                        gap = current_y - max_y
                        if gap > 250:
                            Sy = 0.6
                    else:
                        # 在中间，检查是否太近
                        closest_gap = min(abs(current_y - y) for y in assigned_ys)
                        if closest_gap < 60:
                            Sy = 0.7
            
            # 综合得分
            score = Sd * Sside * Sl * Sx * Sy * S_bottom
            scores.append((ln, score, param))
            
        
        if not scores:
            continue
        
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # 决策：使用绝对分数阈值，降低相对优势要求
        if scores[0][1] >= FALLBACK_SCORE_THR:
            # 检查是否有明显更好的选择
            if len(scores) > 1 and scores[0][1] < DOMINANCE_RATIO * scores[1][1]:
                # 优势不明显，检查哪个更符合方位规则
                if (is_label_on_correct_side(lbl_point, scores[0][0]) and 
                    not is_label_on_correct_side(lbl_point, scores[1][0])):
                    # 第一个符合方位规则，第二个不符合，选择第一个
                    pass
                elif (not is_label_on_correct_side(lbl_point, scores[0][0]) and 
                      is_label_on_correct_side(lbl_point, scores[1][0])):
                    # 第一个不符合，第二个符合，选择第二个
                    scores[0], scores[1] = scores[1], scores[0]
            
            ln, score, param = scores[0]
            lbl["assigned"] = True
            ln["assigned"].append({
                "id": lbl["id"],
                "label_data": lbl["entity"],
                "mode": "fallback",
                "score": score,
                "param": param,
            })
            occupy_slot(ln, param)


# ============================
# 输出
# ============================

def build_output(lines, labels):
    groups = []
    floating = []

    for ln in lines:
        if ln["assigned"]:
            # 按参数排序
            sorted_assigned = sorted(ln["assigned"], key=lambda x: x.get("param", 0))
            groups.append({
                "line_handle": ln["handle"],
                "line_orientation": ln["orientation"],
                "line_leaning": ln.get("leaning", "unknown"),
                "line_data": ln["entity"],
                "associated_labels": sorted_assigned,
                "label_count": len(sorted_assigned),
                "label_ids": [x["id"] for x in sorted_assigned],
            })

    for lbl in labels:
        if not lbl["assigned"]:
            floating.append(lbl["id"])

    return {
        "groups": groups,
        "floating": sorted(floating),
    }


# ============================
# 主函数
# ============================

def print_summary(lines, labels):
    print("\n========== 分组结果汇总 ==========")
    print(f"总线条数: {len(lines)}")
    print(f"总标签数: {len(labels)}")
    
    unassigned_lines = []
    assigned_lines = []
    
    for ln in lines:
        if not ln["assigned"]:
            unassigned_lines.append(ln)
        else:
            assigned_lines.append(ln)
    
    print(f"\n已分配线条: {len(assigned_lines)}")
    for ln in assigned_lines:
        label_ids = [x["id"] for x in ln["assigned"]]
        print(f"  线 {ln['handle']} ({ln['orientation']}, {ln.get('leaning', 'unknown')}): {len(label_ids)}个标签 - {sorted(label_ids)}")
    
    print(f"\n未分配线条: {len(unassigned_lines)}")
    if unassigned_lines:
        for ln in unassigned_lines[:10]:  # 只显示前10个
            print(f"  线 {ln['handle']} ({ln['orientation']})")
        if len(unassigned_lines) > 10:
            print(f"  ... 还有{len(unassigned_lines)-10}条未显示")
    
    floating = [lbl["id"] for lbl in labels if not lbl["assigned"]]
    print(f"\n未分配标签: {len(floating)}个")
    if floating:
        print(f"  {sorted(floating)}")


if __name__ == "__main__":
    # 读取数据
    with open(r"info\0105new-export\LINE_export_front.json", "r", encoding="utf-8") as f:
        line_entities = json.load(f)
    
    with open(r"info\0105new-export\MTEXT_export_front.json", "r", encoding="utf-8") as f:
        mtext_entities = json.load(f)
    
    # 合并实体
    entities = line_entities + mtext_entities

    # 执行分组
    lines, labels = collect_lines_and_labels(entities)
    collect_line_candidates(lines, labels)
    strong_assign(lines)
    fallback_assign(lines, labels)
    
    # 打印汇总
    print_summary(lines, labels)
    
    # 保存结果
    result = build_output(lines, labels)
    with open(r"info\0105new-export\linetype_enhanced_pair_front.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print("\n结果已保存到 linetype_enhanced_pair_front.json")