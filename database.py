import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection():

    connection = mysql.connector.connect(
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"]
)

    return connection


if __name__ == "__main__":

    connection = get_connection()

    if connection.is_connected():
        print("MySQL connected successfully!")

    connection.close()

