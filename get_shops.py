from db import get_db_connection


connection = get_db_connection()
cursor = connection.cursor(dictionary=True)

cursor.execute("SELECT * FROM shops")

shops = cursor.fetchall()

for shop in shops:
    print(shop)

cursor.close()
connection.close()