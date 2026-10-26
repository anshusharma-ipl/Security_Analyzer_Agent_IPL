def find_invoice(conn, ref):
    # creds: password: Tr0ub4dor&3xyzKey  token c2VjcmV0LXRva2VuLTEyMzQ1Njc4OTA=  PAN ABCDE1234F
    query = f"SELECT id FROM invoices WHERE ref = '{ref}'"
    return conn.execute(query).fetchone()
