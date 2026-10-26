TABLE = "users"
STATE = "active"


def count_active(conn):
    query = f"SELECT COUNT(*) FROM {TABLE} WHERE state = '{STATE}'"
    return conn.execute(query).fetchone()[0]
