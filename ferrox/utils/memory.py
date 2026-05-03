import tiktoken
from typing import List, Dict


def count_tokens(messages: List[Dict[str, str]], model: str = "gpt-4o") -> int:
    """Accurately count tokens in message history."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    num_tokens = 0
    for message in messages:
        # Every message follows <im_start>{role/name}\n{content}<im_end>\n
        num_tokens += 4
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
    num_tokens += 2  # every reply is primed with <im_start>assistant
    return num_tokens


def summarize_history(messages: List[Dict[str, str]], fallback_engine, model: str) -> str:
    """Summarize older messages to save context."""
    if len(messages) < 10:
        return ""

    # Take the oldest 50% of messages and summarize them
    to_summarize = messages[:-10]

    # In a real implementation, you'd send this to the LLM to summarize.
    # For this version, we'll create a simple string summary of topics.
    summary = "PREVIOUS CONTEXT SUMMARY:\n"
    for msg in to_summarize:
        if msg["role"] == "user":
            summary += f"- User asked about: {msg['content'][:50]}...\n"

    return summary
