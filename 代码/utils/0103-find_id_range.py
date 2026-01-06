import json
from collections import defaultdict

from collections import defaultdict
from typing import List

def get_non_consecutive_groups(input_file: str) -> List[List[int]]:
    """
    Extract and return only the non-consecutive groups based on layer '0' connection lines.
    
    A group is non-consecutive if it contains more than one ID but the IDs do not form
    a strictly consecutive sequence (e.g., [11, 14] has a gap, while [11, 12, 13] does not).
    
    :param input_file: Path to the JSON file containing paired data.
    :return: List of non-consecutive groups, each as a sorted list of integers.
             Groups are sorted by their smallest ID.
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        paired_data = json.load(f)
    
    # Map connection handle -> list of associated IDs
    conn_to_ids = defaultdict(list)
    
    for entry in paired_data:
        for nl in entry.get("nearest_lines", []):
            line_data = nl["line_data"]
            if line_data.get("layer") == "0":
                handle = line_data["handle"]
                conn_to_ids[handle].append(entry["id"])
    
    # Build multi-ID groups (one per connection line)
    multi_groups = []
    for ids in conn_to_ids.values():
        unique_sorted = sorted(set(ids))
        if len(unique_sorted) > 1:
            multi_groups.append(unique_sorted)
    
    # Filter to non-consecutive groups
    non_consecutive_groups = []
    for group in multi_groups:
        is_consecutive = all(group[i + 1] == group[i] + 1 for i in range(len(group) - 1))
        if not is_consecutive:
            non_consecutive_groups.append(group)
    
    # Sort groups by the smallest ID for consistent ordering
    non_consecutive_groups.sort(key=lambda g: g[0])
    
    return non_consecutive_groups

# Example usage
if __name__ == "__main__":
    input_file = r"info\0103rebuild\0103_pair_front.json"  # Adjust path as needed
    non_consec_groups = get_non_consecutive_groups(input_file)
    
    print("Non-consecutive groups:")
    for group in non_consec_groups:
        print(group)
    
    print(f"\nTotal non-consecutive groups found: {len(non_consec_groups)}")