import json

with open("1211combine3view_no_fix.json", "r", encoding="utf-8") as f:
    merged = json.load(f)

missing_left = []
missing_front = []

for item in merged:
    circle_id = item["circle_id"]
    sources = item["sources"]

    has_left = any(s["source"] == "left" for s in sources)
    has_front = any(s["source"] == "front" for s in sources)

    if not has_left:
        missing_left.append(circle_id)
    if not has_front:
        missing_front.append(circle_id)

print("Circles missing LEFT data:", missing_left)
print("Circles missing FRONT data:", missing_front)

"""
Circles missing LEFT data: [38, 37, 36, 35, 34, 33, 32, 29, 24, 41, 42, 43, 44, 45, 46, 47, 21, 18, 17, 12, 15, 16]
Circles missing FRONT data: [28, 29, 24, 25, 21, 20, 17, 12, 13, 16]
 """
