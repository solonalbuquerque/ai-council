"""Definições dos CLIs suportados (Claude, Codex, Gemini, DeepSeek)."""

CLI_SPECS = {
    "claude": {
        "label": "Claude",
        "commands": ["claude"],
        "install": "npm install -g @anthropic-ai/claude-code",
        "install_alt": "claude install stable",
        "auth_help": "No terminal: claude auth login  (ou claude setup-token com assinatura)",
        "version_args": ["--version"],
        "ping_prompt": "OI",
    },
    "gpt": {
        "label": "ChatGPT (Codex)",
        "commands": ["codex"],
        "install": "npm install -g @openai/codex",
        "auth_help": "No terminal: codex login",
        "version_args": ["--version"],
        "ping_prompt": "OI",
    },
    "gemini": {
        "label": "Gemini",
        "commands": ["gemini"],
        "install": "npm install -g @google/gemini-cli",
        "auth_help": "No terminal: gemini  (login com conta Google) ou defina GEMINI_API_KEY",
        "version_args": ["--version"],
        "ping_prompt": "OI",
    },
    "deepseek": {
        "label": "DeepSeek",
        "commands": ["deepseek", "deepseek-tui"],
        "install": "npm install -g deepseek-tui",
        "auth_help": "No terminal: deepseek  (configure DEEPSEEK_API_KEY ou login interativo)",
        "version_args": ["--version"],
        "ping_prompt": "OI",
    },
}

PKEY_ORDER = ["claude", "gpt", "gemini", "deepseek"]
