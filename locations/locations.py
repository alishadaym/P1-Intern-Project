"""Single source of truth for mall waypoints, shared by the QR generator and the Flask app.

`map` coordinates are pixel positions on static/map.jpg, which is MAP_WIDTH x MAP_HEIGHT.
"""

MAP_WIDTH = 1080
MAP_HEIGHT = 628

LOCATIONS = {
    "entrance-main": {"label": "Main Entrance", "floor": "Ground Floor", "map": {"x": 549, "y": 460}},
    "escalator-1": {"label": "Escalator (upper, near Good2U)", "floor": "Ground Floor", "map": {"x": 648, "y": 197}},
    "escalator-2": {"label": "Escalator (near Main Entrance)", "floor": "Ground Floor", "map": {"x": 463, "y": 280}},
    "escalator-3": {"label": "Escalator (near Family Mart)", "floor": "Ground Floor", "map": {"x": 739, "y": 301}},
    "escalator-4": {"label": "Escalator (lower, near Good2U)", "floor": "Ground Floor", "map": {"x": 876, "y": 388}},
    "atm": {"label": "ATM (near Good2U)", "floor": "Ground Floor", "map": {"x": 855, "y": 271}},
    "restroom-1": {"label": "Restroom (near F.O.S)", "floor": "Ground Floor", "map": {"x": 264, "y": 137}},
    "restroom-2": {"label": "Restroom (accessible & baby facilities)", "floor": "Ground Floor", "map": {"x": 533, "y": 150}},
    "restroom-3": {"label": "Restroom (near SSF)", "floor": "Ground Floor", "map": {"x": 334, "y": 420}},
    "restroom-4": {"label": "Restroom (near Good2U)", "floor": "Ground Floor", "map": {"x": 901, "y": 388}},
}
