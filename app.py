from flask import Flask, jsonify, request, render_template
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

@app.route("/api/shops/search", methods=["GET"])
def search_shops():
    search_query = request.args.get("q", "").strip()

    if not search_query:
        return jsonify({
            "error": "Search query is required"
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            s.id,
            s.shop_name,
            s.category,
            s.unit,
            s.description,
            s.floor_id,
            f.floor_name,
            f.floor_code,
            s.x_position,
            s.y_position
        FROM shops s
        JOIN floors f ON s.floor_id = f.id
        WHERE
            s.shop_name LIKE %s
            OR s.category LIKE %s
            OR s.unit LIKE %s
    """

    search_pattern = f"%{search_query}%"

    cursor.execute(
        query,
        (search_pattern, search_pattern, search_pattern)
    )

    shops = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(shops)

# the <int:shop_id> means the URL contains the shop's ID
@app.route("/api/shops/<int:shop_id>", methods=["PUT"])
def update_shop(shop_id):
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
        UPDATE shops
        SET
            shop_name = %s,
            category = %s,
            unit = %s,
            description = %s,
            floor_id = %s,
            x_position = %s,
            y_position = %s
        WHERE id = %s
    """

    values = (
        shop_name,
        category,
        unit,
        description,
        floor_id,
        x_position,
        y_position,
        shop_id
    )

    cursor.execute(query, values)
    connection.commit()

    if cursor.rowcount == 0:
        cursor.close()
        connection.close()

        return jsonify({
            "error": "Shop not found"
        }), 404

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Shop updated successfully",
        "shop_id": shop_id
    })

@app.route("/api/shops/<int:shop_id>", methods=["DELETE"])
def delete_shop(shop_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    # find shop whose id matches the ID from URL and delete it
    query = "DELETE FROM shops WHERE id = %s"

    cursor.execute(query, (shop_id,))
    connection.commit()

    if cursor.rowcount == 0:
        cursor.close()
        connection.close()

        return jsonify({
            "error": "Shop not found"
        }), 404

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Shop deleted successfully",
        "shop_id": shop_id
    })

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

@app.route("/add-shop")
def add_shop_page():
    return render_template("add_shop.html")

@app.route("/api/floors", methods=["GET"])
def get_floors():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM floors ORDER BY id")

    floors = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(floors)

if __name__ == "__main__":
    app.run(debug=True)