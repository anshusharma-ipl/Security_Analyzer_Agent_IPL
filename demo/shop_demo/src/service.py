from db import run


def search_users(conn, name):
    sql = f"SELECT id, name FROM users WHERE name = '{name}'"
    return run(conn, sql)
