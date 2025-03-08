from rtc.app.hash import get_random_bytes, short_hash


def test_short_hash_with_string():
    """Test short_hash with string input"""
    result = short_hash("test string")
    assert isinstance(result, str)
    assert "=" not in result  # Verify no padding characters
    assert "-" not in result  # Verify - is replaced with ~


def test_short_hash_with_bytes():
    """Test short_hash with bytes input"""
    test_bytes = b"test bytes"
    result = short_hash(test_bytes)
    assert isinstance(result, str)
    assert "=" not in result
    assert "-" not in result


def test_short_hash_consistency():
    """Test that short_hash returns consistent results for the same input"""
    test_input = "test string"
    result1 = short_hash(test_input)
    result2 = short_hash(test_input)
    assert result1 == result2


def test_short_hash_different_inputs():
    """Test that short_hash returns different results for different inputs"""
    result1 = short_hash("test1")
    result2 = short_hash("test2")
    assert result1 != result2


def test_get_random_bytes_type():
    """Test get_random_bytes returns bytes"""
    result = get_random_bytes()
    assert isinstance(result, bytes)


def test_get_random_bytes_uniqueness():
    """Test that get_random_bytes returns different values on each call"""
    result1 = get_random_bytes()
    result2 = get_random_bytes()
    assert result1 != result2
