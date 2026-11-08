"""Adversarial sentence-to-archive-image resolver.

This package starts with the golden-dataset contract: labelled history-video
sentences, their acceptable archive images, and hard negatives. Retrieval and
the adversarial panel are layered on top in later stages.
"""

from mnemosyne.resolver.golden import GoldenFileError, load_golden
from mnemosyne.resolver.models import (
    GoldenClaim,
    GoldenGold,
    GoldenImage,
    GoldenSegment,
    GoldenSentence,
    GoldenVideo,
    HardNegative,
)

__all__ = [
    "GoldenClaim",
    "GoldenFileError",
    "GoldenGold",
    "GoldenImage",
    "GoldenSegment",
    "GoldenSentence",
    "GoldenVideo",
    "HardNegative",
    "load_golden",
]
