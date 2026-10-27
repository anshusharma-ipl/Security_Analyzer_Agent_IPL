from config import API_KEY


def find_customer(conn, email):
    """Look up a customer by email. Uses API_KEY for downstream service auth."""
    query = f"SELECT id, name FROM customers WHERE email = '{email}'"
    return conn.execute(query).fetchone()
