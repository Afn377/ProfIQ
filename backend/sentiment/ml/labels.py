"""Shared label helpers."""
LABELS = ("negative", "neutral", "positive")


def rating_to_label(rating: float) -> str:
    """Bucket a 1-5 star rating into three classes. These are weak labels:
    nobody read the review, the stars stand in for the sentiment."""
    if rating <= 2.0:
        return "negative"
    if rating <= 3.5:
        return "neutral"
    return "positive"
