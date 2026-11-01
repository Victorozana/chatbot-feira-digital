"""Gerenciamento de estado de sessões conversacionais em memória com TTL."""

import copy
import time
from collections import OrderedDict
from threading import Lock
from typing import Any

from src.config import CONVERSA_TTL_SECONDS, MAX_CONVERSAS_ATIVAS
from src.domain.models import criar_estado_vazio


class ArmazenamentoConversas:
    """Armazena estados conversacionais por chat_id de forma thread-safe com expiração (TTL) e limite LRU."""

    def __init__(
        self,
        ttl_seconds: int = CONVERSA_TTL_SECONDS,
        maximo: int = MAX_CONVERSAS_ATIVAS,
        clock=time.monotonic,
    ):
        self._ttl_seconds = ttl_seconds
        self._maximo = maximo
        self._clock = clock
        self._conversas: OrderedDict[int, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = Lock()

    def _limpar_expiradas(self, agora: float) -> None:
        expirados = [
            chat_id
            for chat_id, (atualizada_em, _) in self._conversas.items()
            if agora - atualizada_em >= self._ttl_seconds
        ]
        for chat_id in expirados:
            del self._conversas[chat_id]

    def obter(self, chat_id: int) -> dict[str, Any]:
        """Recupera o estado salvo ou retorna um novo estado limpo."""
        with self._lock:
            self._limpar_expiradas(self._clock())
            registro = self._conversas.get(chat_id)
            if registro is None:
                return criar_estado_vazio()
            self._conversas.move_to_end(chat_id)
            return copy.deepcopy(registro[1])

    def salvar(self, chat_id: int, dados: dict[str, Any]) -> None:
        """Salva ou atualiza os dados da conversa do usuário."""
        with self._lock:
            self._limpar_expiradas(self._clock())
            self._conversas[chat_id] = (self._clock(), copy.deepcopy(dados))
            self._conversas.move_to_end(chat_id)
            while len(self._conversas) > self._maximo:
                self._conversas.popitem(last=False)

    def quantidade(self) -> int:
        """Retorna o total de conversas ativas no momento."""
        with self._lock:
            self._limpar_expiradas(self._clock())
            return len(self._conversas)
