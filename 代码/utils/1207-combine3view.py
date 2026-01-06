import json
from collections import defaultdict

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def integrate_circle_views(input_file, output_file):

    raw = load_json(input_file)

    # dictionary: id → {"top":{}, "left":{}, "front":{}}
    merged = defaultdict(lambda: {"top": None, "left": None, "front": None})

    current_id = None

    for entry in raw:
        # detect circle_id block starter
        if "circle_id" in entry:
            current_id = entry["circle_id"]
            continue
        
        # must have source key
        src = entry.get("source")
        if current_id is None or src not in ("top", "left", "front"):
            continue
        
        # Copy entire dict as-is
        merged[current_id][src] = entry

    # Save
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)

    print(f"Merged circles saved to {output_file}")

if __name__ == "__main__":
    integrate_circle_views(
        "file1_top.json",
        "file2_left.json",
        "file3_front.json",
        "merged_circle_views.json"
    )
"""example"""
[{"circle_id":1},
    {   "source":"top",
        "handle": "3DA",
        "type": "CIRCLE",
        "layer": "15104尾巷图",
        "group": null,
        "attributes": {
            "center": [
                2404.000621397938,
                923.9055741993291,
                0.0
            ],
            "radius": 40.0,
            "associated_label": "1",
            "label_distance": 77.89341868793302,
            "label_handle": "3F7"
        }
    },
{
    "source":"front",
    "nearest_line": "3DA",
    "line_data": {
      "handle": "3DA",
      "type": "LINE",
      "layer": "15104Î²ÏïÍ¼",
      "attributes": {
        "start": [
          2183.970720627192,
          701.7315894178118,
          0.0
        ],
        "end": [
          6383.970720627193,
          701.7315894178118,
          0.0
        ]
      }
    }
  },
{
    "source":"left",
    "nearest_line": "36D",
    "line_data": {
      "handle": "36D",
      "type": "LINE",
      "layer": "15104尾巷图",
      "group": null,
      "attributes": {
        "start": [
          1500.0000000001146,
          0.0,
          0.0
        ],
        "end": [
          1500.0000000001146,
          2900.0000000001155,
          0.0
        ]
      }
    }
  }
  ]