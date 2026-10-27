def find_customer(conn, email):
    query = f"SELECT id, name FROM customers WHERE email = '{email}'"
    return conn.execute(query).fetchone()
