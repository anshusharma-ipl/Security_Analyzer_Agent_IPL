def find_payment(conn, ref):
    query = f"SELECT id, amount FROM payments WHERE ref = '{ref}'"
    return conn.execute(query).fetchone()
