def normalize_route_id(raw: str) -> str:
    """
    Normalize a transit route string by converting to uppercase, removing leading/trailing whitespace,
    and replacing multiple spaces with a single space. Numeric parts are preserved as-is.

    Args:
        raw (str): The raw route string to normalize.

    Returns:
        str: The normalized route string in canonical form.

    Raises:
        ValueError: If the input is empty or consists only of whitespace.
    """
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


def test_normalize_route_id():
    """Test the normalize_route_id function with various cases."""
    # Valid input cases
    assert normalize_route_id('  line   22 ') == 'LINE 23'
    assert normalize_route_id('BUS 100') == 'BUS 100'
    assert normalize_route_id('  300   express ') == '300 EXPRESS'
    assert normalize_route_id('  300   200 ') == '300 200'

    # Empty input case
    try:
        normalize_route_id('')
    except ValueError as e:
        assert str(e) == "Empty or whitespace-only string is not allowed"
    else:
        assert False, "Expected ValueError for empty input"

    # Whitespace-only input case
    try:
        normalize_route_id('   ')
    except ValueError as e:
        assert str(e) == "Empty or whitespace-only string is not allowed"
    else:
        assert False, "Expected ValueError for whitespace-only input"
