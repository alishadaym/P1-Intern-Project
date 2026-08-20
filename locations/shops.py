"""Clickable store regions on static/map.jpg (pixel boxes, MAP_WIDTH x MAP_HEIGHT).

Boxes were measured from static/map.jpg directly where possible (connected-component
analysis of the plain map), and otherwise derived from static/map_labeled_reference.jpg
(a separately labeled version of the same floor plan) via an affine transform fitted on
7 shared icon landmarks (escalators/restrooms/ATM) that are precisely detectable in both
images.

Listed in the order they should stack when boxes overlap (later = on top).
"""

SHOPS = [
    {"id": "fos", "label": "F.O.S", "box": {"x1": 209, "y1": 37, "x2": 467, "y2": 239}},
    {"id": "tone-mann", "label": "Tone & Mann.", "box": {"x1": 165, "y1": 141, "x2": 317, "y2": 265}},
    {"id": "ssf", "label": "SSF", "box": {"x1": 146, "y1": 234, "x2": 299, "y2": 480}},
    {"id": "good2u", "label": "Good2U", "box": {"x1": 878, "y1": 192, "x2": 987, "y2": 292}},
    {"id": "family-mart", "label": "Family Mart", "box": {"x1": 589, "y1": 418, "x2": 651, "y2": 500}},
    {"id": "zus-coffee", "label": "Zus Coffee", "box": {"x1": 194, "y1": 574, "x2": 319, "y2": 610}},
    {"id": "ajumma", "label": "Ajumma", "box": {"x1": 405, "y1": 204, "x2": 436, "y2": 229}},
    {"id": "elianto", "label": "Elianto", "box": {"x1": 434, "y1": 206, "x2": 475, "y2": 239}},
    {"id": "mi-store", "label": "Mi Store", "box": {"x1": 487, "y1": 200, "x2": 516, "y2": 223}},
    {"id": "world-of-perfumes", "label": "World of Perfumes", "box": {"x1": 533, "y1": 205, "x2": 574, "y2": 244}},
    {"id": "jacs-optometry", "label": "Jac's Optometry", "box": {"x1": 568, "y1": 200, "x2": 616, "y2": 274}},
    {"id": "mnb", "label": "MNB", "box": {"x1": 676, "y1": 158, "x2": 712, "y2": 253}},
    {"id": "mc-vogue", "label": "MC Vogue", "box": {"x1": 716, "y1": 165, "x2": 752, "y2": 253}},
    {"id": "kunzense-bodyline", "label": "Kunzense Bodyline", "box": {"x1": 757, "y1": 172, "x2": 793, "y2": 253}},
    {"id": "skechers", "label": "Skechers", "box": {"x1": 797, "y1": 178, "x2": 833, "y2": 253}},
    {"id": "hong-leong", "label": "Hong Leong Islamic Bank", "box": {"x1": 834, "y1": 194, "x2": 864, "y2": 228}},
    {"id": "jewellery-kiosk", "label": "Sparkle & Silver Fine Jewellery", "box": {"x1": 603, "y1": 250, "x2": 636, "y2": 269}},
    {"id": "parca-fashion", "label": "Parca Fashion", "box": {"x1": 422, "y1": 254, "x2": 500, "y2": 309}},
    {"id": "maxis", "label": "Maxis", "box": {"x1": 651, "y1": 291, "x2": 669, "y2": 322}},
    {"id": "royal-sporting-house", "label": "Royal Sporting House", "box": {"x1": 896, "y1": 306, "x2": 936, "y2": 334}},
    {"id": "starbucks", "label": "Starbucks", "box": {"x1": 700, "y1": 320, "x2": 779, "y2": 351}},
    {"id": "sarong-by-ar", "label": "Sarong By A&R", "box": {"x1": 318, "y1": 332, "x2": 357, "y2": 374}},
    {"id": "solight", "label": "Solight", "box": {"x1": 366, "y1": 339, "x2": 399, "y2": 354}},
    {"id": "nandos", "label": "Nando's", "box": {"x1": 399, "y1": 339, "x2": 432, "y2": 354}},
    {"id": "al-ikhsan-sports", "label": "Al-Ikhsan Sports", "box": {"x1": 434, "y1": 339, "x2": 474, "y2": 360}},
    {"id": "baskin-robbins", "label": "Baskin Robbins", "box": {"x1": 483, "y1": 338, "x2": 517, "y2": 360}},
    {"id": "coffee-bean", "label": "The Coffee Bean & Tea Leaf", "box": {"x1": 525, "y1": 359, "x2": 563, "y2": 445}},
    {"id": "the-body-shop", "label": "The Body Shop", "box": {"x1": 589, "y1": 375, "x2": 616, "y2": 426}},
    {"id": "sox-world", "label": "Sox World", "box": {"x1": 620, "y1": 375, "x2": 651, "y2": 415}},
    {"id": "mr-dakgalbi", "label": "Mr. Dakgalbi", "box": {"x1": 671, "y1": 373, "x2": 713, "y2": 499}},
    {"id": "go-noodle-house", "label": "Go Noodle House", "box": {"x1": 716, "y1": 373, "x2": 758, "y2": 499}},
    {"id": "happikiddo", "label": "Happikiddo", "box": {"x1": 761, "y1": 373, "x2": 803, "y2": 499}},
    {"id": "homes-harmony", "label": "Home's Harmony", "box": {"x1": 806, "y1": 373, "x2": 857, "y2": 499}},
]
