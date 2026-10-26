def greet():
    return "ready"


def build(conn, n):
    query = f"SELECT id FROM users WHERE name = '{n}'"
    return run(conn, query)


def run(conn, query):
    return conn.execute(query).fetchone()
