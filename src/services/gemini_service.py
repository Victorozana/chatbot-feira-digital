"""Integração com a API Gemini usando o SDK oficial google-genai."""

import base64
import json
import time
from typing import Any

from google import genai

from src.config import (
    BLOQUEIO_POR_COTA_SECONDS,
    MAX_ITENS_POR_CONVERSA,
    MODEL_NAME,
    REQUEST_TIMEOUT_SECONDS,
    RETRYABLE_STATUS_CODES,
)
from src.domain.models import carregar_resultado_json
from src.services.rate_limiter import LimitadorGemini, ServicoOcupadoError


GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["coletando", "pronto", "fora_de_escopo"]},
        "transcricao": {"type": "string"},
        "dados": {
            "type": "object",
            "properties": {
                "operacao": {"type": ["string", "null"], "enum": ["venda", "compra", None]},
                "papel": {"type": ["string", "null"], "enum": ["agricultor", "cliente", None]},
                "itens": {
                    "type": "array",
                    "maxItems": MAX_ITENS_POR_CONVERSA,
                    "items": {
                        "type": "object",
                        "properties": {
                            "produto": {"type": ["string", "null"]},
                            "quantidade": {"type": ["number", "null"]},
                            "unidade": {"type": ["string", "null"]},
                            "preco": {"type": ["number", "null"]},
                            "tipo_preco": {
                                "type": ["string", "null"],
                                "enum": ["por_unidade", "por_lote", "negociavel", None],
                            },
                        },
                        "required": ["produto", "quantidade", "unidade", "preco", "tipo_preco"],
                    },
                },
                "localizacao": {"type": ["string", "null"]},
                "preco_sem_produto": {"type": "boolean"},
            },
            "required": ["operacao", "papel", "itens", "localizacao", "preco_sem_produto"],
        },
    },
    "required": ["status", "transcricao", "dados"],
}

SYSTEM_INSTRUCTION = """
Voce e o assistente comercial da Feira Digital, voltado a agricultura familiar.
Conduza somente conversas de compra e venda de produtos rurais, hortifruti, graos,
animais, insumos e ferramentas rurais.

Existem somente dois papeis: agricultor para venda e cliente para compra.
Extraia cada produto como um item separado. Nunca associe o preco de um produto a
outro produto. Registre preco como numero sem "R$" e tipo_preco como por_unidade,
por_lote ou negociavel. Se o preco ou a qual produto ele pertence nao estiver claro,
use null, marque preco_sem_produto=true e nao invente valores. Caso contrario, marque
preco_sem_produto=false.

O contexto recebido contem dados de uma conversa anterior. Devolva os dados completos
ja conhecidos, preservando-os. Quando a pessoa corrigir algo, o dado novo substitui o
anterior. Se o audio estiver fora do escopo, use status "fora_de_escopo" e nao crie
dados comerciais.
""".strip()


class GeminiService:
    """Encapsula as interações multimodais de áudio com a API Gemini."""

    def __init__(self, api_key: str, rate_limiter: LimitadorGemini | None = None):
        self._client = genai.Client(api_key=api_key)
        self._rate_limiter = rate_limiter

    @staticmethod
    def _eh_limite_de_cota(exc: Exception) -> bool:
        descricao = str(exc).upper()
        return "429" in descricao or "RESOURCE_EXHAUSTED" in descricao

    @staticmethod
    def _eh_erro_transitorio(exc: Exception) -> bool:
        return any(codigo in str(exc) for codigo in RETRYABLE_STATUS_CODES)

    def analisar_audio(self, audio_bytes: bytes, estado: dict[str, Any]) -> dict[str, Any]:
        """Envia o áudio e o estado contextual para extração via Gemini."""
        prompt = (
            "Transcreva o audio e atualize os dados comerciais abaixo. Retorne somente o JSON do schema.\n\n"
            f"Contexto atual: {json.dumps(estado, ensure_ascii=False)}"
        )
        tempo_de_espera = 5
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        for tentativa in range(3):
            try:
                interaction = self._client.interactions.create(
                    model=MODEL_NAME,
                    system_instruction=SYSTEM_INSTRUCTION,
                    input=[
                        {"type": "text", "text": prompt},
                        {"type": "audio", "data": audio_b64, "mime_type": "audio/ogg"},
                    ],
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": GEMINI_RESPONSE_SCHEMA,
                    },
                    generation_config={"temperature": 0.1},
                    store=False,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                return carregar_resultado_json(interaction.output_text)
            except Exception as exc:
                if self._eh_limite_de_cota(exc):
                    if self._rate_limiter:
                        self._rate_limiter.suspender_por(BLOQUEIO_POR_COTA_SECONDS)
                    raise ServicoOcupadoError("Limite de cota Gemini atingido.") from exc

                if self._eh_erro_transitorio(exc) and tentativa < 2:
                    print(f"Servidor Gemini ocupado. Tentativa {tentativa + 1} falhou. Nova tentativa em {tempo_de_espera}s.")
                    time.sleep(tempo_de_espera)
                    tempo_de_espera *= 2
                    continue
                raise
