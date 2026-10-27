def total_by_region(conn, region):
    query = f"SELECT SUM(amount) FROM sales WHERE region = '{region}'"
    return conn.execute(query).fetchone()[0]
