import json
import os
import requests

from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv


# ==================================================
# CONFIGURAÇÕES
# ==================================================

load_dotenv()

URL_API = os.getenv("URL_API")

BASE_DIR = Path(__file__).resolve().parent
PASTA_TEMP_ENV = os.getenv("PASTA_TEMP_TRIAGEM", "temp")

PASTA_TEMP = Path(PASTA_TEMP_ENV)

if not PASTA_TEMP.is_absolute():
    PASTA_TEMP = BASE_DIR / PASTA_TEMP


# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================

def buscar_ultimo_json_triagem():
    arquivos = list(PASTA_TEMP.glob("triagem_temp_*.txt"))

    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum arquivo triagem_temp_*.txt encontrado em: {PASTA_TEMP}"
        )

    return max(arquivos, key=lambda arquivo: arquivo.stat().st_mtime)


def carregar_dados_paciente_do_json():
    caminho_arquivo = buscar_ultimo_json_triagem()

    with open(caminho_arquivo, "r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    sinais_vitais = dados.get("sinais_vitais", "Não informado")

    if isinstance(sinais_vitais, dict):
        sinais_vitais = (
            f"Temperatura: {sinais_vitais.get('temperatura', 'Não informado')} °C | "
            f"PA: {sinais_vitais.get('pressao', 'Não informado')} | "
            f"Frequência cardíaca: {sinais_vitais.get('frequencia', 'Não informado')} BPM | "
            f"Glicemia: {sinais_vitais.get('glicemia', 'Não informado')} mg/dL"
        )

    dados_paciente = {
        "idade": dados.get("idade", "Não informado"),
        "genero": dados.get("genero", "Não informado"),
        "sintomas": dados.get("sintomas", "Não informado"),
        "sinais_vitais": sinais_vitais,
        "medicamentos": dados.get("medicamentos", "Não informado")
    }

    return dados_paciente, caminho_arquivo


def salvar_resposta_llm(resultado):
    PASTA_TEMP.mkdir(parents=True, exist_ok=True)

    nome_arquivo = f"resposta_llm_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    caminho_arquivo = PASTA_TEMP / nome_arquivo

    triagem = resultado.get("triagem", "Resposta da LLM não encontrada.")

    conteudo = f"""RESPOSTA DA LLM - TRIAGEM HOSPITALAR
Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

============================================================
TRIAGEM RECEBIDA DO SERVIDOR
============================================================

{triagem}

============================================================
JSON COMPLETO DA RESPOSTA
============================================================

{json.dumps(resultado, ensure_ascii=False, indent=4)}
"""

    with open(caminho_arquivo, "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)

    return caminho_arquivo


# ==================================================
# EXECUÇÃO PRINCIPAL
# ==================================================

print("🏥 SISTEMA DE TRIAGEM HOSPITALAR - ENTRADA DE DADOS")
print("-" * 50)

if not URL_API:
    print("❌ URL_API não configurada no arquivo .env")
    print("Exemplo no .env:")
    print("URL_API=http://SEU_IP_PUBLICO/triagem")
    exit()

try:
    print("📂 Buscando dados do paciente no JSON temporário...")

    dados_paciente, caminho_json_origem = carregar_dados_paciente_do_json()

    print("✅ JSON carregado de:")
    print(caminho_json_origem)

    print("\n📦 Dados clínicos preparados:")
    print(json.dumps(dados_paciente, ensure_ascii=False, indent=4))

    print("\n🚀 Enviando dados clínicos para o servidor central...")

    resposta = requests.post(
        URL_API,
        json=dados_paciente,
        timeout=60
    )

    resposta.raise_for_status()

    resultado = resposta.json()

    if resultado.get("sucesso"):
        print("\n" + "=" * 60)
        print("📥 TRIAGEM RECEBIDA DO SERVIDOR:")
        print("=" * 60)
        print(resultado.get("triagem"))
        print("=" * 60)

        caminho_resposta = salvar_resposta_llm(resultado)

        print("\n💾 Resposta da LLM salva temporariamente em:")
        print(caminho_resposta)

    else:
        print(f"❌ Erro processado no servidor: {resultado.get('erro')}")

        caminho_resposta = salvar_resposta_llm(resultado)

        print("\n💾 Resposta de erro salva temporariamente em:")
        print(caminho_resposta)

except FileNotFoundError as erro:
    print(f"❌ {erro}")

except requests.exceptions.ConnectionError:
    print("❌ Falha de conexão com o servidor.")
    print("Verifique se URL_API está correta no .env, se o NGINX está ativo e se a rota existe.")

except requests.exceptions.Timeout:
    print("❌ Timeout: o servidor demorou muito para responder.")

except requests.exceptions.HTTPError as erro:
    print(f"❌ Erro HTTP retornado pelo servidor: {erro}")

except json.JSONDecodeError:
    print("❌ O arquivo temporário não contém um JSON válido.")

except Exception as e:
    print(f"❌ Falha inesperada: {e}")