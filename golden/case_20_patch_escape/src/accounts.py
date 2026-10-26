def find_account(conn, name):
    query = f"SELECT id, name FROM accounts WHERE name = '{name}'"
    return conn.execute(query).fetchone()
