from flask import Flask, jsonify, render_template
import json
import os

app = Flask(__name__)

def load_map():
    map_path = os.path.join("data", "map.json")
    with open(map_path, "r", encoding="utf-8") as file:
        return json.load(file)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/map")
def get_map():
    map_data = load_map()
    return jsonify(map_data)

if __name__ == "__main__":
    app.run(debug = True)