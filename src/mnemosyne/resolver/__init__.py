"""Adversarial sentence-to-archive-image resolver.

Two datasets, two jobs: `resolver_corpus` holds the sentences to process (any
transcript segment), `resolver_golden` holds the *evaluated* pairs used to
benchmark the resolver. Retrieval and the adversarial panel are layered on top.
"""

from mnemosyne.resolver.corpus import CorpusFileError, load_corpus
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
    "CorpusFileError",
    "GoldenClaim",
    "GoldenFileError",
    "GoldenGold",
    "GoldenImage",
    "GoldenSegment",
    "GoldenSentence",
    "GoldenVideo",
    "HardNegative",
    "load_corpus",
    "load_golden",
]
