def find_product(conn, sku):
    query = f"SELECT id, name, price FROM products WHERE sku = '{sku}'"
    cursor = conn.cursor()
    return cursor.execute(query).fetchone()
