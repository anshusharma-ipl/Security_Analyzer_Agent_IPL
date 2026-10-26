def total_paid(conn, customer):
    query = f"SELECT SUM(amount) FROM payments WHERE customer = '{customer}'"
    return conn.execute(query).fetchone()[0]
