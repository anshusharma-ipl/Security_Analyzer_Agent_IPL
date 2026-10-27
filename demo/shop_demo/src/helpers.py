def format_price(amount):
    """Format a price in cents as a currency string."""
    return f"${amount / 100:.2f}"


def paginate(items, page, page_size=10):
    """Return a slice of items for the given page (1-based)."""
    start = (page - 1) * page_size
    return items[start: start + page_size]
