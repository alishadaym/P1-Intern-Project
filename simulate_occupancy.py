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


def update_occupancy():
    global quiet_until, wave_target

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT NOW() AS db_now")
    current_time = cursor.fetchone()["db_now"]

    cursor.execute("""
        SELECT c.id, c.updated_at
        FROM cubicles c
        JOIN utilities u ON u.id = c.utility_id
        WHERE LOWER(u.utility_type) IN ('restroom', 'toilet')
          AND LOWER(c.status) = 'occupied'
    """)

    released_count = 0
    for cubicle in cursor.fetchall():
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

    cursor.execute("""
        SELECT c.id
        FROM cubicles c
        JOIN utilities u ON u.id = c.utility_id
        WHERE LOWER(u.utility_type) IN ('restroom', 'toilet')
          AND LOWER(c.status) = 'occupied'
    """)
    active_count = len(cursor.fetchall())

    occupied_count = 0
    if active_count == 0:
        if wave_target is not None:
            wave_target = None
            quiet_until = current_time + timedelta(seconds=QUIET_GAP_SECONDS)

        if quiet_until is None or current_time >= quiet_until:
            wave_target = get_wave_target(current_time)
            cursor.execute("""
                SELECT c.id
                FROM cubicles c
                JOIN utilities u ON u.id = c.utility_id
                WHERE LOWER(u.utility_type) IN ('restroom', 'toilet')
                  AND LOWER(c.status) = 'available'
                ORDER BY RAND()
                LIMIT %s
            """, (wave_target,))
            available_cubicles = cursor.fetchall()

            for cubicle in available_cubicles:
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
