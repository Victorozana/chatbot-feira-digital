"""Testes unitários dos fluxos comerciais, validação de regras e formatação de mensagens."""

import unittest

from src.domain.messages import montar_mensagem_comercial
from src.domain.models import criar_estado_vazio, processar_resultado_comercial
from src.services.rate_limiter import LimitadorGemini
from src.services.state_manager import ArmazenamentoConversas


def dados_venda(itens, localizacao="Arapiraca", preco_sem_produto=False):
    return {
        "operacao": "venda",
        "papel": "agricultor",
        "itens": itens,
        "localizacao": localizacao,
        "preco_sem_produto": preco_sem_produto,
    }


class ConversaComercialTest(unittest.TestCase):
    def test_separa_dois_produtos_com_precos(self):
        resposta = {
            "status": "coletando",
            "transcricao": "Vendo tomate e alface.",
            "dados": dados_venda([
                {"produto": "tomate", "quantidade": 10, "unidade": "caixas", "preco": 50, "tipo_preco": "por_unidade"},
                {"produto": "alface", "quantidade": 5, "unidade": "caixas", "preco": 30, "tipo_preco": "por_unidade"},
            ]),
        }
        resultado = processar_resultado_comercial(criar_estado_vazio(), resposta)
        self.assertEqual(resultado["status"], "pronto")
        self.assertEqual(resultado["dados"]["papel"], "agricultor")
        self.assertEqual(resultado["dados"]["itens"][0]["quantidade"], 10.0)
        self.assertEqual(resultado["dados"]["itens"][0]["unidade"], "caixas")
        self.assertEqual(resultado["dados"]["itens"][0]["preco"], 50.0)
        self.assertEqual(resultado["dados"]["itens"][1]["produto"], "alface")
        self.assertEqual(resultado["dados"]["itens"][1]["quantidade"], 5.0)
        self.assertEqual(resultado["dados"]["itens"][1]["unidade"], "caixas")
        self.assertEqual(resultado["dados"]["itens"][1]["preco"], 30.0)

    def test_venda_sem_preco_pergunta_pelo_preco(self):
        resposta = {
            "status": "coletando",
            "transcricao": "Vendo tomate.",
            "dados": dados_venda([
                {"produto": "tomate", "quantidade": 10, "unidade": "caixas", "preco": None, "tipo_preco": None}
            ]),
        }
        resultado = processar_resultado_comercial(criar_estado_vazio(), resposta)
        self.assertEqual(resultado["campos_pendentes"], ["preco"])
        self.assertEqual(
            montar_mensagem_comercial(resultado),
            "Vamos completar sua negociacao.\n\nQual e o preco de tomate, ou voce aceita negociar?",
        )

    def test_compra_incompleta_pergunta_apenas_pelo_dado_faltante(self):
        resposta = {
            "status": "coletando",
            "transcricao": "Quero comprar mandioca.",
            "dados": {
                "operacao": "compra",
                "papel": "cliente",
                "itens": [{"produto": "mandioca", "quantidade": 20, "unidade": "quilos", "preco": None, "tipo_preco": None}],
                "localizacao": None,
                "preco_sem_produto": False,
            },
        }
        resultado = processar_resultado_comercial(criar_estado_vazio(), resposta)
        self.assertEqual(resultado["campos_pendentes"], ["localizacao"])
        self.assertEqual(
            montar_mensagem_comercial(resultado),
            "Vamos completar sua negociacao.\n\nEm qual municipio ou comunidade fica a negociacao?",
        )

    def test_compra_sem_preco_fica_pronta(self):
        resposta = {
            "status": "coletando",
            "transcricao": "Quero comprar mandioca.",
            "dados": {
                "operacao": "compra",
                "papel": "cliente",
                "itens": [{"produto": "mandioca", "quantidade": 20, "unidade": "quilos", "preco": None, "tipo_preco": None}],
                "localizacao": "Arapiraca",
                "preco_sem_produto": False,
            },
        }
        resultado = processar_resultado_comercial(criar_estado_vazio(), resposta)
        self.assertEqual(resultado["status"], "pronto")
        self.assertEqual(resultado["dados"]["papel"], "cliente")
        self.assertIn("Pedido de cliente pronto", montar_mensagem_comercial(resultado))

    def test_preco_ambiguo_gera_pergunta_esclarecedora(self):
        resposta = {
            "status": "coletando",
            "transcricao": "Vendo cenoura e batata por 40 reais.",
            "dados": dados_venda(
                [
                    {"produto": "cenoura", "quantidade": 5, "unidade": "sacos", "preco": None, "tipo_preco": None},
                    {"produto": "batata", "quantidade": 5, "unidade": "sacos", "preco": None, "tipo_preco": None},
                ],
                preco_sem_produto=True,
            ),
        }
        resultado = processar_resultado_comercial(criar_estado_vazio(), resposta)
        self.assertIn("preco_ambiguo", resultado["campos_pendentes"])
        self.assertIn("Voce informou um preco para mais de um produto", montar_mensagem_comercial(resultado))

    def test_armazenamento_conversas_ttl_e_isolamento(self):
        armazenamento = ArmazenamentoConversas(ttl_seconds=10)
        estado_inicial = {"operacao": "venda", "papel": "agricultor", "itens": [], "localizacao": "Maceió", "preco_sem_produto": False}
        armazenamento.salvar(chat_id=101, dados=estado_inicial)

        recuperado = armazenamento.obter(101)
        self.assertEqual(recuperado["localizacao"], "Maceió")

        # Chat inexistente retorna estado vazio
        desconhecido = armazenamento.obter(999)
        self.assertIsNone(desconhecido["operacao"])

    def test_limitador_de_taxa(self):
        limitador = LimitadorGemini(intervalo_global=1, maximo_por_minuto=5, intervalo_por_usuario=2)
        permitido1, _ = limitador.tentar_reservar(chat_id=1)
        self.assertTrue(permitido1)

        # Mesma requisição imediata do mesmo usuário deve ser contida
        permitido2, espera = limitador.tentar_reservar(chat_id=1)
        self.assertFalse(permitido2)
        self.assertGreaterEqual(espera, 1)


if __name__ == "__main__":
    unittest.main()
