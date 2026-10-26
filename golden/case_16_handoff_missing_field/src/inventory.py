def find_item(conn, sku):
    query = f"SELECT id, qty FROM items WHERE sku = '{sku}'"
    return conn.execute(query).fetchone()
