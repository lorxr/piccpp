import json
import os
import re
import requests

from pathlib import Path
from datetime import datetime
from functools import wraps
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    url_for,
    abort,
)


# ==================================================
# CONFIGURAÇÕES DO PROJETO
# ==================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "chave-secreta-do-projeto-pi")

DATABASE_URL = os.getenv("DATABASE_URL")

IP_PUBLICO_CASA = os.getenv("IP_PUBLICO_CASA", "").strip()
URL_API = os.getenv("URL_API", "").strip()

if URL_API and "{IP_PUBLICO_CASA}" in URL_API:
    URL_API = URL_API.replace("{IP_PUBLICO_CASA}", IP_PUBLICO_CASA)

if not URL_API and IP_PUBLICO_CASA:
    URL_API = f"http://{IP_PUBLICO_CASA}:9000/triagem"

BASE_DIR = Path(__file__).resolve().parent
PASTA_TEMP_ENV = os.getenv("PASTA_TEMP_TRIAGEM", "temp")
PASTA_TEMP_TRIAGEM = Path(PASTA_TEMP_ENV)

if not PASTA_TEMP_TRIAGEM.is_absolute():
    PASTA_TEMP_TRIAGEM = BASE_DIR / PASTA_TEMP_TRIAGEM


# Mantém uma sessão HTTP reaproveitável para a API/LLM.
# Não define timeout para não matar nem limitar a conexão.
SESSAO_API = requests.Session()
SESSAO_API.headers.update({"Connection": "keep-alive"})


# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================

def limpar_valor(valor):
    if valor is None or str(valor).strip() == "":
        return "Não informado"

    return str(valor).strip()


def cpf_somente_numeros(cpf):
    return "".join(filter(str.isdigit, cpf or ""))


def formatar_cpf(cpf_numerico):
    return f"{cpf_numerico[:3]}.{cpf_numerico[3:6]}.{cpf_numerico[6:9]}-{cpf_numerico[9:]}"


def montar_sinais_vitais_texto(temperatura, pressao, frequencia, glicemia):
    return (
        f"Temperatura: {limpar_valor(temperatura)} °C | "
        f"PA: {limpar_valor(pressao)} | "
        f"Frequência cardíaca: {limpar_valor(frequencia)} BPM | "
        f"Glicemia: {limpar_valor(glicemia)} mg/dL"
    )


def calcular_tempo_espera(data_triagem):
    if not data_triagem:
        return 0

    try:
        diferenca = datetime.now() - data_triagem
        return max(int(diferenca.total_seconds() // 60), 0)
    except Exception:
        return 0


def normalizar_texto(texto):
    texto = (texto or "").lower()

    substituicoes = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }

    for origem, destino in substituicoes.items():
        texto = texto.replace(origem, destino)

    return texto


def cor_por_classificacao(classificacao):
    texto = normalizar_texto(classificacao)

    if "emerg" in texto or "vermelh" in texto:
        return "#e53935"

    if "nao urgente" in texto or "azul" in texto:
        return "#1e88e5"

    if "pouco" in texto or "verde" in texto:
        return "#43a047"

    if "urg" in texto or "amarel" in texto:
        return "#fdd835"

    return "#43a047"


def converter_texto_para_classificacao(texto):
    """
    Converte a resposta da IA para uma classificação padronizada.
    Retorna None quando o texto não possui uma classificação válida.
    """

    texto_normalizado = normalizar_texto(texto)

    if not texto_normalizado:
        return None

    # Evita aceitar valores genéricos vindos do JSON, como "Não classificada".
    if "nao classificada" in texto_normalizado or "nao informado" in texto_normalizado:
        return None

    # Ordem importante: "não urgente" e "pouco urgente" vêm antes de "urgente".
    if "vermelh" in texto_normalizado or "emergencia" in texto_normalizado:
        return "Emergência"

    if "azul" in texto_normalizado or "nao urgente" in texto_normalizado:
        return "Não Urgente"

    if "verde" in texto_normalizado or "pouco urgente" in texto_normalizado:
        return "Pouco Urgente"

    if (
        "amarel" in texto_normalizado
        or "laranja" in texto_normalizado
        or "urgencia" in texto_normalizado
        or "urgente" in texto_normalizado
    ):
        return "Urgência"

    return None


def extrair_classificacao_ia(resultado_llm, texto_triagem):
    """
    Extrai a classificação da IA mesmo quando a API retorna a classificação
    apenas dentro do texto completo, por exemplo:
    **Classificação de Manchester:** [AMARELO]
    """

    if isinstance(resultado_llm, dict):
        for chave in [
            "classificacao",
            "classificacao_ia",
            "classificação",
            "risco",
            "prioridade",
            "cor",
            "manchester",
        ]:
            valor = resultado_llm.get(chave)

            if valor:
                classificacao = converter_texto_para_classificacao(valor)

                if classificacao:
                    return classificacao

    texto = texto_triagem or ""

    # Primeiro tenta encontrar a linha específica da classificação.
    for linha in str(texto).splitlines():
        linha_normalizada = normalizar_texto(linha)

        if (
            "classificacao" in linha_normalizada
            or "manchester" in linha_normalizada
            or "prioridade" in linha_normalizada
            or "risco" in linha_normalizada
        ):
            classificacao = converter_texto_para_classificacao(linha)

            if classificacao:
                return classificacao

    # Se não achou em linha específica, procura no texto inteiro da IA.
    classificacao = converter_texto_para_classificacao(texto)

    if classificacao:
        return classificacao

    return "Não classificada"


def limpar_nome_doenca(texto):
    """
    Deixa somente o nome da doença/hipótese clínica.
    Remove markdown, bullets, numeração e frases explicativas.
    """

    if not texto:
        return ""

    texto = str(texto).strip()

    texto = texto.replace("**", "")
    texto = texto.replace("*", "")
    texto = texto.lstrip("-").lstrip("•").strip()
    texto = re.sub(r"^\d+[\.\)]\s*", "", texto)
    texto = texto.strip(" .;:-")

    texto_minusculo = normalizar_texto(texto)

    bloqueios = [
        "com base",
        "considerando",
        "paciente",
        "sintomas",
        "sinais vitais",
        "historico",
        "pode indicar",
        "pode sugerir",
        "pode ser",
        "sugere",
        "sugerir",
        "as possiveis patologias",
        "possiveis patologias",
        "sao",
        "incluem",
        "indica",
        "indicando",
        "relatados",
        "relatadas",
        "possivel",
        "necessario",
        "necessaria",
        "avaliar",
        "avaliacao",
        "consulta",
        "exame",
        "tratamento",
        "conduta",
        "procedimento",
    ]

    for bloqueio in bloqueios:
        if bloqueio in texto_minusculo:
            return ""

    if len(texto.split()) > 6:
        return ""

    return texto


def extrair_diagnostico_ia(resultado_llm, texto_triagem):
    """
    Retorna APENAS nomes de doenças/hipóteses clínicas.

    Exemplo:
    diagnostico_ia = "Otite; Gastrite; Cárie Dentária"

    A resposta completa da IA deve ser salva em descricao_ia.
    """

    diagnosticos = []

    if isinstance(resultado_llm, dict):
        for chave in [
            "diagnostico_ia",
            "diagnostico",
            "diagnóstico",
            "doenca",
            "doença",
            "doencas",
            "doenças",
            "patologia",
            "patologias",
            "hipotese",
            "hipótese",
            "hipotese_diagnostica",
            "hipótese diagnóstica",
        ]:
            valor = resultado_llm.get(chave)

            if valor:
                if isinstance(valor, list):
                    for item in valor:
                        nome = limpar_nome_doenca(item)

                        if nome:
                            diagnosticos.append(nome)
                else:
                    partes = re.split(r";|,|\n| e ", str(valor))

                    for parte in partes:
                        nome = limpar_nome_doenca(parte)

                        if nome:
                            diagnosticos.append(nome)

    if diagnosticos:
        diagnosticos_unicos = list(dict.fromkeys(diagnosticos))
        return "; ".join(diagnosticos_unicos)[:255]

    texto = texto_triagem or ""
    linhas = texto.splitlines()

    marcadores_secao = [
        "Pré-Diagnóstico Clínico:",
        "Pre-Diagnóstico Clínico:",
        "Pré Diagnóstico Clínico:",
        "Pre Diagnostico Clinico:",
        "Pré-Diagnóstico:",
        "Pre-Diagnóstico:",
        "Diagnóstico provável:",
        "Diagnostico provável:",
        "Diagnóstico:",
        "Diagnostico:",
        "Possíveis patologias:",
        "Possiveis patologias:",
        "Patologias:",
        "Suspeita:",
    ]

    indice_secao = None

    for indice, linha in enumerate(linhas):
        linha_limpa = linha.replace("**", "").strip()
        linha_minuscula = normalizar_texto(linha_limpa)

        for marcador in marcadores_secao:
            marcador_minusculo = normalizar_texto(marcador)

            if marcador_minusculo in linha_minuscula:
                indice_secao = indice
                break

        if indice_secao is not None:
            break

    if indice_secao is None:
        return "Não informado pela IA"

    for linha in linhas[indice_secao + 1:]:
        linha_limpa = linha.replace("**", "").strip()

        if not linha_limpa:
            continue

        linha_minuscula = normalizar_texto(linha_limpa)

        proxima_secao = [
            "possiveis procedimentos",
            "procedimentos",
            "condutas",
            "conduta",
            "alerta medico",
            "justificativa",
            "classificacao",
            "manchester",
        ]

        if any(secao in linha_minuscula for secao in proxima_secao):
            break

        if linha_limpa.startswith("-") or linha_limpa.startswith("•"):
            nome = limpar_nome_doenca(linha_limpa)

            if nome:
                diagnosticos.append(nome)

    if diagnosticos:
        diagnosticos_unicos = list(dict.fromkeys(diagnosticos))
        return "; ".join(diagnosticos_unicos)[:255]

    return "Não informado pela IA"


# ==================================================
# BANCO DE DADOS OTIMIZADO COM POOL
# ==================================================

POOL_BANCO = None


def iniciar_pool_banco():
    global POOL_BANCO

    if POOL_BANCO is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL não configurada no arquivo .env")

        POOL_BANCO = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DATABASE_URL,
        )

        print("Pool de conexões com o banco iniciado com sucesso.")

    return POOL_BANCO


@contextmanager
def conexao_banco():
    pool = iniciar_pool_banco()
    conexao = None

    try:
        conexao = pool.getconn()
        yield conexao

    except Exception:
        if conexao:
            conexao.rollback()
        raise

    finally:
        if conexao:
            pool.putconn(conexao)


def executar_select(sql, valores=None, um_registro=False):
    with conexao_banco() as conexao:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, valores or ())

            if um_registro:
                return cursor.fetchone()

            return cursor.fetchall()


def executar_comando(sql, valores=None, retornar_id=False):
    with conexao_banco() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(sql, valores or ())

            if retornar_id:
                resultado = cursor.fetchone()[0]
            else:
                resultado = cursor.rowcount

            conexao.commit()

            return resultado


def testar_conexao_banco():
    sql = "SELECT NOW() AS horario_banco;"
    return executar_select(sql, um_registro=True)


def garantir_usuario_admin():
    sql_buscar = """
        SELECT id_usuario
        FROM public."Usuario"
        WHERE nome_usuario = %s
        LIMIT 1;
    """

    usuario = executar_select(sql_buscar, ("admin",), um_registro=True)

    if usuario:
        return usuario["id_usuario"]

    sql_criar = """
        INSERT INTO public."Usuario" (
            nome_usuario,
            senha_usuario
        )
        VALUES (%s, %s)
        RETURNING id_usuario;
    """

    return executar_comando(
        sql_criar,
        ("admin", "123"),
        retornar_id=True,
    )


def cpf_ja_existe_no_banco(cpf_numerico):
    sql = """
        SELECT id_paciente
        FROM public."Paciente"
        WHERE regexp_replace(cpf_paciente, '[^0-9]', '', 'g') = %s
        LIMIT 1;
    """

    paciente = executar_select(sql, (cpf_numerico,), um_registro=True)

    return paciente is not None


def salvar_paciente_banco(paciente):
    sql = """
        INSERT INTO public."Paciente" (
            nome_paciente,
            cpf_paciente,
            data_nasc_paciente,
            idade_paciente,
            genero_paciente,
            telefone_paciente,
            endereco_paciente,
            cidade_paciente
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id_paciente;
    """

    valores = (
        paciente["nome_completo"],
        paciente["cpf"],
        paciente["data_nascimento"],
        int(paciente["idade"]),
        paciente["genero"],
        paciente["telefone"],
        paciente["endereco"],
        paciente["cidade"],
    )

    return executar_comando(sql, valores, retornar_id=True)


def listar_pacientes_banco():
    sql = """
        SELECT
            id_paciente,
            nome_paciente,
            cpf_paciente,
            data_nasc_paciente,
            idade_paciente,
            genero_paciente,
            telefone_paciente,
            endereco_paciente,
            cidade_paciente
        FROM public."Paciente"
        ORDER BY nome_paciente ASC;
    """

    return executar_select(sql)


def buscar_paciente_por_id(id_paciente):
    sql = """
        SELECT
            id_paciente,
            nome_paciente,
            cpf_paciente,
            data_nasc_paciente,
            idade_paciente,
            genero_paciente,
            telefone_paciente,
            endereco_paciente,
            cidade_paciente
        FROM public."Paciente"
        WHERE id_paciente = %s
        LIMIT 1;
    """

    return executar_select(sql, (id_paciente,), um_registro=True)


def salvar_triagem_inicial_banco(
    id_paciente,
    id_usuario,
    sintomas,
    descricao_inicial,
):
    sql = """
        INSERT INTO public."Triagem" (
            id_paciente,
            id_usuario,
            sintomas_relatados,
            classificacao_ia,
            diagnostico_ia,
            descricao_ia,
            status_validacao
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id_triagem;
    """

    valores = (
        int(id_paciente),
        int(id_usuario),
        limpar_valor(sintomas),
        "Não classificada",
        "Não informado pela IA",
        limpar_valor(descricao_inicial),
        "Pendente",
    )

    return executar_comando(sql, valores, retornar_id=True)


def atualizar_triagem_com_ia(
    id_triagem,
    classificacao_ia,
    diagnostico_ia,
    descricao_ia,
):
    sql = """
        UPDATE public."Triagem"
        SET
            classificacao_ia = %s,
            diagnostico_ia = %s,
            descricao_ia = %s,
            status_validacao = %s
        WHERE id_triagem = %s;
    """

    valores = (
        limpar_valor(classificacao_ia)[:50],
        limpar_valor(diagnostico_ia)[:255],
        limpar_valor(descricao_ia),
        "Pendente",
        int(id_triagem),
    )

    linhas_afetadas = executar_comando(sql, valores)

    if linhas_afetadas == 0:
        raise RuntimeError(f"Nenhuma triagem foi atualizada. ID recebido: {id_triagem}")


def listar_triagens_medico():
    sql = """
        SELECT
            t.id_triagem,
            t.classificacao_ia,
            t.diagnostico_ia,
            t.descricao_ia,
            t.sintomas_relatados,
            t.data_triagem,
            p.nome_paciente
        FROM public."Triagem" t
        INNER JOIN public."Paciente" p
            ON p.id_paciente = t.id_paciente
        ORDER BY t.data_triagem ASC;
    """

    triagens = executar_select(sql)

    pacientes_espera = []

    for triagem in triagens:
        classificacao = triagem.get("classificacao_ia") or "Não classificada"

        pacientes_espera.append({
            "id": triagem.get("id_triagem"),
            "nome": triagem.get("nome_paciente"),
            "classificacao": classificacao,
            "diagnostico": triagem.get("diagnostico_ia"),
            "descricao": triagem.get("descricao_ia"),
            "cor": cor_por_classificacao(classificacao),
            "tempo": calcular_tempo_espera(triagem.get("data_triagem")),
            "sintoma": triagem.get("sintomas_relatados"),
        })

    return pacientes_espera


def listar_triagens_para_tela_inicial():
    sql = """
        SELECT
            t.id_triagem,
            t.classificacao_ia,
            t.diagnostico_ia,
            t.descricao_ia,
            t.sintomas_relatados,
            t.status_validacao,
            t.data_triagem,
            p.nome_paciente
        FROM public."Triagem" t
        INNER JOIN public."Paciente" p
            ON p.id_paciente = t.id_paciente
        ORDER BY t.data_triagem ASC;
    """

    triagens = executar_select(sql)

    painel = {
        "emergencia": [],
        "urgencia": [],
        "pouco_urgente": [],
        "nao_urgente": [],
    }

    for triagem in triagens:
        classificacao = triagem.get("classificacao_ia") or "Não classificada"
        texto = normalizar_texto(classificacao)

        paciente = {
            "id": triagem.get("id_triagem"),
            "nome": triagem.get("nome_paciente"),
            "classificacao": classificacao,
            "diagnostico": triagem.get("diagnostico_ia"),
            "descricao": triagem.get("descricao_ia"),
            "sintoma": triagem.get("sintomas_relatados"),
            "tempo": calcular_tempo_espera(triagem.get("data_triagem")),
            "status": triagem.get("status_validacao"),
        }

        if "emerg" in texto or "vermelh" in texto:
            painel["emergencia"].append(paciente)

        elif "nao urgente" in texto or "azul" in texto:
            painel["nao_urgente"].append(paciente)

        elif "pouco" in texto or "verde" in texto:
            painel["pouco_urgente"].append(paciente)

        elif "urg" in texto or "amarel" in texto:
            painel["urgencia"].append(paciente)

        else:
            painel["nao_urgente"].append(paciente)

    return painel


# ==================================================
# ARQUIVOS TEMPORÁRIOS DA TRIAGEM
# ==================================================

def salvar_txt_temporario_triagem(dados_paciente):
    PASTA_TEMP_TRIAGEM.mkdir(parents=True, exist_ok=True)

    nome_arquivo = f"triagem_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    caminho_arquivo = PASTA_TEMP_TRIAGEM / nome_arquivo

    with open(caminho_arquivo, "w", encoding="utf-8") as arquivo:
        json.dump(dados_paciente, arquivo, ensure_ascii=False, indent=4)

    return caminho_arquivo


def enviar_triagem_para_llm(dados_paciente):
    if not URL_API:
        return {
            "sucesso": False,
            "erro": "URL_API não configurada no arquivo .env",
        }

    print("URL_API utilizada:", URL_API)
    print("IP_PUBLICO_CASA:", IP_PUBLICO_CASA)

    resposta = SESSAO_API.post(
        URL_API,
        json=dados_paciente,
    )

    resposta.raise_for_status()
    return resposta.json()


def salvar_resposta_llm_temporaria(resultado_llm):
    PASTA_TEMP_TRIAGEM.mkdir(parents=True, exist_ok=True)

    nome_arquivo = f"resposta_llm_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    caminho_arquivo = PASTA_TEMP_TRIAGEM / nome_arquivo

    triagem = resultado_llm.get("triagem", "Resposta da LLM não encontrada.")

    conteudo = f"""RESPOSTA DA LLM - TRIAGEM HOSPITALAR

Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

============================================================
TRIAGEM RECEBIDA DO SERVIDOR
============================================================

{triagem}

============================================================
JSON COMPLETO DA RESPOSTA
============================================================

{json.dumps(resultado_llm, ensure_ascii=False, indent=4)}
"""

    with open(caminho_arquivo, "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)

    return caminho_arquivo


# ==================================================
# FUNÇÕES DE MASCARAMENTO
# ==================================================

def mascarar_email(email):
    if not email or "@" not in email:
        return ""

    usuario, dominio = email.split("@", 1)

    if len(usuario) <= 3:
        return usuario[0] + "***@" + dominio

    return usuario[:3] + "*" * (len(usuario) - 3) + "@" + dominio


def mascarar_telefone(tel):
    if not tel:
        return ""

    numeros = "".join(c for c in tel if c.isdigit())

    if len(numeros) < 5:
        return "****"

    return numeros[:2] + "*" * (len(numeros) - 5) + numeros[-3:]


# ==================================================
# VERIFICA SE O USUÁRIO ESTÁ LOGADO
# ==================================================

def login_obrigatorio(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        if "usuario_logado" not in session:
            return redirect(url_for("login"))

        return funcao(*args, **kwargs)

    return wrapper


# ==================================================
# VERIFICA PERMISSÃO
# ==================================================

def permissao_obrigatoria(tipo_permitido):
    def decorator(funcao):
        @wraps(funcao)
        def wrapper(*args, **kwargs):
            if "usuario_logado" not in session:
                return redirect(url_for("login"))

            if session.get("tipo_usuario") != tipo_permitido:
                abort(403)

            return funcao(*args, **kwargs)

        return wrapper

    return decorator


# ==================================================
# LOGIN
# ==================================================

@app.route("/")
def raiz():
    if "usuario_logado" in session:
        return redirect(url_for("inicio"))

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuarioLogin", "").strip()
        senha = request.form.get("senhaLogin", "").strip()

        if usuario == "admin" and senha == "123":
            try:
                iniciar_pool_banco()
                id_usuario = garantir_usuario_admin()

            except Exception as erro:
                print("Erro ao iniciar banco no login:", erro)

                return render_template(
                    "seguranca/login.html",
                    erro="Não foi possível conectar ao banco de dados.",
                )

            session["usuario_logado"] = "admin"
            session["tipo_usuario"] = "enfermeiro"
            session["id_usuario"] = id_usuario

            return redirect(url_for("inicio"))

        return render_template(
            "seguranca/login.html",
            erro="Usuário ou senha inválidos",
        )

    return render_template("seguranca/login.html")


# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==================================================
# RECUPERAR SENHA
# ==================================================

@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        usuario_digitado = request.form.get("usuarioRecuperar")

        if usuario_digitado == "admin":
            email_original = "testandoteste@gmail.com"
            telefone_original = "55996988211"

            email_censurado = mascarar_email(email_original)
            sms_censurado = mascarar_telefone(telefone_original)

            return render_template(
                "seguranca/escolher_metodo.html",
                email=email_censurado,
                sms=sms_censurado,
            )

        return render_template(
            "seguranca/esqueci_senha.html",
            erro="Usuário não encontrado.",
        )

    return render_template("seguranca/esqueci_senha.html")


@app.route("/enviar-codigo", methods=["POST"])
def enviar_codigo():
    metodo_escolhido = request.form.get("metodo")
    print(f"Enviando código de verificação por: {metodo_escolhido}")

    return render_template("seguranca/redefinir_senha.html")


@app.route("/salvar-nova-senha", methods=["POST"])
def salvar_nova_senha():
    codigo = request.form.get("codigoVerificacao")
    nova_senha = request.form.get("novaSenha")
    confirmar_senha = request.form.get("confirmarSenha")

    if nova_senha != confirmar_senha:
        return render_template(
            "seguranca/redefinir_senha.html",
            erro="As senhas não coincidem. Tente novamente.",
        )

    if codigo != "123456":
        return render_template(
            "seguranca/redefinir_senha.html",
            erro="Código de verificação inválido.",
        )

    print("Senha alterada com sucesso no banco de dados!")

    return redirect(url_for("login"))


# ==================================================
# TELAS INTERNAS
# ==================================================

@app.route("/inicio")
@login_obrigatorio
def inicio():
    try:
        painel_triagem = listar_triagens_para_tela_inicial()

    except Exception as erro:
        print("Erro ao carregar triagens na tela inicial:", erro)

        painel_triagem = {
            "emergencia": [],
            "urgencia": [],
            "pouco_urgente": [],
            "nao_urgente": [],
        }

    return render_template(
        "index.html",
        painel_triagem=painel_triagem,
    )


# ==================================================
# PACIENTES
# ==================================================

@app.route("/pacientes")
@login_obrigatorio
def lista_pacientes():
    try:
        pacientes_banco = listar_pacientes_banco()

        pacientes_cadastrados = []

        for paciente in pacientes_banco:
            pacientes_cadastrados.append({
                "id": paciente["id_paciente"],
                "nome": paciente["nome_paciente"],
                "idade": paciente["idade_paciente"],
                "genero": paciente["genero_paciente"],
                "cpf": paciente["cpf_paciente"],
            })

    except Exception as erro:
        print("Erro ao carregar pacientes do banco:", erro)
        pacientes_cadastrados = []

    return render_template(
        "pacientes.html",
        pacientes=pacientes_cadastrados,
    )


@app.route("/cadastrar-paciente", methods=["GET", "POST"])
@login_obrigatorio
def cadastrar_paciente():
    if request.method == "POST":
        nome_completo = request.form.get("nome_completo", "").strip()
        cpf = request.form.get("cpf", "").strip()
        cpf_numerico = cpf_somente_numeros(cpf)
        data_nascimento = request.form.get("data_nascimento", "").strip()
        idade = request.form.get("idade", "").strip()
        genero = request.form.get("genero", "").strip()
        telefone = request.form.get("telefone", "").strip()
        endereco = request.form.get("endereco", "").strip()
        cidade = request.form.get("cidade", "").strip()

        if not nome_completo:
            return render_template(
                "cadastrar_paciente.html",
                erro="O nome completo do paciente é obrigatório.",
            )

        if not cpf_numerico:
            return render_template(
                "cadastrar_paciente.html",
                erro="O CPF do paciente é obrigatório.",
            )

        if len(cpf_numerico) != 11:
            return render_template(
                "cadastrar_paciente.html",
                erro="O CPF deve conter exatamente 11 dígitos.",
            )

        if not data_nascimento:
            return render_template(
                "cadastrar_paciente.html",
                erro="A data de nascimento é obrigatória.",
            )

        if not idade:
            return render_template(
                "cadastrar_paciente.html",
                erro="A idade é obrigatória.",
            )

        try:
            idade_int = int(idade)
        except ValueError:
            return render_template(
                "cadastrar_paciente.html",
                erro="A idade deve ser um número válido.",
            )

        if not genero:
            return render_template(
                "cadastrar_paciente.html",
                erro="O gênero é obrigatório.",
            )

        if not telefone:
            return render_template(
                "cadastrar_paciente.html",
                erro="O telefone é obrigatório.",
            )

        if not endereco:
            return render_template(
                "cadastrar_paciente.html",
                erro="O endereço é obrigatório.",
            )

        if not cidade:
            return render_template(
                "cadastrar_paciente.html",
                erro="A cidade é obrigatória.",
            )

        cpf_formatado = formatar_cpf(cpf_numerico)

        try:
            if cpf_ja_existe_no_banco(cpf_numerico):
                return render_template(
                    "cadastrar_paciente.html",
                    erro="Já existe um paciente cadastrado com este CPF.",
                )

            novo_paciente = {
                "nome_completo": nome_completo,
                "cpf": cpf_formatado,
                "data_nascimento": data_nascimento,
                "idade": idade_int,
                "genero": genero,
                "telefone": telefone,
                "endereco": endereco,
                "cidade": cidade,
            }

            id_paciente = salvar_paciente_banco(novo_paciente)

            return render_template(
                "cadastrar_paciente.html",
                sucesso=f"Paciente cadastrado com sucesso. ID: {id_paciente}",
            )

        except Exception as erro:
            print("Erro ao salvar paciente no banco:", erro)

            return render_template(
                "cadastrar_paciente.html",
                erro="Erro ao salvar paciente no banco de dados.",
            )

    return render_template("cadastrar_paciente.html")


# ==================================================
# TRIAGEM
# ==================================================

@app.route("/nova-triagem")
@login_obrigatorio
def nova_triagem():
    try:
        pacientes = listar_pacientes_banco()
        erro_pacientes = None

    except Exception as erro:
        print("Erro ao carregar pacientes para triagem:", erro)
        pacientes = []
        erro_pacientes = "Não foi possível carregar os pacientes do banco."

    return render_template(
        "nova_triagem.html",
        pacientes=pacientes,
        erro_pacientes=erro_pacientes,
    )


@app.route("/triagem", methods=["POST"])
@login_obrigatorio
def gerar_triagem():
    paciente_id = request.form.get("paciente_id", "")
    paciente_nome = request.form.get("paciente_nome", "Paciente não informado")
    idade = request.form.get("idade", "Não informado")
    genero = request.form.get("genero", "Não informado")

    if paciente_id and str(paciente_id).isdigit():
        try:
            paciente_banco = buscar_paciente_por_id(paciente_id)

            if paciente_banco:
                paciente_nome = paciente_banco["nome_paciente"]
                idade = paciente_banco["idade_paciente"]
                genero = paciente_banco["genero_paciente"]

        except Exception as erro:
            print("Erro ao buscar paciente selecionado:", erro)

    temperatura = request.form.get("temperatura", "Não informado")
    pressao = request.form.get("pressao", "Não informado")
    frequencia = request.form.get("frequencia", "Não informado")
    glicemia = request.form.get("glicemia", "Não informado")
    medicamentos = request.form.get("medicamentos", "Não informado")
    sintomas = request.form.get("sintomas", "Não informado")

    palavras_chave_json = request.form.get("palavras_chave", "[]")

    try:
        palavras_chave = json.loads(palavras_chave_json)
    except json.JSONDecodeError:
        palavras_chave = []

    palavras_chave_texto = ", ".join(palavras_chave) if palavras_chave else "Não informado"

    pre_analise = f"""
Com base nas informações informadas, o paciente apresenta dados que devem ser avaliados pela equipe responsável.

Dados do paciente:
- Nome: {paciente_nome}
- Idade: {idade}
- Gênero: {genero}

Sinais vitais registrados:
- Temperatura: {temperatura} °C
- Pressão arterial: {pressao}
- Frequência cardíaca: {frequencia} BPM
- Glicemia: {glicemia} mg/dL

Medicamentos de uso contínuo:
{medicamentos}

Palavras-chave informadas:
{palavras_chave_texto}

Relato de sintomas:
{sintomas}

Pré-análise:
O caso deve ser analisado considerando os sinais vitais, o relato do paciente, as palavras-chave informadas e possíveis fatores de risco.

Esta pré-análise serve apenas como apoio inicial e não substitui a avaliação profissional.
"""

    return render_template(
        "pre_analise.html",
        paciente_id=paciente_id,
        paciente_nome=paciente_nome,
        idade=idade,
        genero=genero,
        temperatura=temperatura,
        pressao=pressao,
        frequencia=frequencia,
        glicemia=glicemia,
        medicamentos=medicamentos,
        sintomas=sintomas,
        palavras_chave=palavras_chave,
        palavras_chave_json=json.dumps(palavras_chave, ensure_ascii=False),
        palavras_chave_texto=palavras_chave_texto,
        pre_analise=pre_analise,
    )


@app.route("/salvar-triagem", methods=["POST"])
@login_obrigatorio
def salvar_triagem():
    paciente_id = request.form.get("paciente_id", "").strip()
    paciente_nome = request.form.get("paciente_nome", "").strip()
    idade = request.form.get("idade", "").strip()
    genero = request.form.get("genero", "").strip()

    temperatura = request.form.get("temperatura", "").strip()
    pressao = request.form.get("pressao", "").strip()
    frequencia = request.form.get("frequencia", "").strip()
    glicemia = request.form.get("glicemia", "").strip()
    medicamentos = request.form.get("medicamentos", "").strip()
    sintomas = request.form.get("sintomas", "").strip()
    pre_analise = request.form.get("pre_analise", "").strip()

    palavras_chave_json = request.form.get("palavras_chave", "[]")

    try:
        palavras_chave = json.loads(palavras_chave_json)
    except json.JSONDecodeError:
        palavras_chave = []

    print("\n========== DEBUG SALVAR TRIAGEM ==========")
    print("paciente_id recebido:", paciente_id)
    print("paciente_nome recebido:", paciente_nome)
    print("idade recebida:", idade)
    print("genero recebido:", genero)
    print("sintomas recebidos:", sintomas)
    print("id_usuario sessão:", session.get("id_usuario"))
    print("URL_API:", URL_API)
    print("IP_PUBLICO_CASA:", IP_PUBLICO_CASA)
    print("==========================================\n")

    if not paciente_id or not paciente_id.isdigit():
        return """
        <h2>Erro ao salvar triagem</h2>
        <p>O paciente não foi vinculado corretamente.</p>
        <a href="/nova-triagem">Voltar</a>
        """, 400

    sinais_vitais_texto = montar_sinais_vitais_texto(
        temperatura=temperatura,
        pressao=pressao,
        frequencia=frequencia,
        glicemia=glicemia,
    )

    dados_paciente = {
        "idade": limpar_valor(idade),
        "genero": limpar_valor(genero),
        "sintomas": limpar_valor(sintomas),
        "sinais_vitais": sinais_vitais_texto,
        "medicamentos": limpar_valor(medicamentos),
    }

    caminho_triagem_temp = salvar_txt_temporario_triagem(dados_paciente)

    print("\n=== TRIAGEM SALVA LOCALMENTE ===")
    print("Paciente ID:", paciente_id)
    print("Paciente:", paciente_nome)
    print("Idade:", idade)
    print("Gênero:", genero)
    print("Temperatura:", temperatura)
    print("Pressão:", pressao)
    print("Frequência:", frequencia)
    print("Glicemia:", glicemia)
    print("Medicamentos:", medicamentos)
    print("Sintomas:", sintomas)
    print("Palavras-chave:", palavras_chave)
    print("Pré-análise revisada:", pre_analise)
    print("Arquivo temporário da triagem:", caminho_triagem_temp)

    id_triagem = None

    try:
        id_usuario = session.get("id_usuario")

        if not id_usuario:
            id_usuario = garantir_usuario_admin()
            session["id_usuario"] = id_usuario

        id_triagem = salvar_triagem_inicial_banco(
            id_paciente=paciente_id,
            id_usuario=id_usuario,
            sintomas=sintomas,
            descricao_inicial=pre_analise or "Triagem registrada aguardando resposta da IA.",
        )

        print("Triagem inicial salva no banco. ID:", id_triagem)

    except Exception as erro:
        print("Erro ao salvar triagem inicial no banco:", erro)

        return f"""
        <h2>Erro ao salvar triagem no banco</h2>
        <p>{erro}</p>
        <a href="/nova-triagem">Voltar</a>
        """, 500

    resultado_llm = {
        "sucesso": False,
        "erro": "A API/LLM não foi chamada.",
    }

    descricao_ia = pre_analise or "Triagem registrada aguardando resposta da IA."
    diagnostico_ia = "Não informado pela IA"
    classificacao_ia = "Não classificada"

    try:
        print("\nEnviando dados clínicos para a API/LLM sem timeout...")
        print("A conexão será mantida até a API responder.")

        resultado_llm = enviar_triagem_para_llm(dados_paciente)

        if resultado_llm.get("sucesso"):
            descricao_ia = resultado_llm.get(
                "triagem",
                "Resposta completa da IA não encontrada.",
            )

            classificacao_ia = extrair_classificacao_ia(
                resultado_llm,
                descricao_ia,
            )

            diagnostico_ia = extrair_diagnostico_ia(
                resultado_llm,
                descricao_ia,
            )

            print("Resposta completa da IA:")
            print(descricao_ia)

            print("Classificação extraída:")
            print(classificacao_ia)

            print("Diagnóstico extraído:")
            print(diagnostico_ia)

        else:
            erro_servidor = resultado_llm.get(
                "erro",
                "Erro não informado pelo servidor.",
            )

            descricao_ia = f"Erro retornado pelo servidor: {erro_servidor}"
            diagnostico_ia = "Não informado pela IA"
            classificacao_ia = "Erro API"

            print("Erro retornado pelo servidor:", erro_servidor)

        caminho_resposta_llm = salvar_resposta_llm_temporaria(resultado_llm)
        print("Resposta da LLM salva em:", caminho_resposta_llm)

    except requests.exceptions.ConnectionError as erro:
        descricao_ia = f"Falha de conexão com a API/LLM: {erro}"
        diagnostico_ia = "Não informado pela IA"
        classificacao_ia = "Erro conexão"

        print("Falha de conexão com a API/LLM:", erro)

    except requests.exceptions.HTTPError as erro:
        descricao_ia = f"Erro HTTP retornado pela API/LLM: {erro}"
        diagnostico_ia = "Não informado pela IA"
        classificacao_ia = "Erro HTTP"

        print("Erro HTTP retornado pela API/LLM:", erro)

    except json.JSONDecodeError as erro:
        descricao_ia = f"A API respondeu, mas não retornou um JSON válido: {erro}"
        diagnostico_ia = "Não informado pela IA"
        classificacao_ia = "JSON inválido"

        print("A API respondeu, mas não retornou um JSON válido:", erro)

    except Exception as erro:
        descricao_ia = f"Erro inesperado ao enviar para a API/LLM: {erro}"
        diagnostico_ia = "Não informado pela IA"
        classificacao_ia = "Erro inesperado"

        print("Erro inesperado ao enviar para a API/LLM:", erro)

    try:
        atualizar_triagem_com_ia(
            id_triagem=id_triagem,
            classificacao_ia=classificacao_ia,
            diagnostico_ia=diagnostico_ia,
            descricao_ia=descricao_ia,
        )

        print("Triagem atualizada no banco com resposta da IA. ID:", id_triagem)

    except Exception as erro:
        print("Erro ao atualizar triagem com resposta da IA:", erro)

    return redirect(url_for("inicio"))


# ==================================================
# TELA DO MÉDICO
# ==================================================

@app.route("/medico")
@login_obrigatorio
def fila_medico():
    try:
        pacientes_espera = listar_triagens_medico()

    except Exception as erro:
        print("Erro ao carregar fila médica do banco:", erro)
        pacientes_espera = []

    return render_template(
        "medico.html",
        pacientes=pacientes_espera,
    )


# ==================================================
# TESTE DE CONEXÃO COM BANCO
# ==================================================

@app.route("/teste-banco")
@login_obrigatorio
def teste_banco():
    try:
        resultado = testar_conexao_banco()

        return f"Banco conectado com sucesso. Horário do banco: {resultado['horario_banco']}"

    except Exception as erro:
        return f"Erro ao conectar no banco: {erro}", 500


# ==================================================
# INICIA O PROJETO
# ==================================================

if __name__ == "__main__":
    app.run(debug=False)