"""Clean and parse DeepSeek-R1 output.

DeepSeek-R1 wraps its reasoning chain in  think tags.
The final answer may appear after a  response tag or
after the last  think closing tag.
"""

import re


def clean_r1_output(raw: str) -> str:
    """Remove DeepSeek-R1 think/response tags and extract the final answer.

    Handles two formats:
      Format A:  think...think  responseanswer text
      Format B:  think...thinkanswer text
    """
    if not raw:
        return ""

    answer = raw

    # Strategy: find the last  think closing tag, take everything after it.
    # Then strip any  response wrapper.
    think_close = answer.rfind("</think>")
    if think_close != -1:
        answer = answer[think_close + len("</think>"):]

    # Strip <response> wrapper if present (possibly without closing tag)
    answer = re.sub(r"<response>", "", answer)

    return answer.strip()


def extract_reasoning(raw: str) -> str:
    """Extract the reasoning/thinking portion of R1 output."""
    if not raw:
        return ""

    # Try standard format: <think>...</think>
    match = re.search(r"<think>(.*?)</think>", raw, flags=re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try open <think> without closing </think>
    think_start = raw.find("<think>")
    if think_start != -1:
        think_end = raw.rfind("</think>")
        if think_end != -1:
            return raw[think_start + len("<think>"):think_end].strip()

        # No closing think tag — take everything after <think>
        return raw[think_start + len("<think>"):].strip()

    return ""


def strip_whitespace_artifacts(text: str) -> str:
    """Remove leading/trailing whitespace and normalize newlines."""
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def clean_r1_output_full(raw: str) -> dict:
    """Clean R1 output and return both reasoning and answer.

    Returns:
        dict with keys 'reasoning' and 'answer'.
    """
    return {
        "reasoning": extract_reasoning(raw),
        "answer": clean_r1_output(raw),
    }
