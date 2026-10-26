from service import search_users


def handle_search(conn, params):
    rows = search_users(conn, params.get("name", ""))
    return [row[1] for row in rows]
