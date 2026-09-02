from flask import Flask, abort, jsonify, request, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection
from simulate_occupancy import run_simulator
from locations import LOCATIONS, MAP_WIDTH, MAP_HEIGHT, SHOPS, NODE_MAP
from scan_log import read_scans, record_scan
from simulate_occupancy import run_simulator

import json
import os
import secrets
import threading
import uuid
import threading
import urllib.request
import urllib.parse

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

def start_occupancy_simulator():
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    simulator_thread = threading.Thread(
        target=run_simulator,
        name="occupancy-simulator",
        daemon=True
    )
    simulator_thread.start()


start_occupancy_simulator()
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
        s.full_description,
        s.products_services,
        s.website_url,
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
            u.name,
            u.map_code,
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
    used_map_facilities = set()

    for utility in utilities:
        utility_type = utility["type"].strip().lower().replace(" ", "_")
        if utility_type in ("toilet", "restroom"):
            utility_type = "restroom"
        elif "baby" in utility_type and "diaper" in utility_type:
            utility_type = "baby_diaper"
        elif utility_type.startswith("oku"):
            utility_type = "oku"
        elif utility_type.startswith("lift"):
            utility_type = "lift"
        utility["type"] = utility_type
        utility["utility_id"] = int(utility["utility_id"])
        utility["utility_code"] = utility["map_code"] or str(utility["utility_id"])
        utility["total_cubicles"] = int(utility["total_cubicles"] or 0)
        utility["occupied_cubicles"] = int(utility["occupied_cubicles"] or 0)
        utility["available_cubicles"] = (
            utility["total_cubicles"] - utility["occupied_cubicles"]
        )
        utility["is_occupied"] = utility["type"] == "oku" and utility["occupied_cubicles"] > 0

        matching_facility = None
        if utility["map_code"] in map_facilities:
            matching_facility = (utility["map_code"], map_facilities[utility["map_code"]])

        if matching_facility:
            facility_id, facility = matching_facility
            used_map_facilities.add(facility_id)
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
            description = %s,
            floor_id = %s
        WHERE id = %s
    """

    values = (
        shop_name,
        operating_hours,
        category,
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


def get_shop_categories():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT DISTINCT TRIM(category) AS category
        FROM shops
        WHERE category IS NOT NULL AND TRIM(category) <> ''
        ORDER BY category
    """)
    categories = [row["category"] for row in cursor.fetchall()]
    cursor.close()
    connection.close()
    return categories


def get_dpulze_shop_overview(limit=None):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    if limit is None:
        cursor.execute("""
                SELECT s.shop_code, s.shop_name, s.operating_hours, s.category, s.description,
                     s.full_description, s.products_services, f.floor_name
            FROM shops s
            LEFT JOIN floors f ON f.id = s.floor_id
            ORDER BY f.id, s.shop_name
        """)
    else:
        cursor.execute("""
                SELECT s.shop_code, s.shop_name, s.operating_hours, s.category, s.description,
                     s.full_description, s.products_services, f.floor_name
            FROM shops s
            LEFT JOIN floors f ON f.id = s.floor_id
            ORDER BY f.id, s.shop_name
            LIMIT %s
        """, (limit,))
    shops = cursor.fetchall()
    cursor.close()
    connection.close()
    return shops


def get_dpulze_facility_overview():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT utility_type, name, floor
        FROM utilities
        ORDER BY utility_type, name
    """)
    facilities = cursor.fetchall()
    cursor.close()
    connection.close()
    return facilities


def get_dpulze_map_locations():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT location_name, location_code, floor_id
        FROM locations
        ORDER BY location_name
    """)
    locations = cursor.fetchall()
    cursor.close()
    connection.close()
    return locations


def build_mall_context():
    categories = get_shop_categories()
    shops = get_dpulze_shop_overview()
    facilities = get_dpulze_facility_overview()
    locations = get_dpulze_map_locations()

    def shop_detail(shop):
        detail = (
            shop.get("products_services")
            or shop.get("full_description")
            or shop.get("description")
            or shop.get("category")
            or "general mall offerings"
        )
        return str(detail).strip()

    category_text = ", ".join(categories) if categories else "general shopping"
    facility_text = ", ".join(
        f"{item['utility_type']} ({item['name']}, floor {item['floor'] or 'unknown'})" for item in facilities[:12]
    ) if facilities else "restroom, OKU restroom, baby diaper room, lift"

    shop_text = "; ".join(
        f"{shop['shop_name']} ({shop['category'] or 'General'} on {shop['floor_name'] or 'ground floor'}): {shop_detail(shop)}"
        for shop in shops
    ) if shops else "No store list available"

    location_text = "; ".join(
        f"{item['location_name']} ({item['location_code']})" for item in locations[:12]
    ) if locations else "main entrance and common zones"

    return (
        "You are the AI concierge for Dpulze Mall. "
        "Answer questions only using the Dpulze Mall data in this app. "
        "Use the full shops catalogue in the database, especially the store names, categories, descriptions, full_description, and products_services fields. "
        "When a user asks for stores that sell a product or item, review the complete shops table and list every matching store based on its product/services description. "
        "Do not invent stores, facilities, sections, or food courts that are not present in the mall data. "
        "If a location or store is not listed in the Dpulze database or map, say it is not available in Dpulze Mall. "
        "The available Dpulze map locations include: "
        f"{location_text}. "
        "This mall includes the following utility/facility entries: "
        f"{facility_text}. "
        "The mall store categories currently in the database are: "
        f"{category_text}. "
        "Sample Dpulze shops currently in the database: "
        f"{shop_text}. "
        "Keep replies concise, friendly, and specific to Dpulze Mall."
    )


def build_recommendation_guidance(message):
    lowered = message.lower()
    if not any(keyword in lowered for keyword in ("shoe", "shoes", "footwear", "sneaker", "sneakers")):
        return ""

    shops = get_dpulze_shop_overview()
    shoe_terms = (
        "shoe", "footwear", "sneaker", "sandal", "boot", "sportswear", "sporting", "running", "slipper"
    )
    matching_shops = []
    for shop in shops:
        if "permanently closed" in str(shop.get("operating_hours") or "").lower():
            continue
        searchable_text = " ".join(
            str(shop.get(field) or "")
            for field in ("shop_name", "category", "description", "full_description", "products_services")
        ).lower()
        if any(term in searchable_text for term in shoe_terms):
            matching_shops.append(
                f"{shop['shop_name']} ({shop['category'] or 'General'}): "
                f"{shop.get('products_services') or shop.get('full_description') or shop.get('description') or shop.get('category') or 'No selling details'}"
            )

    matching_text = "; ".join(matching_shops) if matching_shops else "No shoe-related store was found"
    return (
        "This is a shoe/footwear request. Only recommend stores whose category or selling details "
        "match shoes, footwear, sneakers, sandals, boots, sportswear, sporting goods, running shoes, or slippers. "
        "Do not include electronics, telecommunications, food, beauty, furniture, banking, or other unrelated stores. "
        "The database-matched shoe stores are: "
        f"{matching_text}."
    )


def ask_ollama_chat(prompt):
    model_name = os.environ.get("OLLAMA_MODEL", "llama3.2")
    mall_context = build_mall_context()

    payload = {
        "model": model_name,
        "prompt": (
            f"{mall_context}\n\nUser question: {prompt}"
        ),
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 250,
        },
    }

    request = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            text = result.get("response", "").strip()
            if text:
                return text
    except Exception:
        return None

    return None


def ask_openai_chat(prompt):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful mall concierge for Dpulze Mall. Use the mall database as the source of truth. "
                    "When someone asks which stores sell an item, search across the full shops catalogue and list all matching stores with their selling details. "
                    "Do not rely on a few famous brands or generic recommendations if the database contains more specific matches. "
                    "Answer user questions about stores, mall navigation, shopping recommendations, and general mall services. "
                    "Keep replies concise, friendly, and practical."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 250,
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def generate_local_chat_reply(message):
    if not message or not message.strip():
        return "Please send a question or shopping request."

    text = message.strip()
    lowered = text.lower()
    categories = get_shop_categories()
    category_hint = ", ".join(categories[:6]) if categories else "fashion, food, electronics, services"

    if any(keyword in lowered for keyword in ["hi", "hello", "hey", "good morning", "good afternoon"]):
        return "Hi! I can help with mall information, store suggestions, categories, and shopping recommendations."

    if any(keyword in lowered for keyword in ["where", "locate", "direction", "map", "find"]):
        return "You can use the mall map in the navigation page to find stores and facilities. I can also suggest nearby categories or relevant shops."

    if any(keyword in lowered for keyword in ["recommend", "suggest", "shop", "buy", "looking for", "need"]):
        if any(keyword in lowered for keyword in ["food", "eat", "restaurant", "cafe"]):
            return "For food and dining, try the food and dining sections in the mall directory. If you want, I can narrow it down by budget or vibe."
        if any(keyword in lowered for keyword in ["clothes", "fashion", "apparel", "outfit", "dress"]):
            return "For fashion and apparel, look for the clothing and lifestyle categories in the mall. I can also suggest a quick shopping route for a casual or premium look."
        if any(keyword in lowered for keyword in ["kids", "baby", "diaper", "family"]):
            return "For family needs, check the baby care and family-friendly facilities on the map. You can also look for kid-friendly or family-oriented stores in the directory."
        return (
            f"I can help with shopping suggestions. Popular categories in this mall include: {category_hint}. "
            "Tell me your preference, such as fashion, food, family needs, or budget, and I’ll narrow it down."
        )

    if any(keyword in lowered for keyword in ["bathroom", "toilet", "restroom", "baby diaper", "oku"]):
        return "You can check the map for restroom, OKU restroom, and baby diaper room locations. The app also shows live availability for these facilities."

    if any(keyword in lowered for keyword in ["opening", "hours", "close", "time"]):
        return "Store hours are usually listed in the shop details on the map and directory. I can help you find the right store based on availability or shopping type."

    return (
        "I can help with mall navigation, store recommendations, categories, and shopping preferences. "
        "Ask me for nearby stores, family-friendly spots, food options, or general mall help."
    )


def get_chat_memory():
    if "chat_memory" not in session:
        session["chat_memory"] = []
    return session["chat_memory"]


def find_shop_from_message(message):
    normalized_message = message.casefold()
    shops = get_dpulze_shop_overview()
    matches = [
        shop for shop in shops
        if shop.get("shop_code") and shop.get("shop_name")
        and shop["shop_name"].casefold() in normalized_message
    ]
    return max(matches, key=lambda shop: len(shop["shop_name"])) if matches else None


def is_confirmation_message(message):
    """Return True for a short affirmative reply to a pending store action.

    Users often reply with phrases such as "yes, please" or "sure, take me
    there" instead of repeating "map navigation".  A pending store in the
    session makes those replies unambiguous enough to show its map link.
    """
    normalized = message.casefold().strip().lstrip("!,. ")
    affirmative_starts = (
        "yes", "yeah", "yep", "sure", "okay", "ok", "please", "go ahead"
    )
    return any(
        normalized == phrase
        or normalized.startswith(f"{phrase} ")
        or normalized.startswith(f"{phrase},")
        for phrase in affirmative_starts
    )


def build_chat_context():
    memory = get_chat_memory()
    if not memory:
        return ""

    recent = memory[-6:]
    lines = [f"{item['role']}: {item['content']}" for item in recent]
    return "Conversation memory:\n" + "\n".join(lines)


def generate_chatbot_reply(message):
    if is_confirmation_message(message) and session.get("navigation_shop"):
        shop = session["navigation_shop"]
        return (
            f"Sure. Open Map Navigation and enter {shop['shop_name']} in the shop search. "
            "The map will select the store and show the route from your current starting point."
        )

    context = build_chat_context()
    db_guidance = (
        "Use the full shops table and all product/service descriptions in the database before recommending or listing stores. "
        "Do not default to a few well-known shops unless they are the only matching stores in the database."
    )
    recommendation_guidance = build_recommendation_guidance(message)
    prompt = message if not context else f"{context}\n\nCurrent user message: {message}"
    prompt = f"{db_guidance}\n{recommendation_guidance}\n\n{prompt}"

    ollama_reply = ask_ollama_chat(prompt)
    if ollama_reply:
        return ollama_reply

    openai_reply = ask_openai_chat(prompt)
    if openai_reply:
        return openai_reply

    return generate_local_chat_reply(message)

# main menu
@app.route("/")
def home():
    return render_template("home.html")

# map navigation
@app.route("/map")
def map_page():
    current = session.get("current_location")

    return render_template(
        "index.html",
        current=LOCATIONS.get(current),
        current_name=current,
        start_node=NODE_MAP.get(current),
    )

# shop directory
@app.route("/directory")
def directory_page():
    return render_template("directory.html")

# feedback
@app.route("/feedback")
def feedback_page():
    return render_template("feedback.html")

# QR location
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
    return redirect("/directory")

# chatbot AI
@app.route("/chat")
def chat_page():
    return render_template("chat.html")

@app.route("/api/chat", methods=["POST"])
def chat_api():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()

    if not message:
        return jsonify({"reply": "Please type a message first."}), 400

    # Treat a natural affirmative reply as confirmation for the most recently
    # mentioned store.  The user does not need to repeat "map navigation".
    confirmation = is_confirmation_message(message)
    selected_shop = find_shop_from_message(message)
    if selected_shop:
        session["navigation_shop"] = {
            "shop_code": selected_shop["shop_code"],
            "shop_name": selected_shop["shop_name"],
        }

    memory = get_chat_memory()
    memory.append({"role": "user", "content": message})
    if len(memory) > 12:
        memory = memory[-12:]
    session["chat_memory"] = memory

    reply = generate_chatbot_reply(message)
    if selected_shop and not confirmation:
        if "navigation" not in reply.casefold() and "directions" not in reply.casefold():
            reply = f"{reply}\n\nWould you like navigation to {selected_shop['shop_name']}?"
    memory.append({"role": "assistant", "content": reply})
    if len(memory) > 12:
        memory = memory[-12:]
    session["chat_memory"] = memory

    navigation_shop = session.get("navigation_shop")
    navigation_url = None
    if navigation_shop and confirmation:
        navigation_url = url_for(
            "map_page",
            shop=navigation_shop["shop_code"],
            navigate="1",
        )

    return jsonify({"reply": reply, "navigation_url": navigation_url})

@app.route("/api/chat/reset", methods=["POST"])
def chat_reset_api():
    session.pop("chat_memory", None)
    session.pop("navigation_shop", None)
    return jsonify({"status": "cleared"})

# if __name__ == "__main__":
#     app.run(debug=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
