"""
Swedish Compound Splitter - Dictionary-based decompounding
=========================================================

Splits Swedish compound words into constituent parts for improved BM25 recall.
Uses Hunspell Swedish dictionary + custom legal terminology.

Strategy (from Gemini research):
- Index-time expansion: "trafikskadelagen" → ["trafikskadelagen", "trafik", "skade", "lag"]
- Keeps original word for exact match (highest score)
- Adds components for partial match (recall boost)

Swedish compound structure:
- Head word at the end (determines grammatical properties)
- Linking morphemes: -s-, -n-, -e-, -a- (most common: -s-)
- Example: "arbets-givar-avgift" = arbete + s + givare + avgift

Usage:
    splitter = SwedishCompoundSplitter()
    parts = splitter.split("trafikskadelagen")
    # Returns: ["trafikskadelagen", "trafik", "skade", "lag"]
"""

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger("constitutional.compound_splitter")

# Hunspell dictionary location (Ubuntu/Debian)
HUNSPELL_DICT_PATH = Path("/usr/share/hunspell/sv_SE.dic")

# Minimum word length for splitting (avoid noise)
MIN_WORD_LENGTH = 8

# Minimum component length (avoid single-letter junk)
MIN_COMPONENT_LENGTH = 3

# Swedish linking morphemes (fugenmorpheme)
# These appear between compound parts
LINKING_MORPHEMES = ["s", "n", "e", "a", "o", "u"]

# Common Swedish prefixes that should NOT be split off alone
NON_SPLIT_PREFIXES = {
    "för",
    "be",
    "ge",
    "er",
    "an",
    "av",
    "på",
    "in",
    "ut",
    "om",
    "upp",
    "ned",
    "ner",
    "sam",
    "mis",
    "van",
    "oför",
    "obe",
}

# Legal domain stopwords - words too common to be useful as split parts
LEGAL_STOPWORDS = {
    "och",
    "att",
    "det",
    "som",
    "den",
    "för",
    "med",
    "har",
    "kan",
    "ska",
    "vid",
    "till",
    "var",
    "sig",
    "men",
    "eller",
    "från",
    "när",
    "där",
}


class SwedishCompoundSplitter:
    """
    Dictionary-based Swedish compound word splitter.

    Uses greedy longest-match from right (Swedish head words are at end).
    Handles linking morphemes (-s-, -n-, etc.).
    """

    def __init__(
        self,
        dict_path: Optional[Path] = None,
        min_word_length: int = MIN_WORD_LENGTH,
        min_component_length: int = MIN_COMPONENT_LENGTH,
    ):
        """
        Initialize compound splitter.

        Args:
            dict_path: Path to Hunspell .dic file (default: Swedish SE)
            min_word_length: Only split words longer than this
            min_component_length: Minimum length for split parts
        """
        self.dict_path = dict_path or HUNSPELL_DICT_PATH
        self.min_word_length = min_word_length
        self.min_component_length = min_component_length
        self._word_set: Optional[Set[str]] = None
        self._loaded = False

    def _ensure_loaded(self) -> bool:
        """Lazy load dictionary on first use."""
        if self._loaded:
            return True

        if not self.dict_path.exists():
            logger.warning(f"Swedish dictionary not found at {self.dict_path}")
            return False

        try:
            self._word_set = self._load_dictionary()
            self._loaded = True
            logger.info(f"Loaded Swedish dictionary: {len(self._word_set):,} words")
            return True
        except Exception as e:
            logger.error(f"Failed to load dictionary: {e}")
            return False

    def _load_dictionary(self) -> Set[str]:
        """
        Load words from Hunspell dictionary file.

        Hunspell format: word/flags (one per line)
        First line is word count.
        """
        words = set()

        with open(self.dict_path, "r", encoding="utf-8", errors="ignore") as f:
            # Skip first line (word count)
            next(f, None)

            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Extract word (before / if present)
                word = line.split("/")[0].lower()

                # Skip very short words, punctuation, numbers
                if len(word) >= self.min_component_length and word.isalpha():
                    words.add(word)

        return words

    def _is_word(self, s: str) -> bool:
        """Check if string is a known Swedish word."""
        if not self._ensure_loaded() or not self._word_set:
            return False
        return s.lower() in self._word_set

    def split(self, word: str) -> List[str]:
        """
        Split a compound word into parts.

        Args:
            word: Swedish word to split

        Returns:
            List starting with original word, followed by components.
            If no valid split found, returns [word].

        Example:
            split("trafikskadelagen") → ["trafikskadelagen", "trafik", "skade", "lag"]
        """
        if not word or len(word) < self.min_word_length:
            return [word] if word else []

        word_lower = word.lower()

        # Skip if in stopwords
        if word_lower in LEGAL_STOPWORDS:
            return [word]

        # Try to find valid splits
        parts = self._find_splits(word_lower)

        if parts and len(parts) > 1:
            # Return original + components (without duplicates)
            result = [word]  # Original form preserved
            for part in parts:
                if part.lower() != word_lower and part not in result:
                    result.append(part)
            return result

        return [word]

    def _find_splits(self, word: str) -> List[str]:
        """
        Find valid compound splits using iterative approach.

        Strategy:
        1. Try simple 2-part splits first (most common)
        2. Then try 3-part splits
        3. Score and pick the best split

        Swedish compounds have the head word at the end.
        """
        if not self._ensure_loaded():
            return [word]

        candidates = []

        # Try 2-part splits
        for split in self._find_two_part_splits(word):
            candidates.append(split)

        # Try 3-part splits
        for split in self._find_three_part_splits(word):
            candidates.append(split)

        # Pick best split (prefer fewer, longer parts)
        if candidates:
            best = max(candidates, key=lambda s: self._score_split(s))
            # Only return if score is good enough
            if self._score_split(best) > 0:
                return best

        return [word]

    def _find_two_part_splits(self, word: str) -> List[List[str]]:
        """Find all valid 2-part splits."""
        results = []

        for i in range(self.min_component_length, len(word) - self.min_component_length + 1):
            prefix = word[:i]
            suffix = word[i:]

            # Direct match
            if self._is_word(prefix) and self._is_word(suffix):
                results.append([prefix, suffix])
                continue

            # Try removing linking morpheme from prefix
            for morph in LINKING_MORPHEMES:
                if prefix.endswith(morph) and len(prefix) > len(morph) + 2:
                    base = prefix[: -len(morph)]
                    if self._is_word(base) and self._is_word(suffix):
                        results.append([base, suffix])

            # Handle suffix inflections (e.g., lagen → lag)
            for ending in ["en", "n", "et", "t", "er", "ar", "or"]:
                if suffix.endswith(ending) and len(suffix) > len(ending) + 2:
                    base_suffix = suffix[: -len(ending)]
                    if self._is_word(prefix) and self._is_word(base_suffix):
                        results.append([prefix, base_suffix])
                    # Also try with linking morpheme
                    for morph in LINKING_MORPHEMES:
                        if prefix.endswith(morph) and len(prefix) > len(morph) + 2:
                            base_prefix = prefix[: -len(morph)]
                            if self._is_word(base_prefix) and self._is_word(base_suffix):
                                results.append([base_prefix, base_suffix])

        return results

    def _find_three_part_splits(self, word: str) -> List[List[str]]:
        """Find valid 3-part splits."""
        results = []
        min_len = self.min_component_length

        for i in range(min_len, len(word) - 2 * min_len + 1):
            for j in range(i + min_len, len(word) - min_len + 1):
                part1 = word[:i]
                part2 = word[i:j]
                part3 = word[j:]

                # Try various combinations with linking morpheme removal
                # parts_valid removed - unused

                # Check part1
                if self._is_word(part1):
                    p1 = part1
                else:
                    p1 = self._strip_linking_morpheme(part1)
                    if not p1:
                        continue

                # Check part2
                if self._is_word(part2):
                    p2 = part2
                else:
                    p2 = self._strip_linking_morpheme(part2)
                    if not p2:
                        continue

                # Check part3 (may have inflection)
                if self._is_word(part3):
                    p3 = part3
                else:
                    p3 = self._strip_inflection(part3)
                    if not p3:
                        continue

                results.append([p1, p2, p3])

        return results

    def _strip_linking_morpheme(self, word: str) -> Optional[str]:
        """Try to find valid word by removing linking morpheme."""
        for morph in LINKING_MORPHEMES:
            if word.endswith(morph) and len(word) > len(morph) + 2:
                base = word[: -len(morph)]
                if self._is_word(base):
                    return base
        return None

    def _strip_inflection(self, word: str) -> Optional[str]:
        """Try to find valid word by removing inflection ending."""
        for ending in ["en", "n", "et", "t", "er", "ar", "or", "a", "e"]:
            if word.endswith(ending) and len(word) > len(ending) + 2:
                base = word[: -len(ending)]
                if self._is_word(base):
                    return base
        return None

    def _score_split(self, parts: List[str]) -> float:
        """
        Score a split. Higher is better.

        Prefers:
        - Fewer parts (less fragmentation)
        - Longer minimum part (no junk)
        - All parts are known words
        """
        if not parts:
            return -1

        # All parts must be valid
        for p in parts:
            if not self._is_word(p):
                return -1

        # Prefer fewer parts
        part_penalty = len(parts) * 0.5

        # Prefer longer minimum part
        min_len = min(len(p) for p in parts)
        if min_len < 3:
            return -1

        # Score based on total coverage and part quality
        avg_len = sum(len(p) for p in parts) / len(parts)

        return avg_len - part_penalty

    def expand_text(self, text: str) -> str:
        """
        Expand all compound words in text.

        Useful for BM25 indexing - adds component words after compounds.

        Args:
            text: Text to process

        Returns:
            Text with compound words expanded

        Example:
            "Trafikskadelagen reglerar..." →
            "Trafikskadelagen trafik skade lag reglerar..."
        """
        if not text:
            return text

        words = re.findall(r"\b\w+\b", text)
        result_parts = []

        for word in words:
            parts = self.split(word)
            result_parts.extend(parts)

        return " ".join(result_parts)

    def expand_tokens(self, tokens: List[str]) -> List[str]:
        """
        Expand compound words in a token list.

        For use as custom tokenizer in retriv.

        Args:
            tokens: List of tokens

        Returns:
            Expanded token list with compound components added
        """
        expanded = []
        for token in tokens:
            parts = self.split(token)
            expanded.extend(parts)
        return expanded

    def is_available(self) -> bool:
        """Check if dictionary is available."""
        return self.dict_path.exists()

    def get_stats(self) -> dict:
        """Get splitter statistics."""
        self._ensure_loaded()
        return {
            "available": self.is_available(),
            "loaded": self._loaded,
            "dict_path": str(self.dict_path),
            "word_count": len(self._word_set) if self._word_set else 0,
            "min_word_length": self.min_word_length,
            "min_component_length": self.min_component_length,
        }


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON ACCESSOR
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache()
def get_compound_splitter() -> SwedishCompoundSplitter:
    """Get singleton compound splitter instance."""
    return SwedishCompoundSplitter()


# ═══════════════════════════════════════════════════════════════════════════
# TEST CODE
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    splitter = get_compound_splitter()

    test_words = [
        "trafikskadelagen",
        "arbetsgivaravgift",
        "olycksfallsförsäkring",
        "skadeståndsansvar",
        "försäkringsavtal",
        "anställningsavtal",
        "tryckfrihetsförordningen",
        "fotbollsplan",
        "lagstiftning",
        "rättsväsen",
        "grundlag",
        "regeringsform",
        "riksdagsledamot",
        "myndighetsutövning",
        "domstolsväsen",
        "brottsförebyggande",
        "skadeståndsanspråk",
        "hyresavtal",
        "köpeavtal",
    ]

    print("Swedish Compound Splitter Test")
    print("=" * 60)
    print(f"Dictionary: {splitter.get_stats()}")
    print()

    for word in test_words:
        parts = splitter.split(word)
        if len(parts) > 1:
            print(f"✓ {word} → {parts}")
        else:
            print(f"✗ {word} → (no split)")
