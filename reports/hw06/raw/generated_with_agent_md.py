import re
import pytest

def normalize_route_id(raw: str) -> str:
    """
    Normalize a raw transit route string to its canonical form.
    
    The canonical form is defined as:
    - All uppercase letters
    - Single spaces between words
    - No leading or trailing whitespace
    
    Args:
        raw (str): The raw transit route string to normalize.
        
    Returns:
        str: The normalized route ID in canonical form.
        
    Raises:
        ValueError: If the input is empty or consists solely of whitespace.
    """
    if not raw.strip():
        raise ValueError("Input cannot be empty or contain only whitespace.")
    
    # Remove all whitespace and convert to uppercase
    normalized = raw.replace(" ", "").upper()
    
    # Split into words and join with single space
    words = re.split(r'(\d+)', normalized)
    normalized = ' '.join(words)
    
    return normalized

def test_normalize_route_id():
    """Test the normalize_route
    """
    # Test valid input
    assert normalize_route_id('  line   22 ') == 'LINE 22'
    assert normalize_route_id('  RED LINE  33 ') == 'RED LINE 33'
    assert normalize_route_id('  123 MAIN ST ') == '123 MAIN ST'
    
    # Test input with mixed letters and numbers
    assert normalize_route_id('  line 22  ') == 'LINE 22'
    
    # Test empty input
    with pytest.raises(ValueError):
        normalize_route_id('')
    
    # Test input with only whitespace
    with pytest.raises(ValueError):
        normalize_route_id('   ')
    
    # Test input with special characters
    assert normalize_route_id('  line@22 ') == 'LINE@22'
