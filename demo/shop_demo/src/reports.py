def run_report(conn, condition):
    """Clients send a SQL condition such as 'amount > 100'."""
    sql = f"SELECT * FROM orders WHERE {condition}"
    return conn.execute(sql).fetchall()
