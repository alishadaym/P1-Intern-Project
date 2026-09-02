"""Simulate random restroom cubicle occupancy for local development.

Run this in a separate terminal while Flask is running. Each occupied cubicle
stays occupied for a random duration between two and five minutes, then
becomes available automatically.
"""

from datetime import datetime, timedelta
import random
import time

from db import get_db_connection

MIN_OCCUPIED_SECONDS = 120
MAX_OCCUPIED_SECONDS = 300
CHECK_EVERY_SECONDS = 5
QUIET_GAP_SECONDS = 300
occupied_until = {}
quiet_until = None
wave_target = None


def normalize_utility_type(value):
    """Normalize utility types from the database to the app's facility names."""
    if value is None:
        return ""

    normalized = " ".join(str(value).strip().lower().replace("_", " ").split())
    if "toilet" in normalized or "restroom" in normalized:
        return "restroom"
    if "baby" in normalized and "diaper" in normalized:
        return "baby_diaper"
    if "oku" in normalized:
        return "oku"
    return normalized


def get_occupied_utility_types():
    return ("restroom", "baby_diaper", "oku")


def get_room_capacity(utility_type):
    normalized = normalize_utility_type(utility_type)
    if normalized == "oku":
        return 1
    if normalized == "baby_diaper":
        return 3
    return None


def get_wave_target(current_time):
    """Return a realistic number of simultaneous restroom users."""
    is_weekday = current_time.weekday() < 5
    hour = current_time.hour

    if is_weekday and 10 <= hour < 12:
        return random.randint(2, 2)
    if is_weekday and 12 <= hour < 14:
        return random.randint(2, 3)
    if is_weekday and 17 <= hour < 21:
        return random.randint(2, 3)
    if is_weekday:
        return random.randint(1, 2)

    return random.randint(2, 3)


def get_supported_cubicles(cursor):
    cursor.execute("""
        SELECT c.id, c.status, c.updated_at, u.utility_type
        FROM cubicles c
        JOIN utilities u ON u.id = c.utility_id
    """)

    cubicles = []
    for cubicle in cursor.fetchall():
        utility_type = normalize_utility_type(cubicle["utility_type"])
        if utility_type in get_occupied_utility_types():
            cubicles.append({
                "id": cubicle["id"],
                "status": str(cubicle["status"] or "").strip().lower(),
                "updated_at": cubicle["updated_at"],
                "utility_type": utility_type,
            })
    return cubicles


def update_occupancy():
    global quiet_until, wave_target

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT NOW() AS db_now")
    current_time = cursor.fetchone()["db_now"]
    cubicles = get_supported_cubicles(cursor)

    released_count = 0
    for cubicle in cubicles:
        if cubicle["status"] != "occupied":
            continue

        expiry = occupied_until.setdefault(
            cubicle["id"],
            cubicle["updated_at"] + timedelta(
                seconds=random.randint(MIN_OCCUPIED_SECONDS, MAX_OCCUPIED_SECONDS)
            )
        )

        if current_time >= expiry:
            cursor.execute("""
                UPDATE cubicles
                SET status = 'Available', updated_at = NOW()
                WHERE id = %s
            """, (cubicle["id"],))
            released_count += cursor.rowcount
            occupied_until.pop(cubicle["id"], None)

    active_count = sum(
        1 for cubicle in cubicles if cubicle["status"] == "occupied"
    )

    occupied_count = 0
    if active_count == 0:
        if wave_target is not None:
            wave_target = None
            quiet_until = current_time + timedelta(seconds=QUIET_GAP_SECONDS)

        if quiet_until is None or current_time >= quiet_until:
            wave_target = get_wave_target(current_time)
            available_by_type = {}
            for cubicle in cubicles:
                if cubicle["status"] != "available":
                    continue
                available_by_type.setdefault(cubicle["utility_type"], []).append(cubicle)

            for utility_type in get_occupied_utility_types():
                available_cubicles = available_by_type.get(utility_type, [])
                if not available_cubicles:
                    continue

                capacity = get_room_capacity(utility_type)
                if utility_type == "oku":
                    max_to_occupy = 1
                elif utility_type == "baby_diaper":
                    max_to_occupy = min(len(available_cubicles), min(wave_target, 3))
                else:
                    max_to_occupy = min(len(available_cubicles), wave_target)

                if capacity is not None:
                    max_to_occupy = min(max_to_occupy, capacity)

                random.shuffle(available_cubicles)
                for cubicle in available_cubicles[:max_to_occupy]:
                    occupied_until[cubicle["id"]] = current_time + timedelta(
                        seconds=random.randint(MIN_OCCUPIED_SECONDS, MAX_OCCUPIED_SECONDS)
                    )
                    cursor.execute("""
                        UPDATE cubicles
                        SET status = 'Occupied', updated_at = NOW()
                        WHERE id = %s
                    """, (cubicle["id"],))
                    occupied_count += cursor.rowcount
    elif wave_target is None:
        wave_target = active_count

    connection.commit()
    cursor.close()
    connection.close()

    return released_count, occupied_count


def run_simulator():
    print("Occupancy simulator started. Cubicles stay occupied for 2 to 5 minutes.")

    while True:
        try:
            released_count, occupied_count = update_occupancy()
            if released_count or occupied_count:
                print(
                    f"Released: {released_count}; "
                    f"newly occupied: {occupied_count}"
                )
            time.sleep(CHECK_EVERY_SECONDS)
        except Exception as error:
            print(f"Occupancy simulator error: {error}")
            time.sleep(CHECK_EVERY_SECONDS)


def main():
    try:
        run_simulator()
    except KeyboardInterrupt:
        print("Occupancy simulator stopped.")


if __name__ == "__main__":
    main()
