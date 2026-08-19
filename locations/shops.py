"""Clickable store regions on static/map.jpg (pixel boxes, MAP_WIDTH x MAP_HEIGHT).

Listed in the order they should stack when boxes overlap (later = on top).
"""

SHOPS = [
    {"id": "fos", "label": "F.O.S", "box": {"x1": 209, "y1": 37, "x2": 467, "y2": 239}},
    {"id": "tone-mann", "label": "Tone & Mann.", "box": {"x1": 165, "y1": 141, "x2": 317, "y2": 265}},
    {"id": "ssf", "label": "SSF", "box": {"x1": 146, "y1": 234, "x2": 299, "y2": 480}},
    {"id": "good2u", "label": "Good2U", "box": {"x1": 878, "y1": 192, "x2": 987, "y2": 292}},
    {"id": "family-mart", "label": "Family Mart", "box": {"x1": 589, "y1": 418, "x2": 651, "y2": 500}},
    {"id": "zus-coffee", "label": "Zus Coffee", "box": {"x1": 194, "y1": 574, "x2": 319, "y2": 610}},
]
