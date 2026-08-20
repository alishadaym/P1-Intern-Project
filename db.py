# to use mysql connector
import mysql.connector

# function to call db
def get_db_connection():
    # establish the connection
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="p1_intern_project"
    )

    return connection