"""Read the full LinkedIn cookie jar from the local Chrome at runtime (handles rotation)."""


def playwright_cookies():
    import browser_cookie3 as bc
    cj = bc.chrome(domain_name="linkedin.com")
    out = []
    for c in cj:
        ck = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain if c.domain.startswith(".") else c.domain,
            "path": c.path or "/",
            "secure": bool(c.secure),
        }
        if c.expires:
            ck["expires"] = float(c.expires)
        out.append(ck)
    return out
