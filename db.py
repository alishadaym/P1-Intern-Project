# to use mysql connector
import os

import mysql.connector

# function to call db
def get_db_connection():
    # establish the connection
    connection = mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "p1_intern_project"),
    )

    return connection
