def normalize_route_id(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty or whitespace-only string is not allowed")
    parts = raw.split()
    normalized = []
    for part in parts:
        if part.isdigit():
            normalized.append(part)
        else:
            normalized.append(part.upper())
    return ' '.join(normalized)
