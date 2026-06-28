"""Definições dos CLIs suportados (Claude, Codex, Gemini, Antigravity, DeepSeek)."""

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
        "auth_help": "OAuth individual/free tier do Gemini CLI foi descontinuado. Use conta enterprise/API key compatível ou o card Antigravity CLI.",
        "login_args": [],
        "version_args": ["--version"],
        "ping_prompt": "OI",
    },
    "antigravity": {
        "label": "Antigravity CLI",
        "commands": ["agy"],
        "install": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
        "install_windows": "powershell -NoProfile -ExecutionPolicy Bypass -Command \"irm https://antigravity.google/cli/install.ps1 | iex\"",
        "auth_help": "Faça login (abre agy), copie a key gerada e cole no campo abaixo e Salvar. O login interativo não vale para o modo -p.",
        "login_args": [],
        "token_env": ["ANTIGRAVITY_API_KEY", "GEMINI_API_KEY"],
        "token_hint": "Cole aqui a key gerada pelo agy após o login",
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

PKEY_ORDER = ["claude", "gpt", "gemini", "antigravity", "deepseek"]
