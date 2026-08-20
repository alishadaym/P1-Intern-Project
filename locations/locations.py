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

# Maps each QR-scannable location to the nearest node in data/map.json's
# pathfinding graph, so a scan can set the user's starting point for
# navigation. Matched by transforming this file's map.jpg pixel coordinates
# into static/img/dpulze_ground_floor.png's coordinate space (the two images
# are the same floor plan at a slightly different crop/scale) and picking
# each node graph's closest point.
NODE_MAP = {
    "entrance-main": "node_01",
    "escalator-1": "node_17",
    "escalator-2": "node_33",
    "escalator-3": "node_35",
    "escalator-4": "node_24",
    "atm": "node_21",
    "restroom-1": "node_09",
    "restroom-2": "node_13",
    "restroom-3": "node_07",
    "restroom-4": "node_24",
}
