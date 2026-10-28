def run(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()
