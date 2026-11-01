"""Templates e geradores de mensagens formatadas para o usuário."""

from typing import Any


def montar_mensagem_boas_vindas() -> str:
    """Mensagem inicial ao executar /start ou /help."""
    return (
        "Feira Digital\n\n"
        "Envie um audio de voz para comprar ou vender produtos da agricultura familiar.\n\n"
        "Exemplos:\n"
        '- "Vendo 10 caixas de tomate por 50 reais cada em Arapiraca."\n'
        '- "Quero comprar 20 quilos de mandioca em Arapiraca."'
    )


def montar_mensagem_orientacao() -> str:
    """Mensagem enviada quando o usuário manda texto em vez de áudio."""
    return (
        "Mensagem nao processada\n\n"
        "No momento eu recebo apenas audio de voz sobre compra ou venda na agricultura familiar."
    )


def montar_mensagem_status() -> str:
    """Mensagem transitória enquanto o áudio é processado."""
    return "Audio recebido\n\nEstou organizando sua negociacao..."


def montar_mensagem_erro(tipo_erro: str | None = None) -> str:
    """Mensagem de erro de compreensão ou fora de escopo."""
    if tipo_erro == "silencio":
        return "Nao foi possivel entender o audio\n\nNao detectei voz na gravacao. Tente enviar de novo."
    return (
        "Atendimento voltado a agricultura familiar\n\n"
        "Envie um audio para comprar ou vender produtos rurais, como hortifruti, graos, animais, insumos ou ferramentas."
    )


def montar_mensagem_audio_muito_grande() -> str:
    """Aviso quando o arquivo de voz ultrapassa o limite suportado."""
    return "Audio muito grande\n\nEnvie uma mensagem de voz de ate 10 MB para eu conseguir processa-la."


def montar_mensagem_servico_ocupado(espera_segundos: int) -> str:
    """Aviso de resiliência e rate limit."""
    return (
        "Servico com muitas solicitacoes\n\n"
        f"Aguarde cerca de {max(1, espera_segundos)} segundos e envie seu audio novamente."
    )


def proxima_pergunta(dados: dict[str, Any], pendentes: list[str]) -> str:
    """Gera a pergunta contextual do próximo campo pendente."""
    campo = pendentes[0]
    produto = next((item["produto"] for item in dados["itens"] if item["produto"]), "o produto")
    
    perguntas = {
        "operacao": "Voce quer comprar ou vender?",
        "produto": "Qual produto voce quer informar?",
        "quantidade": f"Qual e a quantidade de {produto}?",
        "unidade": f"Essa quantidade de {produto} e em quilos, caixas, sacas ou outra unidade?",
        "preco": f"Qual e o preco de {produto}, ou voce aceita negociar?",
        "preco_ambiguo": "Voce informou um preco para mais de um produto. Esse valor e de qual produto?",
        "tipo_preco": f"Esse preco de {produto} e por unidade ou pelo lote todo?",
        "localizacao": "Em qual municipio ou comunidade fica a negociacao?",
    }
    return perguntas.get(campo, "Poderia fornecer mais detalhes sobre a negociacao?")


def formatar_numero(numero: float) -> str:
    """Formata números decimais no padrão brasileiro."""
    return f"{numero:g}".replace(".", ",")


def formatar_item(item: dict[str, Any]) -> str:
    """Formata visualmente a linha de cada produto."""
    descricao = f"{formatar_numero(item['quantidade'])} {item['unidade']} de {item['produto']}"
    if item["tipo_preco"] == "negociavel":
        return f"- {descricao}: preco a combinar"
    if item["preco"] is None:
        return f"- {descricao}"
    sufixo = "por lote" if item["tipo_preco"] == "por_lote" else "por unidade"
    return f"- {descricao}: R$ {formatar_numero(item['preco'])} {sufixo}"


def montar_mensagem_comercial(resultado: dict[str, Any]) -> str:
    """Monta a resposta final do bot (pergunta de continuação ou ficha pronta)."""
    if resultado["status"] == "fora_de_escopo":
        return montar_mensagem_erro("fora_de_escopo")
        
    dados = resultado["dados"]
    if resultado["status"] == "coletando":
        return "Vamos completar sua negociacao.\n\n" + proxima_pergunta(dados, resultado["campos_pendentes"])
        
    titulo = "Oferta de agricultor pronta" if dados["operacao"] == "venda" else "Pedido de cliente pronto"
    itens_formatados = "\n".join(formatar_item(item) for item in dados["itens"])
    return f"{titulo}\n\n{itens_formatados}\n\nLocal: {dados['localizacao']}"
