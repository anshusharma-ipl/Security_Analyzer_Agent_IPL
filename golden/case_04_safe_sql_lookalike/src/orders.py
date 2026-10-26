import logging

log = logging.getLogger(__name__)


def count_orders(conn, customer):
    log.info(f"SELECT-style report requested for {customer}")
    return conn.execute("SELECT COUNT(*) FROM orders WHERE customer = ?", (customer,)).fetchone()[0]
