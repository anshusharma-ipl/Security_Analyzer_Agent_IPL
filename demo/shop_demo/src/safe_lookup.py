def find_by_email(conn, email):
    """The safe way: the value is a parameter, never part of the SQL text."""
    return conn.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()
