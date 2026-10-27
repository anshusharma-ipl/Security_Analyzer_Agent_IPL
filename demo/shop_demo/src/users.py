def find_user(conn, name):
    query = f"SELECT id, name FROM users WHERE name = '{name}'"
    return conn.execute(query).fetchone()
