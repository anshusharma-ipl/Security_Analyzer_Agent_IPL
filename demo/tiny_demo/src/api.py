from search import find_user
from ping import check_host


def handle_search(conn, params):
    """GET /search?name=... — find a user by name."""
    return find_user(conn, params.get("name", ""))


def handle_ping(params):
    """GET /ping?host=... — check if a host is reachable."""
    return check_host(params.get("host", "localhost"))
