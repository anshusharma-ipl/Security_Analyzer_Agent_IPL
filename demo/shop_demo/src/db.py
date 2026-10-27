def run(conn, sql):
    return conn.execute(sql).fetchall()
