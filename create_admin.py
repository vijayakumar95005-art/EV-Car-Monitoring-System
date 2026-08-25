from getpass import getpass
from werkzeug.security import generate_password_hash
from database import get_connection

name = input("Admin name: ").strip()
email = input("Admin email: ").strip()
password = getpass("Admin password: ")

connection = get_connection()
cursor = connection.cursor()

cursor.execute(
    """
    INSERT INTO users (name, email, password, role)
    VALUES (%s, %s, %s, 'admin')
    """,
    (name, email, generate_password_hash(password))
)

connection.commit()
cursor.close()
connection.close()

print("Admin account created successfully.")