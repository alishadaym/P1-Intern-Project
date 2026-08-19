print("TEST START")

from db import get_db_connection

print("Trying to connect...")

connection = get_db_connection()

print("Connection object:", connection)

if connection.is_connected():
    print("Successfully connected to MySQL!")

connection.close()

print("TEST END")