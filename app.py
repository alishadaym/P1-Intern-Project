from flask import Flask, abort, jsonify, request, render_template, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection
from locations import LOCATIONS, MAP_WIDTH, MAP_HEIGHT, SHOPS, NODE_MAP
from scan_log import read_scans, record_scan
from simulate_occupancy import run_simulator

import json
import os
import secrets
import threading
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

# Keeps restroom occupancy changing for visitors without needing real foot
# traffic. Runs in-process rather than as a separate Render service, so it
# only makes sense with a single app worker - gunicorn's default (see
# Procfile) - since multiple workers would each run their own simulation
# and fight over the same cubicles.
threading.Thread(target=run_simulator, daemon=True).start()

GENERAL_VOUCHER_TYPES = {
    "parking": "Parking Voucher",
}

def load_map():
    map_path = os.path.join("data", "map.json")
    with open(map_path, "r", encoding="utf-8") as file:
        return json.load(file)

@app.route("/api/map")
def get_map():
    map_data = load_map()
    return jsonify(map_data)

@app.route("/api/shops")
def get_shops():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            s.id,
            s.shop_code,
            s.shop_name,
            s.operating_hours,
            s.category,
            s.unit,
            s.description,
            s.floor_id,
            f.floor_name,
            f.floor_code
        FROM shops s
        JOIN floors f
            ON s.floor_id = f.id
        ORDER BY s.shop_name
    """

    cursor.execute(query)
    shops = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(shops)

@app.route("/api/categories")
def get_categories():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT DISTINCT TRIM(category) AS category
        FROM shops
        WHERE category IS NOT NULL AND TRIM(category) <> ''
        ORDER BY category
    """)
    categories = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(categories)

@app.route("/api/utilities")
def get_utilities():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            u.id AS utility_id,
            u.map_code,
            u.name,
            CASE
                WHEN u.utility_type = 'toilet' THEN 'restroom'
                ELSE u.utility_type
            END AS type,
            u.floor,
            COUNT(c.id) AS total_cubicles,
            COALESCE(SUM(LOWER(c.status) = 'occupied'), 0) AS occupied_cubicles
        FROM utilities u
        LEFT JOIN cubicles c ON c.utility_id = u.id
        GROUP BY u.id, u.name, u.utility_type, u.floor
        ORDER BY u.utility_type, u.name
    """)
    utilities = cursor.fetchall()

    cursor.close()
    connection.close()

    map_facilities = load_map().get("facilities", {})

    for utility in utilities:
        utility["utility_code"] = str(utility.pop("utility_id"))
        utility["total_cubicles"] = int(utility["total_cubicles"] or 0)
        utility["occupied_cubicles"] = int(utility["occupied_cubicles"] or 0)
        utility["available_cubicles"] = (
            utility["total_cubicles"] - utility["occupied_cubicles"]
        )
        utility["is_occupied"] = utility["type"] == "oku" and utility["occupied_cubicles"] > 0

        facility = map_facilities.get(utility["map_code"])
        if facility:
            utility.update({
                "x": facility["x"],
                "y": facility["y"],
                "node_id": facility["node_id"]
            })

    return jsonify(utilities)

#allowing to send data to /api/shops
@app.route("/api/shops", methods=["POST"])
def add_shop():
    # gets information sent by frontend
    data = request.get_json()

    shop_name = data.get("shop_name")
    operating_hours = data.get("operating_hours")
    category = data.get("category")
    unit = data.get("unit")
    description = data.get("description")
    floor_id = data.get("floor_id")

    if not shop_name or not floor_id:
        return jsonify({
            "error": "Shop name and floor are required"
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        INSERT INTO shops
        (shop_name, operating_hours, category, unit, description, floor_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """

    values = (
        shop_name,
        operating_hours,
        category,
        unit,
        description,
        floor_id
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
            s.shop_code,
            s.shop_name,
            s.operating_hours,
            s.category,
            s.unit,
            s.description,
            s.floor_id,
            f.floor_name,
            f.floor_code
        FROM shops s
        JOIN floors f ON s.floor_id = f.id
        WHERE
            s.shop_name LIKE %s
            OR s.category LIKE %s
    """

    search_pattern = f"%{search_query}%"

    cursor.execute(
        query,
        (search_pattern, search_pattern)
    )

    shops = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(shops)

# the <int:shop_id> means the URL contains the shop's ID
@app.route("/api/shops/<int:shop_id>", methods=["PUT"])
def update_shop(shop_id):

    # Check if store owner is logged in
    if "owner_id" not in session:
        return jsonify({
            "error": "Login required"
        }), 401

    # Make sure this owner owns this shop
    if session["shop_id"] != shop_id:
        return jsonify({
            "error": "You are not authorized to edit this shop"
        }), 403

    data = request.get_json()

    shop_name = data.get("shop_name")
    operating_hours = data.get("operating_hours")
    category = data.get("category")
    unit = data.get("unit")
    description = data.get("description")
    floor_id = data.get("floor_id")

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
            operating_hours = %s,
            category = %s,
            unit = %s,
            description = %s,
            floor_id = %s
        WHERE id = %s
    """

    values = (
        shop_name,
        operating_hours,
        category,
        unit,
        description,
        floor_id,
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

@app.route("/api/shops/<int:shop_id>", methods=["GET"])
def get_shop(shop_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            s.id,
            s.shop_code,
            s.shop_name,
            s.operating_hours,
            s.category,
            s.unit,
            s.description,
            s.floor_id,
            f.floor_name,
            f.floor_code
        FROM shops s
        JOIN floors f ON s.floor_id = f.id
        WHERE s.id = %s
    """

    cursor.execute(query, (shop_id,))
    shop = cursor.fetchone()

    cursor.close()
    connection.close()

    if shop is None:
        return jsonify({
            "error": "Shop not found"
        }), 404

    return jsonify(shop)

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

@app.route("/api/navigation", methods=["GET"])
def get_navigation():
    location_code = request.args.get("from")
    shop_id = request.args.get("shop_id")

    if not location_code or not shop_id:
        return jsonify({
            "error": "Location code and shop ID are required"
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Get user's scanned location
    location_query = """
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

    cursor.execute(location_query, (location_code,))
    user_location = cursor.fetchone()

    if user_location is None:
        cursor.close()
        connection.close()

        return jsonify({
            "error": "Starting location not found"
        }), 404

    # Get destination shop
    shop_query = """
        SELECT
            s.id,
            s.shop_code,
            s.shop_name,
            s.floor_id,
            f.floor_name,
            f.floor_code
        FROM shops s
        JOIN floors f ON s.floor_id = f.id
        WHERE s.id = %s
    """

    cursor.execute(shop_query, (shop_id,))
    shop = cursor.fetchone()

    cursor.close()
    connection.close()

    if shop is None:
        return jsonify({
            "error": "Shop not found"
        }), 404

    return jsonify({
        "from": user_location,
        "to": shop
    })

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({
            "error": "Username and password are required"
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            so.id,
            so.username,
            so.password,
            so.shop_id,
            s.shop_name
        FROM store_owners so
        JOIN shops s ON so.shop_id = s.id
        WHERE so.username = %s
    """

    cursor.execute(query, (username,))
    owner = cursor.fetchone()

    cursor.close()
    connection.close()

    if owner is None or not check_password_hash(owner["password"], password):
        cursor.close()
        connection.close()

        return jsonify({
            "error": "Invalid username or password"
        }), 401

    session["owner_id"] = owner["id"]
    session["username"] = owner["username"]
    session["shop_id"] = owner["shop_id"]

    return jsonify({
        "message": "Login successful",
        "owner": owner
    })

@app.route("/store-owner")
def store_owner_dashboard():

    # if not logged in, can't access owner dashboard
    if "owner_id" not in session:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            so.id,
            so.username,
            so.shop_id,
            s.shop_name,
            s.operating_hours,
            s.category,
            s.unit,
            s.description
        FROM store_owners so
        JOIN shops s ON so.shop_id = s.id
        WHERE so.id = %s
    """

    cursor.execute(query, (session["owner_id"],))
    owner = cursor.fetchone()

    cursor.close()
    connection.close()

    if owner is None:
        session.clear()
        return redirect("/login")

    return render_template(
        "store_owner.html",
        owner=owner
    )

@app.route("/store-owner/edit")
def store_owner_edit():

    if "owner_id" not in session:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Get owner's shop
    shop_query = """
        SELECT *
        FROM shops
        WHERE id = %s
    """

    cursor.execute(
        shop_query,
        (session["shop_id"],)
    )

    shop = cursor.fetchone()

    # Get available floors
    cursor.execute("""
        SELECT *
        FROM floors
        ORDER BY id
    """)

    floors = cursor.fetchall()

    cursor.close()
    connection.close()

    if shop is None:
        session.clear()
        return redirect("/login")

    return render_template(
        "store_owner_edit.html",
        shop=shop,
        floors=floors
    )

@app.route("/guest")
def guest_page():
    return render_template("guest.html")

@app.route("/api/logout", methods=["POST"])
def logout():

    # forget the session data
    session.clear()

    return jsonify({
        "message": "Logged out successfully"
    })

@app.route("/forgot-password")
def forgot_password():
    return render_template("forgot_password.html")

@app.route("/api/forgot-password", methods=["POST"])
def forgot_password_api():

    data = request.get_json()

    username = data.get("username")

    if not username:
        return jsonify({
            "message": "Please enter your username."
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT id
        FROM store_owners
        WHERE username = %s
    """

    cursor.execute(query, (username,))
    owner = cursor.fetchone()

    cursor.close()
    connection.close()

    if owner is None:

        return jsonify({
            "message": "If this account exists, please contact the system administrator to reset your password."
        })

    return jsonify({
        "message": "Please contact the system administrator to reset your password."
    })

@app.route("/feedback")
def feedback_page():
    return render_template("feedback.html")

@app.route("/api/feedback", methods=["POST"])
def submit_feedback():

    data = request.get_json()

    name = data.get("name")
    email = data.get("email")
    phone = data.get("phone")
    incident_date = data.get("incident_date") or None
    message = data.get("message", "").strip()
    resolution = data.get("resolution")

    if not message:
        return jsonify({
            "error": "Please describe your feedback before submitting."
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        INSERT INTO feedback
        (name, email, phone, incident_date, message, resolution)
        VALUES (%s, %s, %s, %s, %s, %s)
    """

    cursor.execute(
        query,
        (name or None, email or None, phone or None, incident_date, message, resolution or None)
    )
    connection.commit()

    new_feedback_id = cursor.lastrowid

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Thank you! Your feedback has been submitted.",
        "feedback_id": new_feedback_id
    }), 201

@app.route("/admin/login")
def admin_login_page():
    return render_template("admin_login.html")

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({
            "error": "Username and password are required"
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT id, username, password FROM admins WHERE username = %s",
        (username,)
    )
    admin = cursor.fetchone()

    cursor.close()
    connection.close()

    if admin is None or not check_password_hash(admin["password"], password):
        return jsonify({
            "error": "Invalid username or password"
        }), 401

    session["admin_id"] = admin["id"]
    session["admin_username"] = admin["username"]

    return jsonify({
        "message": "Login successful"
    })

@app.route("/admin/feedback")
def admin_feedback_page():
    if "admin_id" not in session:
        return redirect("/admin/login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, name, email, phone, incident_date, message, topic, resolution, submitted_at
        FROM feedback
        ORDER BY submitted_at DESC
    """)
    feedback = cursor.fetchall()

    # Group by topic (case-insensitive, blanks excluded) so the admin can
    # see how many distinct visitors reported the same underlying issue
    topic_groups = {}
    for item in feedback:
        topic = (item.get("topic") or "").strip()
        if not topic:
            continue

        key = topic.lower()
        group = topic_groups.setdefault(key, {"topic": topic, "emails": set(), "count": 0})
        group["count"] += 1
        if item.get("email"):
            group["emails"].add(item["email"])

    cursor.close()
    connection.close()

    topics = []
    for group in topic_groups.values():
        topics.append({
            "topic": group["topic"],
            "count": group["count"],
            "distinct_visitors": len(group["emails"])
        })

    topics.sort(key=lambda t: t["count"], reverse=True)

    return render_template(
        "admin_feedback.html",
        feedback=feedback,
        topics=topics,
        general_voucher_types=GENERAL_VOUCHER_TYPES
    )

@app.route("/api/admin/feedback/<int:feedback_id>/topic", methods=["PUT"])
def set_feedback_topic(feedback_id):
    if "admin_id" not in session:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json()
    topic = (data.get("topic") or "").strip() or None

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE feedback SET topic = %s WHERE id = %s",
        (topic, feedback_id)
    )
    connection.commit()

    cursor.close()
    connection.close()

    return jsonify({"message": "Topic updated"})

@app.route("/api/admin/vouchers/issue", methods=["POST"])
def issue_vouchers():
    if "admin_id" not in session:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json()
    topic = (data.get("topic") or "").strip()
    voucher_type = (data.get("voucher_type") or "").strip()
    shop_code = (data.get("shop_code") or "").strip() or None

    if not topic:
        return jsonify({"error": "Topic is required"}), 400

    if voucher_type == "shop":
        if not shop_code:
            return jsonify({"error": "Please choose a shop"}), 400
    elif voucher_type in GENERAL_VOUCHER_TYPES:
        shop_code = None
    else:
        return jsonify({"error": "Please choose a valid voucher type"}), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if voucher_type == "shop":
        cursor.execute("SELECT shop_name FROM shops WHERE shop_code = %s", (shop_code,))
        shop = cursor.fetchone()
        if not shop:
            cursor.close()
            connection.close()
            return jsonify({"error": "Shop not found"}), 400
        voucher_label = f"{shop['shop_name']} Voucher"
    else:
        voucher_label = GENERAL_VOUCHER_TYPES[voucher_type]

    cursor.execute(
        "SELECT DISTINCT email FROM feedback WHERE LOWER(TRIM(topic)) = %s AND email IS NOT NULL AND email <> ''",
        (topic.lower(),)
    )
    emails = [row["email"] for row in cursor.fetchall()]

    cursor.execute(
        "SELECT email FROM vouchers WHERE LOWER(topic) = %s AND voucher_type = %s AND shop_code <=> %s",
        (topic.lower(), voucher_type, shop_code)
    )
    already_issued = {row["email"] for row in cursor.fetchall()}

    issued = []
    for email in emails:
        if email in already_issued:
            continue

        code = "DPULZE-" + secrets.token_hex(4).upper()
        cursor.execute(
            "INSERT INTO vouchers (topic, voucher_type, shop_code, email, code) VALUES (%s, %s, %s, %s, %s)",
            (topic, voucher_type, shop_code, email, code)
        )
        issued.append({"email": email, "code": code, "voucher_type": voucher_label})

    connection.commit()

    cursor.close()
    connection.close()

    return jsonify({
        "message": f"Issued {len(issued)} voucher(s)",
        "vouchers": issued
    })

@app.route("/api/admin/vouchers")
def get_vouchers():
    if "admin_id" not in session:
        return jsonify({"error": "Login required"}), 401

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT v.id, v.topic, v.voucher_type, v.shop_code, v.email, v.code, v.issued_at,
               s.shop_name
        FROM vouchers v
        LEFT JOIN shops s ON s.shop_code = v.shop_code
        ORDER BY v.issued_at DESC
    """)
    vouchers = cursor.fetchall()

    for voucher in vouchers:
        if voucher["voucher_type"] == "shop":
            voucher["voucher_type_label"] = f"{voucher['shop_name'] or 'Unknown Shop'} Voucher"
        else:
            voucher["voucher_type_label"] = GENERAL_VOUCHER_TYPES.get(
                voucher["voucher_type"], voucher["voucher_type"]
            )

    cursor.close()
    connection.close()

    return jsonify(vouchers)

@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_username", None)

    return jsonify({
        "message": "Logged out successfully"
    })

def get_session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex
    return session["session_id"]


@app.route("/")
def index():
    current = session.get("current_location")
    return render_template(
        "index.html",
        current=LOCATIONS.get(current),
        current_name=current,
        start_node=NODE_MAP.get(current),
    )


@app.route("/location/<name>")
def location(name):
    if name not in LOCATIONS:
        abort(404)

    previous_location = session.get("current_location")
    session["last_location"] = previous_location
    session["current_location"] = name
    record_scan(name, get_session_id(), previous_location)
    return redirect("/")


@app.route("/scans")
def scans():
    return redirect("/")


@app.route("/shops")
def shops():
    return redirect("/")

if __name__ == "__main__":
    # use_reloader=False: the reloader re-executes this module in a second
    # process, which would start a duplicate occupancy-simulator thread
    app.run(debug=True, use_reloader=False)

# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000, debug=True)
