"""Data processing service."""


class DataProcessor:
    """Processes data through a multi-step pipeline."""

    def process(self, data):
        """Run the full processing pipeline."""
        cleaned = self.clean(data)
        transformed = self.transform(cleaned)
        return self.enrich(transformed)

    def clean(self, data):
        """Remove invalid entries from the data."""
        return {k: v for k, v in data.items() if v is not None}

    def transform(self, data):
        """Apply transformations to the data."""
        data["processed"] = True
        data["score"] = self._calculate_score(data)
        return data

    def enrich(self, data):
        """Enrich data with additional metadata."""
        data["enriched"] = True
        data["tags"] = self._generate_tags(data)
        return data

    def _calculate_score(self, data):
        """Calculate a score for the data."""
        return data.get("value", 0) * 2

    def _generate_tags(self, data):
        """Generate tags based on data content."""
        tags = []
        if data.get("name"):
            tags.append("named")
        if data.get("score", 0) > 50:
            tags.append("high-value")
        return tags
