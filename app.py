from flask import Flask, jsonify, request
from db import get_db_connection

app = Flask(__name__)


@app.route("/")
def home():
    return "DPULZE Mall System is running!"


@app.route("/api/shops")
def get_shops():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM shops")
    shops = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(shops)

#allowing to send data to /api/shops
@app.route("/api/shops", methods=["POST"])
def add_shop():
    # gets information sent by frontend
    data = request.get_json()

    shop_name = data.get("shop_name")
    category = data.get("category")
    unit = data.get("unit")
    description = data.get("description")
    floor_id = data.get("floor_id")
    x_position = data.get("x_position")
    y_position = data.get("y_position")

    if not shop_name or not floor_id:
        return jsonify({
            "error": "Shop name and floor are required"
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        INSERT INTO shops
        (shop_name, category, unit, description, floor_id, x_position, y_position)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        shop_name,
        category,
        unit,
        description,
        floor_id,
        x_position,
        y_position
    )

    cursor.execute(query, values)
    connection.commit()

    new_shop_id = cursor.lastrowid

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Shop added successfully",
        "shop_id": new_shop_id
    }), 201

@app.route("/api/locations/<location_code>", methods=["GET"])
def get_location(location_code):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            l.id,
            l.location_name,
            l.location_code,
            l.floor_id,
            f.floor_name,
            f.floor_code,
            l.x_position,
            l.y_position
        FROM locations l
        JOIN floors f ON l.floor_id = f.id
        WHERE l.location_code = %s
    """

    cursor.execute(query, (location_code,))
    location = cursor.fetchone()

    cursor.close()
    connection.close()

    if location is None:
        return jsonify({
            "error": "Location not found"
        }), 404

    return jsonify(location)


if __name__ == "__main__":
    app.run(debug=True)