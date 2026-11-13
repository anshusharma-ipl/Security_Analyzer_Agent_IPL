from customers import find_customer
from invoices import find_invoice
from products import find_product
from reports import run_report


def handle_customer(conn, request):
    return find_customer(conn, request["email"])


def handle_invoice(conn, request):
    return find_invoice(conn, request["customer_id"], request["status"])


def handle_product(conn, request):
    return find_product(conn, request["sku"])


def handle_report(conn, request):
    return run_report(conn, request["filter"])
