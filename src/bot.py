"""Orquestrador do bot no Telegram e ciclo de vida de mensagens."""

import telebot

from src.config import MAX_AUDIO_BYTES, BLOQUEIO_POR_COTA_SECONDS
from src.domain.messages import (
    montar_mensagem_audio_muito_grande,
    montar_mensagem_boas_vindas,
    montar_mensagem_comercial,
    montar_mensagem_orientacao,
    montar_mensagem_servico_ocupado,
    montar_mensagem_status,
)
from src.domain.models import processar_resultado_comercial
from src.services.gemini_service import GeminiService
from src.services.rate_limiter import LimitadorGemini, ServicoOcupadoError
from src.services.state_manager import ArmazenamentoConversas


def criar_bot(
    telegram_token: str,
    gemini_service: GeminiService,
    conversas: ArmazenamentoConversas,
    limitador: LimitadorGemini,
) -> telebot.TeleBot:
    """Configura e retorna a instância do TeleBot com seus handlers registrados."""
    bot = telebot.TeleBot(telegram_token)

    @bot.message_handler(commands=["start", "help"])
    def handler_boas_vindas(message):
        bot.reply_to(message, montar_mensagem_boas_vindas())

    @bot.message_handler(content_types=["text"], func=lambda msg: not msg.text.startswith("/"))
    def handler_texto(message):
        bot.reply_to(message, montar_mensagem_orientacao())

    @bot.message_handler(content_types=["voice"])
    def handler_voz(message):
        print(f"[Telegram] Áudio recebido do usuário {message.chat.id}", flush=True)
        msg_status = bot.reply_to(message, montar_mensagem_status())

        try:
            # 1. Validação de tamanho máximo
            if message.voice.file_size and message.voice.file_size > MAX_AUDIO_BYTES:
                bot.edit_message_text(
                    montar_mensagem_audio_muito_grande(),
                    chat_id=message.chat.id,
                    message_id=msg_status.message_id,
                )
                return

            # 2. Verificação de vazão e cotas
            permitido, espera = limitador.tentar_reservar(message.chat.id)
            if not permitido:
                bot.edit_message_text(
                    montar_mensagem_servico_ocupado(espera),
                    chat_id=message.chat.id,
                    message_id=msg_status.message_id,
                )
                return

            # 3. Recuperação de estado e download do áudio
            estado_anterior = conversas.obter(message.chat.id)
            file_info = bot.get_file(message.voice.file_id)
            downloaded_bytes = bot.download_file(file_info.file_path)

            # 4. Extração via Gemini e processamento comercial
            resposta_gemini = gemini_service.analisar_audio(downloaded_bytes, estado_anterior)
            resultado = processar_resultado_comercial(estado_anterior, resposta_gemini)

            # 5. Persistência de contexto
            if resultado["status"] != "fora_de_escopo":
                conversas.salvar(message.chat.id, resultado["dados"])

            # 6. Envio de resposta formatada
            bot.edit_message_text(
                montar_mensagem_comercial(resultado),
                chat_id=message.chat.id,
                message_id=msg_status.message_id,
            )
            print(f"[Telegram] Negociação processada com sucesso para {message.chat.id}", flush=True)

        except ServicoOcupadoError:
            bot.edit_message_text(
                montar_mensagem_servico_ocupado(BLOQUEIO_POR_COTA_SECONDS),
                chat_id=message.chat.id,
                message_id=msg_status.message_id,
            )
        except Exception as exc:
            print(f"[ERRO] {type(exc).__name__}: {exc}", flush=True)
            bot.edit_message_text(
                "Ocorreu um erro ao processar seu áudio. Seus dados anteriores foram preservados com segurança.",
                chat_id=message.chat.id,
                message_id=msg_status.message_id,
            )

    return bot
