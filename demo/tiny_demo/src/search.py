from db import run


def find_user(conn, name):
    sql = f"SELECT id, name FROM users WHERE name = '{name}'"
    return run(conn, sql)
