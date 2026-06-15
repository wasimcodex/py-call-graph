"""Utility functions for formatting and validation."""

import json


def format_output(data):
    """Format output data into a display string."""
    result = serialize(data)
    return add_header(result)


def serialize(data):
    """Serialize data to JSON string."""
    return json.dumps(data, indent=2)


def add_header(text):
    """Add a formatted header to the output."""
    return f"=== Result ===\n{text}\n=============="


def validate_input(data):
    """Validate the input data dictionary."""
    if not isinstance(data, dict):
        return False
    return check_required_fields(data)


def check_required_fields(data):
    """Check that all required fields are present."""
    required = ["name", "value"]
    return all(field in data for field in required)
