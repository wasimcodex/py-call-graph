"""Main application entry point."""

from test_project.utils import format_output, validate_input
from test_project.services.processor import DataProcessor
from test_project.services.notifier import Notifier


def main():
    """Application entry point that orchestrates the pipeline."""
    data = get_user_data()
    if validate_input(data):
        processor = DataProcessor()
        result = processor.process(data)
        formatted = format_output(result)
        notify_completion(formatted)
    else:
        handle_error("Invalid input data")


def get_user_data():
    """Simulate fetching user data."""
    return {"name": "Alice", "value": 42}


def notify_completion(message):
    """Send a notification after processing."""
    notifier = Notifier()
    notifier.send(message)


def handle_error(msg):
    """Handle application errors."""
    log_error(msg)
    print(f"ERROR: {msg}")


def log_error(msg):
    """Log an error message."""
    print(f"[LOG] {msg}")
