def find_user(conn, name):
    query = f"SELECT id FROM users WHERE name = '{name}'"
    return conn.execute(query).fetchone()


def find_admin(conn, name):
    query = f"SELECT id FROM admins WHERE name = '{name}'"
    return conn.execute(query).fetchone()
