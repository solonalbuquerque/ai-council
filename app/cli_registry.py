"""Definições dos CLIs suportados (Claude, Codex, Gemini, DeepSeek)."""

CLI_SPECS = {
    "claude": {
        "label": "Claude",
        "commands": ["claude"],
        "install": "npm install -g @anthropic-ai/claude-code",
        "install_alt": "claude install stable",
        "auth_help": "Clique em Fazer login (abre terminal com claude setup-token), cole o token gerado abaixo e Salvar.",
        "login_args": ["setup-token"],
        "token_env": "CLAUDE_CODE_OAUTH_TOKEN",
        "token_hint": "Cole aqui o token sk-ant-oat01-... gerado pelo claude setup-token",
        "version_args": ["--version"],
        "ping_prompt": "OI",
    },
    "gpt": {
        "label": "ChatGPT (Codex)",
        "commands": ["codex"],
        "install": "npm install -g @openai/codex",
        "auth_help": "Clique em Fazer login (abre terminal com codex login) ou rode no CMD.",
        "login_args": ["login"],
        "version_args": ["--version"],
        "ping_prompt": "OI",
    },
    "gemini": {
        "label": "Gemini",
        "commands": ["gemini"],
        "install": "npm install -g @google/gemini-cli",
        "auth_help": "Clique em Fazer login (abre gemini interativo) ou defina GEMINI_API_KEY.",
        "login_args": [],
        "version_args": ["--version"],
        "ping_prompt": "OI",
    },
    "deepseek": {
        "label": "DeepSeek",
        "commands": ["deepseek", "deepseek-tui"],
        "install": "npm install -g deepseek-tui",
        "auth_help": "Clique em Fazer login (abre deepseek interativo) ou defina DEEPSEEK_API_KEY.",
        "login_args": [],
        "version_args": ["--version"],
        "ping_prompt": "OI",
    },
}

PKEY_ORDER = ["claude", "gpt", "gemini", "deepseek"]
