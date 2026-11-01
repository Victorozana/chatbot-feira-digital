"""Controle de vazão (rate limiting) e resiliência para chamadas à API Gemini."""

import math
import time
from collections import deque
from threading import Lock

from src.config import (
    MAX_REQUESTS_PER_MINUTE,
    MIN_INTERVAL_GLOBAL_SECONDS,
    MIN_INTERVAL_POR_USUARIO_SECONDS,
)


class ServicoOcupadoError(Exception):
    """Exceção levantada quando a cota da API ou limite de taxa foi atingido."""
    pass


class LimitadorGemini:
    """Controla e protege as requisições contra estouro de cotas e sobrecarga."""

    def __init__(
        self,
        intervalo_global: int = MIN_INTERVAL_GLOBAL_SECONDS,
        maximo_por_minuto: int = MAX_REQUESTS_PER_MINUTE,
        intervalo_por_usuario: int = MIN_INTERVAL_POR_USUARIO_SECONDS,
        clock=time.monotonic,
    ):
        self._intervalo_global = intervalo_global
        self._maximo_por_minuto = maximo_por_minuto
        self._intervalo_por_usuario = intervalo_por_usuario
        self._clock = clock
        self._ultimas_requisicoes: deque[float] = deque()
        self._ultima_por_usuario: dict[int, float] = {}
        self._bloqueado_ate = 0.0
        self._lock = Lock()

    def tentar_reservar(self, chat_id: int) -> tuple[bool, int]:
        """Tenta agendar uma requisição para o chat_id informado.

        Retorna (True, 0) se liberado, ou (False, tempo_restante_em_segundos) se barrado.
        """
        agora = self._clock()
        with self._lock:
            while self._ultimas_requisicoes and agora - self._ultimas_requisicoes[0] >= 60:
                self._ultimas_requisicoes.popleft()

            self._ultima_por_usuario = {
                usuario: instante
                for usuario, instante in self._ultima_por_usuario.items()
                if agora - instante < self._intervalo_por_usuario
            }

            esperas = [self._bloqueado_ate - agora]
            if self._ultimas_requisicoes:
                esperas.append(self._intervalo_global - (agora - self._ultimas_requisicoes[-1]))
            if len(self._ultimas_requisicoes) >= self._maximo_por_minuto:
                esperas.append(60 - (agora - self._ultimas_requisicoes[0]))
            if chat_id in self._ultima_por_usuario:
                esperas.append(self._intervalo_por_usuario - (agora - self._ultima_por_usuario[chat_id]))

            espera = max(esperas)
            if espera > 0:
                return False, math.ceil(espera)

            self._ultimas_requisicoes.append(agora)
            self._ultima_por_usuario[chat_id] = agora
            return True, 0

    def suspender_por(self, segundos: int) -> None:
        """Aplica uma pausa forçada global (usado em erros HTTP 429 de cota esgotada)."""
        with self._lock:
            self._bloqueado_ate = max(self._bloqueado_ate, self._clock() + segundos)
