"""Ponto de entrada para execução do Chatbot Feira Digital."""

from src.bot import criar_bot
from src.config import MODEL_NAME, get_required_env, load_project_env
from src.services.gemini_service import GeminiService
from src.services.rate_limiter import LimitadorGemini
from src.services.state_manager import ArmazenamentoConversas


def main() -> None:
    # Carrega variáveis locais do .env
    load_project_env()

    telegram_token = get_required_env("TELEGRAM_TOKEN")
    gemini_api_key = get_required_env("GEMINI_API_KEY")

    # Inicializa serviços do sistema
    conversas = ArmazenamentoConversas()
    limitador = LimitadorGemini()
    gemini_service = GeminiService(api_key=gemini_api_key, rate_limiter=limitador)

    # Cria e inicia o bot
    bot = criar_bot(
        telegram_token=telegram_token,
        gemini_service=gemini_service,
        conversas=conversas,
        limitador=limitador,
    )

    print("=" * 60)
    print("  Chatbot Feira Digital - Assistente Comercial com Gemini")
    print(f"  Modelo Gemini: {MODEL_NAME}")
    print("  Status: Polling ativo no Telegram...")
    print("=" * 60, flush=True)

    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=30,
        skip_pending=True,
    )


if __name__ == "__main__":
    main()
