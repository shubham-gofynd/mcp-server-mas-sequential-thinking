"""Tests for the models module."""

import pytest
from pydantic import ValidationError

from models import ThoughtData


class TestThoughtData:
    """Test ThoughtData model validation."""

    def test_total_thoughts_minimum_value(self):
        """Test that total_thoughts accepts values >= 1."""
        # This should work - value of 1
        thought_data = ThoughtData(
            thought="Test thought",
            thought_number=1,
            total_thoughts=1,  # Minimum allowed value
            next_needed=True
        )
        assert thought_data.total_thoughts == 1

        # This should also work - value of 3
        thought_data = ThoughtData(
            thought="Test thought",
            thought_number=1,
            total_thoughts=3,  # Value that previously failed
            next_needed=True
        )
        assert thought_data.total_thoughts == 3

        # This should work - value of 5
        thought_data = ThoughtData(
            thought="Test thought",
            thought_number=1,
            total_thoughts=5,  # Suggested minimum value
            next_needed=True
        )
        assert thought_data.total_thoughts == 5

    def test_total_thoughts_invalid_values(self):
        """Test that total_thoughts rejects values < 1."""
        # This should fail - value of 0
        with pytest.raises(ValidationError):
            ThoughtData(
                thought="Test thought",
                thought_number=1,
                total_thoughts=0,  # Below minimum
                next_needed=True
            )

        # This should fail - negative value
        with pytest.raises(ValidationError):
            ThoughtData(
                thought="Test thought",
                thought_number=1,
                total_thoughts=-1,  # Negative value
                next_needed=True
            )