import json
from collections import defaultdict
from pathlib import Path

# =========================
# CONFIG
# =========================
FRONT_ENHANCED_FILE = r"info\0105new-export\linetype_enhanced_pair_front.json"  # 前端直线组数据
NON_CONSECUTIVE_FILE = r"info\0103rebuild\0103_return_nonconsecutive.json"  # 非连续组定义
OUTPUT_FILE = r"info\0105new-export\0106_completed_front_groups.json"

# =========================
# HELPERS
# =========================
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def expand_non_consecutive_groups(non_consecutive_data):
    """
    将非连续组展开为完整的标签范围，并记录每个组对应的完整标签列表。
    例如：[[11, 14]] -> {11: [11, 12, 13, 14], 12: [11, 12, 13, 14], ...}
    """
    label_to_full_group = {}
    non_consecutive_groups = non_consecutive_data.get("non_consecutive_groups", [])
    
    for start, end in non_consecutive_groups:
        full_group = list(range(start, end + 1))
        for label in full_group:
            label_to_full_group[str(label)] = full_group
    
    return label_to_full_group

# =========================
# MAIN
# =========================
def enhance_front_groups_with_completion(front_data, non_consecutive_data):
    """
    增强前端直线组数据，补全非连续组中缺失的标签。
    """
    # 获取标签到完整组的映射
    label_to_full_group = expand_non_consecutive_groups(non_consecutive_data)
    
    # 创建标签到直线组的映射
    label_to_line_info = {}
    line_groups_info = []
    
    # 首先，收集所有直线组的信息
    for group in front_data.get("groups", []):
        line_handle = group["line_handle"]
        line_data = group["line_data"]
        label_ids = group["label_ids"]
        
        # 存储直线组信息
        line_group_info = {
            "line_handle": line_handle,
            "line_orientation": group["line_orientation"],
            "line_leaning": group["line_leaning"],
            "line_data": line_data,
            "original_label_ids": label_ids.copy(),  # 原始标签
            "completed_label_ids": label_ids.copy(),  # 将补全的标签
            "associated_labels": group["associated_labels"].copy()
        }
        line_groups_info.append(line_group_info)
        
        # 建立标签到直线组的映射
        for label_id in label_ids:
            label_str = str(label_id)
            if label_str not in label_to_line_info:
                label_to_line_info[label_str] = []
            label_to_line_info[label_str].append(line_group_info)
    
    # 补全非连续组中的缺失标签
    for label_str, full_group in label_to_full_group.items():
        # 检查这个标签是否已经存在于某个直线组中
        if label_str in label_to_line_info:
            # 这个标签已经存在于直线组中
            for line_group in label_to_line_info[label_str]:
                # 补全该直线组中缺失的同组标签
                for label_num in full_group:
                    label_num_str = str(label_num)
                    if label_num not in line_group["completed_label_ids"]:
                        line_group["completed_label_ids"].append(label_num)
                        
                        # 创建虚拟的关联标签信息
                        virtual_label = {
                            "id": label_num,
                            "label_data": {
                                "handle": f"VIRTUAL_{label_num}",
                                "type": "MTEXT",
                                "layer": line_group["line_data"]["layer"],
                                "attributes": {
                                    "text": str(label_num),
                                    "insert_point": [0, 0, 0],  # 虚拟位置
                                    "char_height": 100.0,
                                    "rotation": 0
                                }
                            },
                            "mode": "virtual",
                            "score": 0.0,
                            "param": 0.0,
                            "note": "filled consecutive label"
                        }
                        line_group["associated_labels"].append(virtual_label)
    
    # 构建输出结构
    enhanced_groups = []
    for line_group in line_groups_info:
        enhanced_group = {
            "line_handle": line_group["line_handle"],
            "line_orientation": line_group["line_orientation"],
            "line_leaning": line_group["line_leaning"],
            "line_data": line_group["line_data"],
            "associated_labels": line_group["associated_labels"],
            "label_count": len(line_group["associated_labels"]),
            "original_label_ids": line_group["original_label_ids"],
            "completed_label_ids": sorted(line_group["completed_label_ids"]),
            "completed_count": len(line_group["completed_label_ids"])
        }
        enhanced_groups.append(enhanced_group)
    
    # 计算统计信息
    original_total = sum(len(g["original_label_ids"]) for g in enhanced_groups)
    completed_total = sum(len(g["completed_label_ids"]) for g in enhanced_groups)
    
    # 构建完整输出
    result = {
        "enhanced_groups": enhanced_groups,
        "statistics": {
            "total_groups": len(enhanced_groups),
            "original_total_labels": original_total,
            "completed_total_labels": completed_total,
            "added_virtual_labels": completed_total - original_total
        },
        "non_consecutive_groups": non_consecutive_data.get("non_consecutive_groups", []),
        "singletons": non_consecutive_data.get("singletons", [])
    }
    
    return result

# =========================
# ENTRY
# =========================
if __name__ == "__main__":
    # 加载数据
    front_data = load_json(FRONT_ENHANCED_FILE)
    non_consecutive_data = load_json(NON_CONSECUTIVE_FILE)
    
    # 处理数据
    result = enhance_front_groups_with_completion(front_data, non_consecutive_data)
    
    # 保存结果
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    # 打印统计信息
    stats = result["statistics"]
    print(f"[OK] 增强后的直线组已保存到 → {OUTPUT_FILE}")
    print(f"     直线组数量: {stats['total_groups']}")
    print(f"     原始标签数量: {stats['original_total_labels']}")
    print(f"     补全后标签数量: {stats['completed_total_labels']}")
    print(f"     新增虚拟标签: {stats['added_virtual_labels']}")
    
    # 打印每个直线组的补全情况
    print("\n各直线组补全情况:")
    for i, group in enumerate(result["enhanced_groups"]):
        original = len(group["original_label_ids"])
        completed = len(group["completed_label_ids"])
        if completed > original:
            print(f"  组 {i+1} (句柄: {group['line_handle']}): {original} → {completed} 个标签")
            added_labels = [l for l in group["completed_label_ids"] if l not in group["original_label_ids"]]
            print(f"      新增标签: {added_labels}")