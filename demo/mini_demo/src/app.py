from customers import find_customer
from reports import run_report


def handle_customer(conn, request):
    return find_customer(conn, request["email"])


def handle_report(conn, request):
    return run_report(conn, request["filter"])
