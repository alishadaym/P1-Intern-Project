import os

from flask import Flask, abort, render_template, session

from locations import LOCATIONS

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")


@app.route("/")
def index():
    current = session.get("current_location")
    return render_template("index.html", current=LOCATIONS.get(current), current_name=current)


@app.route("/location/<name>")
def location(name):
    if name not in LOCATIONS:
        abort(404)

    session["current_location"] = name
    return render_template("location.html", name=name, location=LOCATIONS[name])


@app.route("/shops")
def shops():
    current_name = session.get("current_location")
    current = LOCATIONS.get(current_name)
    return render_template("shops.html", current=current)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
