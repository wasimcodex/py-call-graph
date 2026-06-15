"""Notification service."""


class Notifier:
    """Handles sending notifications through various channels."""

    def __init__(self):
        self.channels = ["email", "slack"]

    def send(self, message):
        """Send a notification through all channels."""
        for channel in self.channels:
            self._dispatch(channel, message)

    def _dispatch(self, channel, message):
        """Dispatch a message to a specific channel."""
        formatted = self._format_for_channel(channel, message)
        print(f"[{channel.upper()}] {formatted}")

    def _format_for_channel(self, channel, message):
        """Format message for a specific channel."""
        if channel == "slack":
            return f":bell: {message}"
        return message
