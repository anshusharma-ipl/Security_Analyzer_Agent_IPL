def find_product(conn, sku):
    query = f"SELECT id, name, price FROM products WHERE sku = '{sku}'"
    return conn.execute(query).fetchone()
