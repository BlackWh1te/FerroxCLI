"""Content safety utilities for social media automation.

Provides input sanitization (prompt injection defense) and output moderation
(content filtering before posting to social platforms).
"""

import re
from typing import List, Tuple

# Prompt injection detection patterns
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+(?:instructions|prompts|commands)",
    r"ignore\s+(?:the\s+)?(?:above|prior)\s+(?:instructions|prompts|commands)",
    r"system\s+(?:prompt|instruction|command)",
    r"you\s+are\s+now\s+(?:a\s+)?(?:new|different|other)",
    r"new\s+(?:role|persona|identity)",
    r"forget\s+(?:everything|all|your)\s+(?:instructions|training|constraints)",
    r"(?:from\s+now\s+on|going\s+forward)\s+you\s+(?:are|will|must)",
    r"disregard\s+(?:the|all|your)\s+(?:above|previous|system)",
    r"(?:bypass|override|disable)\s+(?:restrictions|constraints|limits|safety)",
    r"DAN\s+(?:mode|protocol)",
    r"(?:jailbreak|prompt\s+leak)",
]

# Spam and unsafe content patterns
SPAM_PATTERNS = [
    r"DM\s+me",
    r"click\s+here",
    r"click\s+the\s+link",
    r"free\s+(?:money|cash|crypto|bitcoin|NFT)",
    r"get\s+rich\s+quick",
    r"(?:100%|guaranteed)\s+(?:profit|return|win)",
    r"(?:limited\s+time|act\s+now|urgent)",
    r"(?:investment|opportunity)\s+of\s+a\s+lifetime",
    r"(?:make\s+money|earn\s+money)\s+fast",
    r"(?:double|triple)\s+your\s+(?:money|investment)",
]

# Moderation categories - words/phrases that should trigger review
MODERATION_CATEGORIES = {
    "violence": ["kill", "murder", "attack", "violent", "harm", "hurt", "die", "death threat"],
    "hate_speech": ["hate", "racist", "nazi", "supremacist", "genocide", "ethnic cleansing"],
    "self_harm": ["suicide", "self-harm", "cut myself", "end it all", "kill myself"],
    "explicit": ["porn", "nude", "sexual", "xxx", "onlyfans"],
    "scams": [" Ponzi", " pyramid scheme", " phishing", " scam", " fraud"],
    "medical_misinfo": ["cure cancer", "miracle cure", "vaccine causes", "doctors don't want"],
    "copyright": ["full text", "complete article", "entire chapter", "copyrighted"],
}

# Safe domains for links
SAFE_DOMAINS = [
    "github.com",
    "stackoverflow.com",
    "arxiv.org",
    "techcrunch.com",
    "wired.com",
    "theverge.com",
    "reddit.com",
    "medium.com",
    "dev.to",
    "news.ycombinator.com",
    "bloomberg.com",
    "reuters.com",
    "bbc.com",
    "cnn.com",
    "nytimes.com",
    "washingtonpost.com",
    "forbes.com",
    "scientificamerican.com",
    "nature.com",
    "ieee.org",
    "acm.org",
    "mit.edu",
    "stanford.edu",
    "harvard.edu",
    "berkeley.edu",
]


def sanitize_content(text: str) -> Tuple[str, List[str]]:
    """Sanitize content to remove prompt injection attempts and malicious content.
    
    Args:
        text: Raw text content (e.g., from fetched article)
        
    Returns:
        Tuple of (sanitized_text, list_of_warnings)
    """
    warnings = []

    # Check for prompt injection patterns
    text_lower = text.lower()

    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            warnings.append(f"PROMPT INJECTION DETECTED: Pattern '{pattern}' found. Content discarded.")
            return "[CONTENT BLOCKED: Prompt injection detected]", warnings

    # Remove common injection framing
    # Strip things that look like system instructions
    cleaned = text

    # Remove lines that start with common instruction patterns
    cleaned = re.sub(
        r"^(?:system|instruction|prompt|role|you are|forget|ignore|disregard).*?$",
        "",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # Remove very long repetitive sequences (bot behavior indicator)
    cleaned = re.sub(r"(.)\1{50,}", "\1\1\1", cleaned)

    # Check content length - extremely long inputs might be attacks
    if len(cleaned) > 50000:
        warnings.append("Content extremely long (>50k chars). Truncating to 10k.")
        cleaned = cleaned[:10000]

    # Remove zero-width characters and homoglyphs commonly used in attacks
    cleaned = cleaned.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    cleaned = cleaned.replace("\u2060", "").replace("\ufeff", "")

    return cleaned, warnings


def moderation_check(text: str) -> Tuple[bool, List[str]]:
    """Check text for content that violates platform safety policies.
    
    Args:
        text: Text to check (e.g., generated tweet)
        
    Returns:
        Tuple of (is_safe, list_of_violations)
    """
    violations = []
    text_lower = text.lower()

    # Check spam patterns
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            violations.append(f"SPAM: Pattern '{pattern}' detected")

    # Check moderation categories
    for category, keywords in MODERATION_CATEGORIES.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                violations.append(f"MODERATION ({category.upper()}): Keyword '{keyword}' detected")

    # Check all-caps words (aggression indicator)
    all_caps_words = re.findall(r"\b[A-Z]{5,}\b", text)
    if len(all_caps_words) > 2:
        violations.append("STYLE: Excessive all-caps words detected")

    # Check excessive emoji count
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    emoji_count = len(emoji_pattern.findall(text))
    if emoji_count > 5:
        violations.append(f"STYLE: Too many emojis ({emoji_count} > 5)")

    # Check hashtag count
    hashtag_count = len(re.findall(r"#\w+", text))
    if hashtag_count > 5:
        violations.append(f"HASHTAGS: Too many hashtags ({hashtag_count} > 5)")

    # Check for raw short links
    short_link_domains = ["bit.ly", "t.co", "goo.gl", "tinyurl", "ow.ly", "buff.ly"]
    for domain in short_link_domains:
        if domain in text_lower:
            violations.append(f"LINKS: Short link '{domain}' detected - use full URLs")

    is_safe = len(violations) == 0
    return is_safe, violations


def validate_tweet_length(text: str, max_length: int = 280) -> Tuple[bool, int, str]:
    """Validate tweet length. Twitter counts URLs as 23 chars regardless of actual length.
    
    Args:
        text: Tweet text to validate
        max_length: Maximum allowed length (default 280)
        
    Returns:
        Tuple of (is_valid, effective_length, message)
    """
    # Count URLs as 23 chars each (Twitter standard)
    effective_text = text
    url_pattern = re.compile(r"https?://\S+")

    urls = url_pattern.findall(text)
    for url in urls:
        effective_text = effective_text.replace(url, "x" * 23, 1)

    effective_length = len(effective_text)

    if effective_length > max_length:
        return False, effective_length, f"Tweet too long: {effective_length}/{max_length} chars"

    return True, effective_length, f"Tweet length OK: {effective_length}/{max_length} chars"


def is_safe_domain(url: str) -> bool:
    """Check if a URL domain is in the safe/reputable list.
    
    Args:
        url: URL to check
        
    Returns:
        True if domain is in safe list
    """
    url_lower = url.lower()

    for domain in SAFE_DOMAINS:
        if domain in url_lower:
            return True

    # Default to allowing if not in list - the skill will warn
    return True


def check_duplicate_content(new_text: str, previous_texts: List[str], threshold: float = 0.7) -> Tuple[bool, float, str]:
    """Check if new text is too similar to previous posts.
    
    Args:
        new_text: New content to check
        previous_texts: List of previously posted texts
        threshold: Similarity threshold (0.0-1.0) above which it's considered duplicate
        
    Returns:
        Tuple of (is_duplicate, similarity_score, closest_match)
    """
    if not previous_texts:
        return False, 0.0, ""

    # Simple similarity: longest common subsequence ratio
    def lcs_length(s1: str, s2: str) -> int:
        """Compute length of longest common subsequence."""
        m, n = len(s1), len(s2)
        # Use rolling array for memory efficiency
        prev = [0] * (n + 1)
        curr = [0] * (n + 1)

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, [0] * (n + 1)

        return prev[n]

    max_similarity = 0.0
    closest_match = ""

    new_lower = new_text.lower()

    for prev_text in previous_texts:
        prev_lower = prev_text.lower()

        # Calculate similarity based on LCS
        lcs = lcs_length(new_lower, prev_lower)
        max_len = max(len(new_lower), len(prev_lower))

        if max_len == 0:
            similarity = 0.0
        else:
            similarity = lcs / max_len

        if similarity > max_similarity:
            max_similarity = similarity
            closest_match = prev_text[:100] + "..." if len(prev_text) > 100 else prev_text

    is_duplicate = max_similarity > threshold

    return is_duplicate, max_similarity, closest_match
