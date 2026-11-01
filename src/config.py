"""Configurações e constantes do sistema."""

import os
from pathlib import Path


ENV_NAMES = frozenset({"TELEGRAM_TOKEN", "GEMINI_API_KEY"})

# Configurações de modelo e cotas
MODEL_NAME = "gemini-3.1-flash-lite"
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CONVERSAS_ATIVAS = 200
CONVERSA_TTL_SECONDS = 30 * 60  # 30 minutos
MAX_ITENS_POR_CONVERSA = 10

# Controle de taxa e resiliência
MIN_INTERVAL_GLOBAL_SECONDS = 12
MAX_REQUESTS_PER_MINUTE = 5
MIN_INTERVAL_POR_USUARIO_SECONDS = 20
BLOQUEIO_POR_COTA_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 45
RETRYABLE_STATUS_CODES = ("500", "502", "503", "504")


def load_project_env(env_path: Path | None = None) -> None:
    """Lê o arquivo .env do projeto sem sobrescrever variáveis já definidas no ambiente."""
    path = env_path or Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name not in ENV_NAMES or os.getenv(name):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[name] = value


def get_required_env(name: str) -> str:
    """Retorna uma variável de ambiente obrigatória ou lança RuntimeError."""
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
