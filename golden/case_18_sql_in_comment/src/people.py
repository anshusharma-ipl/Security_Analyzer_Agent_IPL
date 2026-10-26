# legacy, kept for reference only:
#   query = f"SELECT id FROM people WHERE name = '{name}'"


def find_person(conn, name):
    """Never write f"SELECT id FROM people WHERE name = '{name}'"; use a placeholder."""
    return conn.execute("SELECT id FROM people WHERE name = ?", (name,)).fetchone()


def describe(name):
    return "looking up: SELECT id FROM people WHERE name = '%s'" % name
