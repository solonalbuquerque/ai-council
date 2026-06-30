"""Provider/model catalog and cost estimation.

NOTE: model names and prices change frequently. Values here are starting points —
confirm current ones and edit. The UI also lets you type a custom model.
"""

# Models offered per provider (editable; UI allows custom input).
PROVIDER_CATALOG = {
    "claude": {
        "label": "Claude",
        "models": ["claude-sonnet-4-6", "claude-opus-4-1", "claude-haiku-4-5"],
    },
    "gpt": {
        "label": "ChatGPT",
        "models": ["gpt-4o", "gpt-4o-mini", "o4-mini"],
    },
    "gemini": {
        "label": "Gemini",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    },
    "deepseek": {
        "label": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
}

# Estimated price in USD per 1 million tokens: (input, output).
# EDIT with current values from each provider.
PRICING = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "o4-mini": (1.1, 4.4),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.3, 2.5),
    "gemini-2.0-flash": (0.1, 0.4),
    "deepseek-chat": (0.27, 1.1),
    "deepseek-reasoner": (0.55, 2.19),
}
_DEFAULT = (1.0, 3.0)


def estimate(model: str, in_tokens: int, out_tokens: int) -> float:
    p_in, p_out = PRICING.get(model, _DEFAULT)
    return (in_tokens / 1_000_000) * p_in + (out_tokens / 1_000_000) * p_out
