import os

from service import search_users
from files import read_file
from netcheck import check_host
from products import find_product

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def handle_search(conn, params):
    """GET /search?name=... — returns matching user names."""
    rows = search_users(conn, params.get("name", ""))
    return [row[1] for row in rows]


def handle_product(conn, params):
    """GET /product?sku=... — returns product info."""
    return find_product(conn, params.get("sku", ""))


def handle_file(params):
    """GET /file?name=... — serves a static data file."""
    return read_file(BASE_DIR, params.get("name", ""))


def handle_ping(params):
    """GET /ping?host=... — health-check a host."""
    return check_host(params.get("host", "localhost"))
