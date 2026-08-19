"""Single source of truth for mall waypoints, shared by the QR generator and the Flask app."""

LOCATIONS = {
    "entrance-main": {"label": "Main Entrance", "floor": "Ground Floor"},
    "escalator-1": {"label": "Escalator (near F.O.S)", "floor": "Ground Floor"},
    "escalator-2": {"label": "Escalator (near SSF)", "floor": "Ground Floor"},
    "escalator-3": {"label": "Escalator (near Good2U, upper)", "floor": "Ground Floor"},
    "escalator-4": {"label": "Escalator (near Good2U, lower)", "floor": "Ground Floor"},
    "atm": {"label": "ATM (near Good2U)", "floor": "Ground Floor"},
    "restroom-1": {"label": "Restroom (near F.O.S)", "floor": "Ground Floor"},
    "restroom-2": {"label": "Restroom (accessible & baby facilities)", "floor": "Ground Floor"},
    "restroom-3": {"label": "Restroom (near SSF)", "floor": "Ground Floor"},
    "restroom-4": {"label": "Restroom (near Good2U)", "floor": "Ground Floor"},
}
