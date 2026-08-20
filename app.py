import os
import uuid

from flask import Flask, abort, render_template, session

from locations import LOCATIONS, MAP_WIDTH, MAP_HEIGHT, SHOPS
from scan_log import read_scans, record_scan

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")


def get_session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex
    return session["session_id"]


@app.route("/")
def index():
    current = session.get("current_location")
    return render_template("index.html", current=LOCATIONS.get(current), current_name=current)


@app.route("/location/<name>")
def location(name):
    if name not in LOCATIONS:
        abort(404)

    previous_location = session.get("current_location")
    session["last_location"] = previous_location
    session["current_location"] = name
    record_scan(name, get_session_id(), previous_location)
    return render_template(
        "location.html",
        name=name,
        location=LOCATIONS[name],
        map_width=MAP_WIDTH,
        map_height=MAP_HEIGHT,
        shops=SHOPS,
        last_location=LOCATIONS.get(previous_location),
    )


@app.route("/scans")
def scans():
    return render_template("scans.html", scans=read_scans(), locations=LOCATIONS)


@app.route("/shops")
def shops():
    current_name = session.get("current_location")
    current = LOCATIONS.get(current_name)
    return render_template("shops.html", current=current)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
