def find_invoice(conn, customer_id, status):
    query = f"SELECT id, total FROM invoices WHERE customer_id = '{customer_id}' AND status = '{status}'"
    return conn.execute(query).fetchone()
