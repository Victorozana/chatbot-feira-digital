"""Modelos de dados, normalização e regras de validação comercial."""

import copy
import json
import math
from typing import Any

from src.config import MAX_ITENS_POR_CONVERSA


def criar_estado_vazio() -> dict[str, Any]:
    """Cria a estrutura base inicial de uma negociação comercial."""
    return {
        "operacao": None,
        "papel": None,
        "itens": [],
        "localizacao": None,
        "preco_sem_produto": False,
    }


def texto_ou_nulo(valor: Any, limite: int = 120) -> str | None:
    """Higieniza e normaliza campos de texto."""
    if not isinstance(valor, str):
        return None
    texto = " ".join(valor.split())
    return texto[:limite] if texto else None


def numero_positivo_ou_nulo(valor: Any) -> float | None:
    """Valida e converte números positivos finitos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    numero = float(valor)
    return numero if math.isfinite(numero) and numero > 0 else None


def normalizar_item(item: dict[str, Any]) -> dict[str, Any]:
    """Valida e normaliza um item individual negociado."""
    tipo_preco = item.get("tipo_preco")
    if tipo_preco not in {"por_unidade", "por_lote", "negociavel"}:
        tipo_preco = None
    preco = numero_positivo_ou_nulo(item.get("preco"))
    if tipo_preco == "negociavel":
        preco = None
    return {
        "produto": texto_ou_nulo(item.get("produto")),
        "quantidade": numero_positivo_ou_nulo(item.get("quantidade")),
        "unidade": texto_ou_nulo(item.get("unidade")),
        "preco": preco,
        "tipo_preco": tipo_preco,
    }


def normalizar_dados(dados: dict[str, Any]) -> dict[str, Any]:
    """Normaliza o estado global de uma negociação."""
    operacao = dados.get("operacao") if dados.get("operacao") in {"venda", "compra"} else None
    itens_brutos = dados.get("itens")
    itens = [
        normalizar_item(item)
        for item in itens_brutos[:MAX_ITENS_POR_CONVERSA]
    ] if isinstance(itens_brutos, list) else []
    
    return {
        "operacao": operacao,
        "papel": "agricultor" if operacao == "venda" else "cliente" if operacao else None,
        "itens": itens,
        "localizacao": texto_ou_nulo(dados.get("localizacao")),
        "preco_sem_produto": dados.get("preco_sem_produto") is True,
    }


def mesclar_item(anterior: dict[str, Any], novo: dict[str, Any]) -> dict[str, Any]:
    """Mescla um item existente com novas informações enviadas."""
    return {
        campo: novo[campo] if novo[campo] is not None else anterior[campo]
        for campo in anterior
    }


def mesclar_dados(anterior: dict[str, Any], novo: dict[str, Any]) -> dict[str, Any]:
    """Mescla o histórico acumulado da conversa com as novidades do turno atual."""
    anterior = normalizar_dados(anterior)
    novo = normalizar_dados(novo)
    
    # Se o usuário mudar a intenção básica (de venda para compra ou vice-versa), reinicia o estado
    if novo["operacao"] and novo["operacao"] != anterior["operacao"]:
        anterior = criar_estado_vazio()

    itens = copy.deepcopy(anterior["itens"])
    for item_novo in novo["itens"]:
        produto = item_novo["produto"]
        indice = next(
            (
                i for i, item_ant in enumerate(itens)
                if produto and item_ant["produto"] and item_ant["produto"].casefold() == produto.casefold()
            ),
            None,
        )
        if indice is None and produto is None and len(itens) == 1:
            indice = 0
            
        if indice is None:
            if len(itens) < MAX_ITENS_POR_CONVERSA:
                itens.append(item_novo)
        else:
            itens[indice] = mesclar_item(itens[indice], item_novo)

    operacao = novo["operacao"] or anterior["operacao"]
    return {
        "operacao": operacao,
        "papel": "agricultor" if operacao == "venda" else "cliente" if operacao else None,
        "itens": itens,
        "localizacao": novo["localizacao"] or anterior["localizacao"],
        "preco_sem_produto": novo["preco_sem_produto"],
    }


def campos_pendentes(dados: dict[str, Any]) -> list[str]:
    """Identifica quais informações comerciais ainda precisam ser coletadas."""
    if not dados["operacao"]:
        return ["operacao"]
    if dados["preco_sem_produto"]:
        return ["preco_ambiguo"]
        
    pendentes = [] if dados["itens"] else ["produto"]
    for item in dados["itens"]:
        if not item["produto"]:
            pendentes.append("produto")
        if item["quantidade"] is None:
            pendentes.append("quantidade")
        if not item["unidade"]:
            pendentes.append("unidade")
        if dados["operacao"] == "venda" and item["tipo_preco"] != "negociavel":
            if item["preco"] is None:
                pendentes.append("preco")
            if item["preco"] is not None and item["tipo_preco"] is None:
                pendentes.append("tipo_preco")
                
    if not dados["localizacao"]:
        pendentes.append("localizacao")
        
    return list(dict.fromkeys(pendentes))


def validar_resposta_gemini(resultado: Any) -> dict[str, Any]:
    """Valida o schema da resposta extraída pelo Gemini."""
    if not isinstance(resultado, dict):
        raise ValueError("O Gemini retornou uma resposta fora do schema esperado.")
    if resultado.get("status") not in {"coletando", "pronto", "fora_de_escopo"}:
        raise ValueError("O Gemini retornou um status inválido.")
    if not isinstance(resultado.get("transcricao"), str) or not isinstance(resultado.get("dados"), dict):
        raise ValueError("O Gemini retornou uma resposta fora do schema esperado.")
    return resultado


def carregar_resultado_json(output_text: str | None) -> dict[str, Any]:
    """Decodifica e valida o JSON gerado pelo Gemini."""
    try:
        resultado = json.loads(output_text or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("O Gemini retornou JSON inválido.") from exc
    return validar_resposta_gemini(resultado)


def processar_resultado_comercial(estado_anterior: dict[str, Any], resposta_gemini: dict[str, Any]) -> dict[str, Any]:
    """Processa o turno atual integrando o histórico e calculando pendências."""
    resposta_gemini = validar_resposta_gemini(resposta_gemini)
    if resposta_gemini["status"] == "fora_de_escopo":
        return {
            "status": "fora_de_escopo",
            "dados": criar_estado_vazio(),
            "campos_pendentes": [],
        }
        
    dados = mesclar_dados(estado_anterior, resposta_gemini["dados"])
    pendentes = campos_pendentes(dados)
    return {
        "status": "pronto" if not pendentes else "coletando",
        "dados": dados,
        "campos_pendentes": pendentes,
    }
