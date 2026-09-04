from flask import Flask, abort, jsonify, request, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection
from simulate_occupancy import run_simulator
from locations import LOCATIONS, MAP_WIDTH, MAP_HEIGHT, SHOPS, NODE_MAP
from scan_log import read_scans, record_scan

import json
import os
import secrets
import threading
import uuid
import urllib.request
import urllib.parse
import re
from html.parser import HTMLParser

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

GENERAL_VOUCHER_TYPES = {
    "parking": "Parking Voucher",
}

MAP_FILES = {
    "ground": "map.json",
    "upper-ground": "map_upper_ground.json",
    "2f": "map_2f.json",
}


def load_map(floor_id="ground"):
    map_filename = MAP_FILES.get(floor_id)
    if not map_filename:
        abort(404)

    map_path = os.path.join("data", map_filename)
    with open(map_path, "r", encoding="utf-8") as file:
        return json.load(file)

@app.route("/api/map")
def get_map():
    floor_id = request.args.get("floor", "ground")
    map_data = load_map(floor_id)
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
    floor_id = request.args.get("floor", "ground")
    map_data = load_map(floor_id)
    database_floor = map_data.get("database_floor")
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    utility_query = """
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
    """
    query_params = ()
    if database_floor:
        utility_query += " WHERE u.floor = %s"
        query_params = (database_floor,)

    utility_query += """
        GROUP BY u.id, u.name, u.utility_type, u.floor
        ORDER BY u.utility_type, u.name
    """
    cursor.execute(utility_query, query_params)
    utilities = cursor.fetchall()

    cursor.close()
    connection.close()

    map_facilities = map_data.get("facilities", {})
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

# =========================================================
# CHATBOT CATEGORY + FLOOR HELPERS
# =========================================================

CATEGORY_ALIASES = {
    "Fashion": (
        "fashion", "clothing", "clothes", "apparel",
        "shirt", "shirts", "t-shirt", "t-shirts",
        "pants", "dress", "dresses",
    ),
    "Food & Beverages": (
        "food", "foods", "restaurant", "restaurants",
        "cafe", "cafes", "coffee", "drink", "drinks",
        "beverage", "beverages", "eat", "eating", "dining",
    ),
    "Sports & Outdoor": (
        "sport", "sports", "sportswear", "sporting",
        "outdoor", "running shoes", "sports shoes",
        "sporting goods",
    ),
    "Cosmetics & Beauty": (
        "beauty", "cosmetic", "cosmetics", "makeup", "skincare",
    ),
    "Electronics": (
        "electronics", "electronic", "gadget", "gadgets",
        "phone", "phones", "mobile phone", "computer", "computers",
    ),
    "Banking & Finance": (
        "bank", "banks", "banking", "finance", "financial", "atm",
    ),
    "Home & Living": (
        "home", "living", "furniture", "household", "homeware",
    ),
    "Health & Wellness": (
        "health", "wellness", "pharmacy", "medical",
    ),
    "Convenience Store": (
        "convenience", "convenience store", "grocery", "groceries",
    ),
    "Retail": (
        "retail", "general retail",
    ),
}


def _chat_terms(value):
    """Return normalized searchable words and basic singular forms."""
    words = re.findall(r"[a-z0-9]+", (value or "").casefold())
    terms = set(words)

    for word in words:
        if len(word) > 4 and word.endswith("ies"):
            terms.add(word[:-3] + "y")
        elif len(word) > 4 and word.endswith("s"):
            terms.add(word[:-1])

    return terms


def detect_dynamic_category_request(message):
    """
    Match customer wording to a category that actually exists in MySQL.

    Priority:
    1. Exact database category wording.
    2. Friendly aliases such as "restaurants" -> "Food & Beverages".
    3. Evidence from shop descriptions/products.
    """
    text = (message or "").casefold()
    categories = get_shop_categories()

    if not categories:
        return None

    for category in categories:
        if category.casefold() in text:
            return category

    category_lookup = {
        category.casefold(): category
        for category in categories
    }

    for alias_category, aliases in CATEGORY_ALIASES.items():
        actual_category = category_lookup.get(alias_category.casefold())
        if not actual_category:
            continue

        if any(alias in text for alias in aliases):
            return actual_category

    ignored = {
        "all", "list", "shop", "shops", "store", "stores", "mall",
        "dpulze", "available", "there", "what", "which", "where",
        "any", "other", "than", "those", "these", "show", "tell",
        "give", "have", "does", "do", "can", "could", "would",
        "please", "the", "and", "for", "with", "are", "is", "in",
        "me", "my", "i", "selling", "sell", "sells",
    }

    useful_terms = {
        term
        for term in _chat_terms(message)
        if term not in ignored and len(term) >= 3
    }

    if not useful_terms:
        return None

    shops = get_dpulze_shop_overview()
    shops_by_category = {}

    for shop in shops:
        category = (shop.get("category") or "").strip()
        if category:
            shops_by_category.setdefault(category.casefold(), []).append(shop)

    best_category = None
    best_score = 0

    for category in categories:
        category_key = category.casefold()
        category_terms = _chat_terms(category)
        score = 0

        for term in useful_terms:
            if term in category_terms:
                score += 6

        for shop in shops_by_category.get(category_key, []):
            searchable = " ".join(
                str(shop.get(field) or "")
                for field in (
                    "shop_name",
                    "category",
                    "description",
                    "full_description",
                    "products_services",
                )
            ).casefold()

            searchable_terms = _chat_terms(searchable)

            for term in useful_terms:
                if term in searchable_terms:
                    score += 1

        if score > best_score:
            best_score = score
            best_category = category

    return best_category if best_score > 0 else None


def is_category_list_request(message):
    """Return True when the customer is asking for a list/set of shops."""
    text = (message or "").casefold()

    list_phrases = (
        "list",
        "all",
        "available",
        "what shops",
        "which shops",
        "what stores",
        "which stores",
        "are there",
        "do you have",
        "show me",
        "give me",
        "any shops",
        "any stores",
        "any other",
        "other than",
        "other shops",
        "other stores",
    )

    return any(phrase in text for phrase in list_phrases)


def get_category_floors(category):
    """Return the distinct floors containing shops in the category."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT DISTINCT f.floor_name
        FROM shops s
        LEFT JOIN floors f ON f.id = s.floor_id
        WHERE LOWER(TRIM(s.category)) = %s
          AND f.floor_name IS NOT NULL
          AND TRIM(f.floor_name) <> ''
        ORDER BY f.floor_name
    """, (category.casefold(),))

    floors = [
        row["floor_name"]
        for row in cursor.fetchall()
        if row.get("floor_name")
    ]

    cursor.close()
    connection.close()
    return floors


def find_floor_from_message(message, available_floors):
    """Match a customer's floor reply to an actual floor in the database."""
    text = (message or "").casefold().strip()

    for floor in available_floors:
        if floor.casefold() in text:
            return floor

    aliases = {
        "ground": ("ground floor", "ground", "gf", "level g"),
        "first": ("first floor", "1st floor", "level 1", "level one"),
        "second": ("second floor", "2nd floor", "level 2", "level two"),
        "third": ("third floor", "3rd floor", "level 3", "level three"),
    }

    for floor in available_floors:
        floor_lower = floor.casefold()

        for floor_key, phrases in aliases.items():
            if floor_key in floor_lower and any(phrase in text for phrase in phrases):
                return floor

        if "1" in floor_lower and any(p in text for p in aliases["first"]):
            return floor
        if "2" in floor_lower and any(p in text for p in aliases["second"]):
            return floor
        if "3" in floor_lower and any(p in text for p in aliases["third"]):
            return floor

    return None


def is_any_floor_reply(message):
    text = (message or "").casefold()

    phrases = (
        "any floor",
        "all floors",
        "doesn't matter",
        "does not matter",
        "either floor",
        "anywhere",
        "no preference",
    )

    return any(phrase in text for phrase in phrases)


def get_shops_by_category(category, floor_name=None):
    """Retrieve every shop in a category, optionally restricted to one floor."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if floor_name:
        cursor.execute("""
            SELECT
                s.shop_code,
                s.shop_name,
                s.category,
                s.unit,
                s.operating_hours,
                s.products_services,
                f.floor_name
            FROM shops s
            LEFT JOIN floors f ON f.id = s.floor_id
            WHERE LOWER(TRIM(s.category)) = %s
              AND LOWER(TRIM(f.floor_name)) = %s
            ORDER BY s.shop_name
        """, (
            category.casefold(),
            floor_name.casefold(),
        ))
    else:
        cursor.execute("""
            SELECT
                s.shop_code,
                s.shop_name,
                s.category,
                s.unit,
                s.operating_hours,
                s.products_services,
                f.floor_name
            FROM shops s
            LEFT JOIN floors f ON f.id = s.floor_id
            WHERE LOWER(TRIM(s.category)) = %s
            ORDER BY f.id, s.shop_name
        """, (category.casefold(),))

    shops = cursor.fetchall()
    cursor.close()
    connection.close()
    return shops


def build_category_list_reply(category, floor_name=None):
    """
    Build a complete database-backed category list.
    """
    shops = get_shops_by_category(category, floor_name)

    if not shops:
        if floor_name:
            return (
                f"I couldn't find any {category} shops on {floor_name} "
                "in the Dpulze Mall directory."
            )

        return (
            f"I couldn't find any shops under {category} "
            "in the Dpulze Mall directory."
        )

    lines = []

    for shop in shops:
        location_parts = []

        if shop.get("unit"):
            location_parts.append(f"Unit {shop['unit']}")

        if shop.get("floor_name"):
            location_parts.append(shop["floor_name"])

        location = ", ".join(location_parts)

        if location:
            lines.append(f"• {shop['shop_name']} — {location}")
        else:
            lines.append(f"• {shop['shop_name']}")

    if floor_name:
        heading = f"Here are the {category} shops on {floor_name}:"
    else:
        heading = f"Here are the {category} shops currently listed in Dpulze Mall:"

    return heading + "\n\n" + "\n".join(lines)



def get_dpulze_shop_overview(limit=None):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    base_query = """
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
            f.floor_name
        FROM shops s
        LEFT JOIN floors f ON f.id = s.floor_id
        ORDER BY f.id, s.shop_name
    """

    if limit is None:
        cursor.execute(base_query)
    else:
        cursor.execute(base_query + " LIMIT %s", (limit,))

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


def normalize_chat_text(value):
    """Normalize names so Nando's, nandos, F.O.S and similar forms can match."""
    value = (value or "").casefold()
    return re.sub(r"[^a-z0-9]+", "", value)


def get_chat_memory():
    if "chat_memory" not in session:
        session["chat_memory"] = []
    return session["chat_memory"]


def find_shop_from_message(message):
    """Find a shop explicitly named by the customer, ignoring punctuation."""
    normalized_message = normalize_chat_text(message)
    shops = get_dpulze_shop_overview()

    matches = []
    for shop in shops:
        if not shop.get("shop_code") or not shop.get("shop_name"):
            continue

        normalized_shop_name = normalize_chat_text(shop["shop_name"])
        if normalized_shop_name and normalized_shop_name in normalized_message:
            matches.append(shop)

    return max(matches, key=lambda shop: len(shop["shop_name"])) if matches else None


def is_confirmation_message(message):
    # """Return True for a short affirmative reply to a pending store action.

    # Users often reply with phrases such as "yes, please" or "sure, take me
    # there" instead of repeating "map navigation".  A pending store in the
    # session makes those replies unambiguous enough to show its map link.
    # """
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


def is_navigation_request(message):
    text = (message or "").casefold().strip()

    navigation_phrases = (
        "navigate",
        "navigation",
        "show me the route",
        "show route",
        "give me the route",
        "give me directions",
        "give me direction",
        "direction to",
        "directions to",
        "take me there",
        "take me to",
        "bring me there",
        "bring me to",
        "i want to go to",
        "i want to go there",
        "i would like to go to",
        "i'd like to go to",
        "how do i get there",
        "how can i get there",
        "how to get there",
        "how do i go there",
        "go there",
        "route there",
        "show me how to get there",
    )

    return any(
        phrase in text
        for phrase in navigation_phrases
    )

def is_follow_up_message(message):
    text = message.casefold().strip()
    follow_up_phrases = (
        "other than that",
        "anything else",
        "any other",
        "another one",
        "another shop",
        "other shop",
        "more options",
        "more option",
        "what else",
        "how about another",
        "and that one",
        "what about that",
        "what about it",
        "what about there",
        "there",
        "that shop",
        "that store",
        "what about them",
        "how about them",
    )
    return any(phrase in text for phrase in follow_up_phrases)


def get_previous_user_message(current_message):
    memory = get_chat_memory()
    for item in reversed(memory):
        if (
            item.get("role") == "user"
            and item.get("content", "").strip() != current_message.strip()
        ):
            return item["content"]
    return None


def get_last_assistant_message():
    memory = get_chat_memory()
    for item in reversed(memory):
        if item.get("role") == "assistant":
            return item.get("content", "")
    return ""


def build_chat_context():
    memory = get_chat_memory()
    if not memory:
        return ""

    recent = memory[-6:]
    lines = [f"{item['role']}: {item['content']}" for item in recent]
    return "Conversation memory:\n" + "\n".join(lines)



PRODUCT_REQUEST_STOPWORDS = {
    "where", "what", "which", "when", "who", "can", "could", "would",
    "please", "i", "me", "my", "the", "a", "an", "is", "are", "do",
    "does", "have", "has", "find", "buy", "get", "shop", "shops",
    "store", "stores", "mall", "dpulze", "want", "need", "looking",
    "for", "give", "show", "tell", "other", "than", "that", "another",
    "anything", "else", "option", "options", "there", "them", "with",
    "under", "below", "less", "budget", "sell", "sells", "selling",
    "sold", "available", "recommend", "recommendation",
}


def extract_product_query(message):
    """
    Extract the useful product wording from a shopping question.

    Examples:
        "I want to buy running shoes" -> "running shoes"
        "Which shop sells shirts?" -> "shirts"
    """
    text = (message or "").casefold()

    # Remove common intent phrases first so the remaining words describe
    # the actual product the customer wants.
    intent_phrases = (
        "which stores sell",
        "which store sells",
        "which shops sell",
        "which shop sells",
        "what stores sell",
        "what store sells",
        "what shops sell",
        "what shop sells",
        "where can i buy",
        "where can i get",
        "who sells",
        "i want to buy",
        "i would like to buy",
        "i'd like to buy",
        "i need",
        "i am looking for",
        "i'm looking for",
        "looking for",
        "find me",
    )

    for phrase in intent_phrases:
        text = text.replace(phrase, " ")

    words = re.findall(r"[a-z0-9]+", text)

    useful = [
        word
        for word in words
        if len(word) >= 2
        and word not in PRODUCT_REQUEST_STOPWORDS
    ]

    # Keep order while removing duplicates.
    useful = list(dict.fromkeys(useful))

    return " ".join(useful).strip()


def search_product_matches(message, limit=8):
    """
    Search product/service information with stricter matching.

    For multi-word products such as:
        "ice cream"
        "running shoes"
        "face mask"

    a shop must match the full phrase OR all meaningful words.
    This prevents false matches such as "ice facial" for "ice cream".
    """

    product_query = extract_product_query(
        message
    )

    if not product_query:
        return []

    query_terms = _chat_terms(
        product_query
    )

    if not query_terms:
        return []

    shops = get_dpulze_shop_overview()

    ranked = []

    exact_phrase = (
        product_query
        .casefold()
        .strip()
    )

    # Original words only, before singular/plural expansion
    original_words = re.findall(
        r"[a-z0-9]+",
        exact_phrase
    )

    original_words = [
        word
        for word in original_words
        if len(word) >= 2
    ]

    multi_word_product = (
        len(original_words) >= 2
    )

    for shop in shops:

        product_text = " ".join([
            str(
                shop.get(
                    "products_services"
                ) or ""
            ),
            str(
                shop.get(
                    "full_description"
                ) or ""
            ),
            str(
                shop.get(
                    "description"
                ) or ""
            ),
        ]).casefold()

        shop_name = str(
            shop.get(
                "shop_name"
            ) or ""
        ).casefold()

        category = str(
            shop.get(
                "category"
            ) or ""
        ).casefold()

        product_terms = _chat_terms(
            product_text
        )

        shop_name_terms = _chat_terms(
            shop_name
        )

        category_terms = _chat_terms(
            category
        )

        score = 0

        # ---------------------------------
        # 1. EXACT PRODUCT PHRASE
        # ---------------------------------

        exact_match = (
            exact_phrase
            and exact_phrase
            in product_text
        )

        if exact_match:
            score += 30


        # ---------------------------------
        # 2. WORD MATCHING
        # ---------------------------------

        matched_product_terms = (
            query_terms
            & product_terms
        )

        matched_name_terms = (
            query_terms
            & shop_name_terms
        )

        matched_category_terms = (
            query_terms
            & category_terms
        )


        # ---------------------------------
        # 3. STRICT MULTI-WORD RULE
        # ---------------------------------

        if multi_word_product:

            original_matches = sum(
                1
                for word
                in original_words
                if word
                in product_terms
            )

            # For "ice cream":
            # both "ice" AND "cream"
            # must be present unless exact phrase matched.
            if (
                not exact_match
                and original_matches
                < len(original_words)
            ):
                continue


        # ---------------------------------
        # 4. SINGLE-WORD PRODUCTS
        # ---------------------------------

        else:

            if (
                not matched_product_terms
                and not matched_name_terms
            ):
                continue


        # ---------------------------------
        # 5. SCORE RESULTS
        # ---------------------------------

        score += (
            len(
                matched_product_terms
            )
            * 6
        )

        score += (
            len(
                matched_name_terms
            )
            * 4
        )

        # Category is supporting evidence only.
        if (
            matched_product_terms
            or matched_name_terms
        ):
            score += (
                len(
                    matched_category_terms
                )
                * 2
            )


        if score > 0:

            ranked.append(
                (
                    score,
                    shop
                )
            )


    ranked.sort(
        key=lambda item: (
            -item[0],
            (
                item[1].get(
                    "shop_name"
                ) or ""
            ).casefold(),
        )
    )


    return [
        shop
        for _, shop
        in ranked[:limit]
    ]


def search_relevant_shops(message, limit=8):
    """Search only the database records relevant to the current shopping question."""
    search_text = (message or "").strip()
    if not search_text:
        return []

    ignored_words = {
        "where", "what", "which", "when", "who", "can", "could", "would",
        "please", "i", "me", "my", "the", "a", "an", "is", "are", "do",
        "does", "have", "has", "find", "buy", "get", "shop", "store", "mall",
        "dpulze", "want", "need", "looking", "for", "give", "show", "tell",
        "other", "than", "that", "another", "anything", "else", "option",
        "options", "there", "them", "with", "under", "below", "less", "budget"
    }

    raw_words = re.findall(r"[A-Za-z0-9]+", search_text.casefold())
    words = [word for word in raw_words if len(word) >= 3 and word not in ignored_words]

    # Keep search efficient and avoid huge SQL statements.
    words = list(dict.fromkeys(words))[:8]
    if not words:
        return []

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    conditions = []
    parameters = []

    for word in words:
        pattern = f"%{word}%"
        conditions.append("""
            (
                s.shop_name LIKE %s
                OR s.category LIKE %s
                OR s.description LIKE %s
                OR s.full_description LIKE %s
                OR s.products_services LIKE %s
            )
        """)
        parameters.extend([pattern, pattern, pattern, pattern, pattern])

    query = f"""
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
            f.floor_name
        FROM shops s
        LEFT JOIN floors f ON f.id = s.floor_id
        WHERE {" OR ".join(conditions)}
        ORDER BY s.shop_name
        LIMIT %s
    """

    parameters.append(limit)
    cursor.execute(query, tuple(parameters))
    shops = cursor.fetchall()
    cursor.close()
    connection.close()
    return shops


def exclude_recently_recommended_shops(shops):
    """For 'other than that?' follow-ups, avoid repeating the previous recommendation."""
    last_reply = normalize_chat_text(get_last_assistant_message())
    if not last_reply:
        return shops

    filtered = []
    for shop in shops:
        shop_name = normalize_chat_text(shop.get("shop_name"))
        if shop_name and shop_name in last_reply:
            continue
        filtered.append(shop)

    return filtered


def build_relevant_shop_context(shops):
    if not shops:
        return ""

    lines = []
    for shop in shops:
        lines.append("\n".join([
            f"Shop: {shop.get('shop_name') or 'Unknown'}",
            f"Shop code: {shop.get('shop_code') or 'Unknown'}",
            f"Category: {shop.get('category') or 'Unknown'}",
            f"Unit: {shop.get('unit') or 'Unknown'}",
            f"Floor: {shop.get('floor_name') or 'Unknown'}",
            f"Hours: {shop.get('operating_hours') or 'Unknown'}",
            f"Products/Services: {shop.get('products_services') or 'Not provided'}",
            f"Description: {shop.get('full_description') or shop.get('description') or 'Not provided'}",
            f"Official website: {shop.get('website_url') or 'Not provided'}",
        ]))

    return "\n\n".join(lines)


def extract_budget(message):
    """Extract a Malaysian Ringgit budget from common customer wording."""
    text = (message or "").casefold()
    patterns = (
        r"rm\s*([0-9]+(?:\.[0-9]+)?)",
        r"budget\s*(?:is|of|around|about)?\s*rm?\s*([0-9]+(?:\.[0-9]+)?)",
        r"under\s*rm?\s*([0-9]+(?:\.[0-9]+)?)",
        r"below\s*rm?\s*([0-9]+(?:\.[0-9]+)?)",
        r"less\s+than\s*rm?\s*([0-9]+(?:\.[0-9]+)?)",
    )

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (TypeError, ValueError):
                return None
    return None


class WebsiteTextParser(HTMLParser):
    """Extract visible text from a simple public shop webpage."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.ignored_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data):
        if self.ignored_depth:
            return
        cleaned = " ".join((data or "").split())
        if cleaned:
            self.parts.append(cleaned)

    def get_text(self):
        return " ".join(self.parts)


def fetch_shop_website(url):
    """
    Fetch a small amount of visible text from an official public website.
    This is used only for budget questions and may fail on JS-heavy or blocked sites.
    """
    if not url or not str(url).startswith(("http://", "https://")):
        return ""

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                )
            },
        )

        with urllib.request.urlopen(req, timeout=6) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return ""

            html = response.read(350_000).decode("utf-8", errors="ignore")

        parser = WebsiteTextParser()
        parser.feed(html)
        text = parser.get_text()

        # Keep Ollama context small for faster responses.
        return text[:8000]

    except Exception as error:
        print(f"Website retrieval skipped for {url}: {error}")
        return ""


def build_budget_website_context(shops, budget):
    """Read only a few relevant official websites when a budget is supplied."""
    if budget is None or not shops:
        return ""

    sections = []
    for shop in shops[:3]:
        website_url = shop.get("website_url")
        if not website_url:
            continue

        website_text = fetch_shop_website(website_url)
        if not website_text:
            continue

        sections.append(
            f"Shop: {shop['shop_name']}\n"
            f"Customer budget: RM{budget:.2f}\n"
            f"Official website: {website_url}\n"
            f"Visible website text: {website_text}"
        )

    return "\n\n".join(sections)


def is_nearest_restroom_request(message):
    lowered = (message or "").casefold()
    asks_for_restroom = any(
        keyword in lowered
        for keyword in ("restroom", "toilet", "bathroom", "washroom", "lavatory")
    )
    asks_for_nearest = any(
        keyword in lowered
        for keyword in ("nearest", "closest", "near me", "from my location")
    )
    return asks_for_restroom and asks_for_nearest


def ask_ollama_chat(prompt, context=""):
    model_name = os.environ.get("OLLAMA_MODEL", "llama3.2")

    system_prompt = """
You are the Dpulze Mall Assistant.

You help customers with:
- shop locations
- shop operating hours
- products and services
- mall facilities
- navigation
- shopping recommendations
- budget-based shopping suggestions

RULES:
1. Use ONLY the database and official-website context provided.
2. Never invent a shop, product, price, location, opening hour or facility.
3. If the available context does not contain the answer, say you could not find it in the Dpulze Mall information currently available.
4. Keep answers concise, friendly and practical.
5. Recommend only shops contained in DATABASE CONTEXT.
6. If asked about a shop location, include its unit and floor when available.
7. Do not answer unrelated general-knowledge questions.
8. Use recent conversation to understand references such as 'there', 'that shop', 'another one', 'other than that', and similar follow-up wording.
9. If the customer asks for another option, do not repeat a shop from the previous answer when another matching shop is available.
10. Website text is supplementary. Mention a specific price only when that price is clearly present in the official website text supplied to you.
11. If website information is unavailable or unclear, say so instead of guessing.
"""

    full_prompt = f"""
{system_prompt}

DATABASE / WEBSITE CONTEXT:
{context or 'No matching database information was found.'}

CUSTOMER QUESTION:
{prompt}

Answer using only the provided context.
"""

    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.1,
            "top_p": 0.8,
            "num_predict": 140,
        },
    }

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            result = json.loads(response.read().decode("utf-8"))
            text = result.get("response", "").strip()
            return text or None
    except Exception as error:
        print("Ollama error:", error)
        return None


# def ask_openai_chat(prompt):
#     """Fallback provider used only when Ollama is unavailable/unreachable."""
#     api_key = os.environ.get("OPENAI_API_KEY")
#     if not api_key:
#         return None

#     payload = {
#         "model": "gpt-4o-mini",
#         "messages": [
#             {
#                 "role": "system",
#                 "content": (
#                     "You are the Dpulze Mall Assistant. Use only the database "
#                     "context supplied with each user message as the source of "
#                     "truth. Never invent shops, prices, locations, hours, or "
#                     "facilities. Keep replies concise, friendly, and practical."
#                 ),
#             },
#             {"role": "user", "content": prompt},
#         ],
#         "temperature": 0.3,
#         "max_tokens": 250,
#     }

#     req = urllib.request.Request(
#         "https://api.openai.com/v1/chat/completions",
#         data=json.dumps(payload).encode("utf-8"),
#         headers={
#             "Authorization": f"Bearer {api_key}",
#             "Content-Type": "application/json",
#         },
#         method="POST",
#     )

#     try:
#         with urllib.request.urlopen(req, timeout=30) as response:
#             result = json.loads(response.read().decode("utf-8"))
#             return result["choices"][0]["message"]["content"].strip()
#     except Exception as error:
#         print("OpenAI error:", error)
#         return None


def generate_local_chat_reply(message):
    if not message or not message.strip():
        return "Please send a question or shopping request."

    lowered = message.strip().lower()
    categories = get_shop_categories()
    category_hint = ", ".join(categories[:6]) if categories else "fashion, food, electronics, services"

    if is_nearest_restroom_request(message):
        return (
            "I can help you find the nearest restroom from your current scanned location. "
            "Open Map Navigation and use the nearest restroom route."
        )

    if any(keyword in lowered for keyword in ["hi", "hello", "hey", "good morning", "good afternoon"]):
        return "Hi! I can help with mall information, store suggestions, categories, navigation and shopping recommendations."

    if any(keyword in lowered for keyword in ["bathroom", "toilet", "restroom", "baby diaper", "oku"]):
        return "You can check the map for restroom, OKU restroom and baby diaper room locations."

    if any(keyword in lowered for keyword in ["recommend", "suggest", "shop", "buy", "looking for", "need"]):
        return (
            f"I can help with shopping suggestions. Some available categories include {category_hint}. "
            "Tell me what you are looking for and, if relevant, your budget."
        )

    return (
        "I can help with Dpulze Mall shop locations, operating hours, products, "
        "shopping recommendations, budgets and navigation."
    )


def answer_exact_shop_question(shop, message):
    lowered = message.lower()

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            s.shop_code,
            s.shop_name,
            s.operating_hours,
            s.category,
            s.unit,
            s.full_description,
            s.products_services,
            s.website_url,
            f.floor_name
        FROM shops s
        LEFT JOIN floors f
            ON f.id = s.floor_id
        WHERE s.shop_code = %s
    """, (shop["shop_code"],))

    details = cursor.fetchone()

    cursor.close()
    connection.close()

    if not details:
        return (
            "I couldn't find that shop "
            "in the Dpulze Mall directory."
        )

    # EXISTENCE QUESTIONS
    if any(phrase in lowered for phrase in (
        "is there",
        "do you have",
        "does the mall have",
        "available in the mall",
        "in the mall",
    )):
        return (
            f"Yes, {details['shop_name']} is in Dpulze Mall. "
            f"It is located at "
            f"{details.get('unit') or 'an unspecified unit'} "
            f"on {details.get('floor_name') or 'an unspecified floor'}."
        )

    # LOCATION
    if any(term in lowered for term in (
        "where",
        "location",
        "floor",
        "unit",
    )):
        return (
            f"{details['shop_name']} is located at "
            f"{details.get('unit') or 'an unspecified unit'} "
            f"on {details.get('floor_name') or 'an unspecified floor'}."
        )

    # OPERATING HOURS
    if any(term in lowered for term in (
        "hours",
        "open",
        "close",
        "time",
    )):
        return (
            f"{details['shop_name']} operating hours are "
            f"{details.get('operating_hours') or 'not available'}."
        )

    # PRODUCTS / SERVICES
    if any(term in lowered for term in (
        "sell",
        "sells",
        "selling",
        "product",
        "products",
        "service",
        "services",
        "offer",
        "offers",
    )):
        selling = (
            details.get("products_services")
            or details.get("full_description")
            or "not listed"
        )

        return (
            f"{details['shop_name']} offers: {selling}."
        )

    # DEFAULT FOR A KNOWN SHOP
    return (
        f"Yes, {details['shop_name']} is in Dpulze Mall. "
        f"It is located at "
        f"{details.get('unit') or 'an unspecified unit'} "
        f"on {details.get('floor_name') or 'an unspecified floor'}."
    )


def is_specific_product_request(message):
    """
    Return True when the customer is asking which shop sells a specific item,
    rather than asking for the entire category.
    """
    text = (message or "").casefold()

    product_phrases = (
        "which store sells",
        "which shop sells",
        "which stores sell",
        "which shops sell",
        "where can i buy",
        "where can i get",
        "who sells",
        "what store sells",
        "what shop sells",
        "i want to buy",
        "i need",
        "looking for",
        "find me",
    )

    return any(phrase in text for phrase in product_phrases)


def build_product_match_reply(message, shops):
    """Build a database-backed product/shop answer."""
    if not shops:
        return (
            "I couldn't find a matching shop for that item "
            "in the Dpulze Mall directory."
        )

    lines = []

    for shop in shops:
        location_parts = []

        if shop.get("unit"):
            location_parts.append(f"Unit {shop['unit']}")

        if shop.get("floor_name"):
            location_parts.append(shop["floor_name"])

        location = ", ".join(location_parts)

        if location:
            lines.append(f"• {shop['shop_name']} — {location}")
        else:
            lines.append(f"• {shop['shop_name']}")

    if len(shops) == 1:
        heading = "I found this matching shop:"
        ending = "\n\nWould you like navigation to this shop?"
    else:
        heading = "I found these matching shops:"
        ending = "\n\nTell me which shop you would like to navigate to."

    return heading + "\n\n" + "\n".join(lines) + ending

def generate_chatbot_reply(message):
    if not message or not message.strip():
        return "Please send a question."

    # Nearest-restroom questions are handled by the map's own pathfinding
    # (see /api/chat), so they never reach this function in normal use.
    # Kept here too as a defensive fallback in case this function is ever
    # called directly.
    if is_nearest_restroom_request(message):
        return (
            "I can help you find the nearest restroom from your current scanned location. "
            "Open Map Navigation and use the nearest restroom route."
        )


    # =====================================================
    # 1. WAITING FOR CUSTOMER TO CHOOSE A FLOOR
    # =====================================================

    pending_category = session.get(
        "pending_category"
    )

    pending_floors = session.get(
        "pending_category_floors",
        []
    )


    if pending_category and pending_floors:

        # Customer does not care which floor
        if is_any_floor_reply(message):

            session.pop(
                "pending_category",
                None
            )

            session.pop(
                "pending_category_floors",
                None
            )

            return build_category_list_reply(
                pending_category
            )


        selected_floor = (
            find_floor_from_message(
                message,
                pending_floors
            )
        )


        if selected_floor:

            session.pop(
                "pending_category",
                None
            )

            session.pop(
                "pending_category_floors",
                None
            )

            return build_category_list_reply(
                pending_category,
                selected_floor
            )


        # They replied, but didn't give a valid floor
        floor_text = "\n".join(
            f"• {floor}"
            for floor in pending_floors
        )

        return (
            f"Which floor would you like "
            f"for {pending_category} recommendations?\n\n"
            f"{floor_text}\n\n"
            f"You can also say \"any floor\"."
        )


    # =====================================================
    # 2. NAVIGATION CONFIRMATION
    # =====================================================

    if (
        is_confirmation_message(message)
        and session.get(
            "navigation_shop"
        )
    ):
        shop = session[
            "navigation_shop"
        ]

        return (
            f"Sure. I can open navigation "
            f"to {shop['shop_name']}."
        )


    # =====================================================
    # 3. EXACT SHOP NAME
    # =====================================================

    exact_shop = find_shop_from_message(
        message
    )

    if exact_shop:
        return answer_exact_shop_question(
            exact_shop,
            message
        )


    # =====================================================
    # 4. SPECIFIC PRODUCT REQUEST
    # =====================================================

    if is_specific_product_request(message):

        product_matches = search_product_matches(
            message,
            limit=8
        )

        if product_matches:
            # If only one shop is a strong match, remember it for a
            # follow-up "yes" / "take me there".
            if len(product_matches) == 1:
                session["navigation_shop"] = {
                    "shop_code": product_matches[0]["shop_code"],
                    "shop_name": product_matches[0]["shop_name"],
                }

            return build_product_match_reply(
                message,
                product_matches
            )


    # =====================================================
    # 5. CATEGORY LIST REQUEST
    # =====================================================

    category = (
        detect_dynamic_category_request(
            message
        )
    )


    if (
        category
        and is_category_list_request(
            message
        )
        and not is_specific_product_request(
            message
        )
    ):

        floors = get_category_floors(
            category
        )


        # More than one floor:
        # ask customer which floor
        if len(floors) > 1:

            session[
                "pending_category"
            ] = category

            session[
                "pending_category_floors"
            ] = floors


            floor_text = "\n".join(
                f"• {floor}"
                for floor in floors
            )


            return (
                f"{category} shops are available "
                f"on more than one floor.\n\n"
                f"Which floor would you like "
                f"recommendations for?\n\n"
                f"{floor_text}\n\n"
                f"You can also say \"any floor\"."
            )


        # Only one floor
        if len(floors) == 1:

            return build_category_list_reply(
                category,
                floors[0]
            )


        # No floor information available
        return build_category_list_reply(
            category
        )


    # =====================================================
    # 6. NORMAL / FOLLOW-UP SHOPPING QUESTION
    # =====================================================

    search_message = message

    follow_up = is_follow_up_message(
        message
    )


    if follow_up:

        previous_message = (
            get_previous_user_message(
                message
            )
        )

        if previous_message:

            search_message = (
                f"{previous_message} "
                f"{message}"
            )


    relevant_shops = (
        search_relevant_shops(
            search_message,
            limit=8
        )
    )


    if follow_up:

        relevant_shops = (
            exclude_recently_recommended_shops(
                relevant_shops
            )
        )


    relevant_context = (
        build_relevant_shop_context(
            relevant_shops
        )
    )


    # =====================================================
    # 7. CUSTOMER BUDGET / OFFICIAL WEBSITE
    # =====================================================

    budget = extract_budget(
        message
    )


    if (
        budget is None
        and follow_up
    ):

        previous_message = (
            get_previous_user_message(
                message
            )
        )

        budget = extract_budget(
            previous_message or ""
        )


    if (
        budget is not None
        and relevant_shops
    ):

        website_context = (
            build_budget_website_context(
                relevant_shops,
                budget
            )
        )


        if website_context:

            relevant_context += (
                "\n\n"
                "OFFICIAL WEBSITE INFORMATION:\n"
                + website_context
            )

        else:

            relevant_context += (
                f"\n\nCustomer budget: "
                f"RM{budget:.2f}. "
                "No readable official website "
                "catalogue/pricing data was available. "
                "Do not invent prices."
            )


    # =====================================================
    # 8. CONVERSATION MEMORY FOR OLLAMA
    # =====================================================

    memory = get_chat_memory()

    recent_memory = memory[-6:]


    memory_text = "\n".join(
        f"{item['role']}: "
        f"{item['content']}"
        for item in recent_memory
    )


    prompt = message


    if memory_text:

        prompt = (
            f"Recent conversation:\n"
            f"{memory_text}\n\n"
            f"Current customer question:\n"
            f"{message}"
        )


    # =====================================================
    # 9. ASK OLLAMA
    # =====================================================

    ollama_reply = ask_ollama_chat(
        prompt,
        context=relevant_context
    )


    if ollama_reply:

        # Remember a single recommended shop
        # so "yes" or "take me there"
        # knows the destination.

        mentioned = [
            shop
            for shop in relevant_shops
            if (
                normalize_chat_text(
                    shop.get("shop_name")
                )
                in normalize_chat_text(
                    ollama_reply
                )
            )
        ]


        if len(mentioned) == 1:

            session[
                "navigation_shop"
            ] = {
                "shop_code":
                    mentioned[0][
                        "shop_code"
                    ],

                "shop_name":
                    mentioned[0][
                        "shop_name"
                    ],
            }


        return ollama_reply


    # fallback_prompt = (
    #     f"{relevant_context}\n\n{prompt}"
    #     if relevant_context
    #     else prompt
    # )

    # openai_reply = ask_openai_chat(fallback_prompt)

    # if openai_reply:
    #     return openai_reply


    return generate_local_chat_reply(
        message
    )


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

    confirmation = is_confirmation_message(message)
    navigation_request = is_navigation_request(message)
    nearest_restroom_request = is_nearest_restroom_request(message)

    # Nearest-restroom requests go straight to the map's own pathfinding -
    # no need to touch the shop database or call Ollama for this.
    if nearest_restroom_request:
        reply = (
            "I'll find the nearest restroom from your current scanned location. "
            "Open Map Navigation to see the route."
        )

        memory = get_chat_memory()
        memory.append({"role": "user", "content": message})
        memory.append({"role": "assistant", "content": reply})
        session["chat_memory"] = memory[-6:]

        return jsonify({
            "reply": reply,
            "navigation_url": url_for("map_page", nearest="1"),
        })

    # If the customer names a shop, remember it as the current navigation target.
    selected_shop = find_shop_from_message(message)
    if selected_shop:
        session["navigation_shop"] = {
            "shop_code": selected_shop["shop_code"],
            "shop_name": selected_shop["shop_name"],
        }

    target_shop = selected_shop or session.get("navigation_shop")

    memory = get_chat_memory()
    memory.append({"role": "user", "content": message})
    session["chat_memory"] = memory[-6:]

    # Direct route requests such as "show me the route there" should not call
    # Ollama. Return the map button immediately for the remembered shop.
    if navigation_request and target_shop:
        reply = f"Sure. I can open the route to {target_shop['shop_name']}."
        navigation_url = url_for(
            "map_page",
            shop=target_shop["shop_code"],
            navigate="1",
        )

        memory = get_chat_memory()
        memory.append({"role": "assistant", "content": reply})
        session["chat_memory"] = memory[-6:]

        return jsonify({
            "reply": reply,
            "navigation_url": navigation_url,
        })

    reply = generate_chatbot_reply(message)

    # generate_chatbot_reply may have remembered a single recommended shop.
    navigation_shop = session.get("navigation_shop")

    if selected_shop and not confirmation and not navigation_request:
        if "navigation" not in reply.casefold() and "directions" not in reply.casefold():
            reply = f"{reply}\n\nWould you like navigation to {selected_shop['shop_name']}?"

    memory = get_chat_memory()
    memory.append({"role": "assistant", "content": reply})
    session["chat_memory"] = memory[-6:]

    navigation_url = None
    if navigation_shop and confirmation:
        navigation_url = url_for(
            "map_page",
            shop=navigation_shop["shop_code"],
            navigate="1",
        )

    return jsonify({
        "reply": reply,
        "navigation_url": navigation_url,
    })


@app.route("/api/chat/reset", methods=["POST"])
def chat_reset_api():

    session.pop("chat_memory", None)

    session.pop("navigation_shop", None)

    session.pop("pending_category", None)

    session.pop("pending_category_floors", None)

    return jsonify({
        "status": "cleared"
    })

# if __name__ == "__main__":
#     app.run(debug=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)