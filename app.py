import json
import os
import requests

from pathlib import Path
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, session, url_for, abort


# ==================================================
# CONFIGURAÇÕES DO PROJETO
# ==================================================

load_dotenv()

app = Flask(__name__)

# Chave usada pelo Flask para controlar a sessão do usuário.
# Pega do .env. Se não existir, usa a chave padrão.
app.secret_key = os.getenv("SECRET_KEY", "chave-secreta-do-projeto-pi")

# URL da API/LLM vinda do .env
URL_API = os.getenv("URL_API")

# Pasta temporária vinda do .env
# Exemplo no .env:
# PASTA_TEMP_TRIAGEM=temp
BASE_DIR = Path(__file__).resolve().parent
PASTA_TEMP_ENV = os.getenv("PASTA_TEMP_TRIAGEM", "temp")

PASTA_TEMP_TRIAGEM = Path(PASTA_TEMP_ENV)

if not PASTA_TEMP_TRIAGEM.is_absolute():
    PASTA_TEMP_TRIAGEM = BASE_DIR / PASTA_TEMP_TRIAGEM


# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================

def limpar_valor(valor):
    if valor is None or str(valor).strip() == "":
        return "Não informado"

    return str(valor).strip()


def montar_sinais_vitais_texto(temperatura, pressao, frequencia, glicemia):
    return (
        f"Temperatura: {limpar_valor(temperatura)} °C | "
        f"PA: {limpar_valor(pressao)} | "
        f"Frequência cardíaca: {limpar_valor(frequencia)} BPM | "
        f"Glicemia: {limpar_valor(glicemia)} mg/dL"
    )


def salvar_txt_temporario_triagem(dados_paciente):
    """
    Salva o JSON enviado para a API/LLM em um arquivo temporário.
    """

    PASTA_TEMP_TRIAGEM.mkdir(parents=True, exist_ok=True)

    nome_arquivo = f"triagem_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    caminho_arquivo = PASTA_TEMP_TRIAGEM / nome_arquivo

    with open(caminho_arquivo, "w", encoding="utf-8") as arquivo:
        json.dump(dados_paciente, arquivo, ensure_ascii=False, indent=4)

    return caminho_arquivo


def enviar_triagem_para_llm(dados_paciente):
    """
    Envia o JSON da triagem para a API/LLM configurada no .env.
    """

    if not URL_API:
        return {
            "sucesso": False,
            "erro": "URL_API não configurada no arquivo .env"
        }

    resposta = requests.post(
        URL_API,
        json=dados_paciente,
        timeout=60
    )

    resposta.raise_for_status()

    return resposta.json()


def salvar_resposta_llm_temporaria(resultado_llm):
    """
    Salva a resposta da API/LLM em um arquivo temporário.
    """

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
# VERIFICA SE O USUÁRIO TEM PERMISSÃO
# Exemplo: enfermeiro, admin, recepcao etc.
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

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuarioLogin")
        senha = request.form.get("senhaLogin")

        # Exemplo simples para teste.
        # Depois você troca isso por consulta no banco.
        if usuario == "admin" and senha == "123":
            session["usuario_logado"] = usuario
            session["tipo_usuario"] = "enfermeiro"

            return redirect(url_for("inicio"))

        return render_template(
            "seguranca/login.html",
            erro="Usuário ou senha inválidos"
        )

    return render_template("seguranca/login.html")


# ==================================================
# RECUPERAR SENHA
# ==================================================

@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        usuario_digitado = request.form.get("usuarioRecuperar")

        # Simulando a busca no banco de dados
        if usuario_digitado == "admin":
            # Dados originais vindos do banco de dados fictício
            email_original = "testandoteste@gmail.com"
            telefone_original = "55996988211"

            # Aplicando o mascaramento
            email_censurado = mascarar_email(email_original)
            sms_censurado = mascarar_telefone(telefone_original)

            return render_template(
                "seguranca/escolher_metodo.html",
                email=email_censurado,
                sms=sms_censurado
            )

        return render_template(
            "seguranca/esqueci_senha.html",
            erro="Usuário não encontrado."
        )

    return render_template("seguranca/esqueci_senha.html")


# ==================================================
# ENVIAR CÓDIGO
# ==================================================

@app.route("/enviar-codigo", methods=["POST"])
def enviar_codigo():
    # Aqui o sistema leria o "metodo" (email ou sms)
    # e faria o disparo real usando uma API.
    metodo_escolhido = request.form.get("metodo")
    print(f"Enviando código de verificação por: {metodo_escolhido}")

    # Abre a tela para o usuário digitar o código e a nova senha
    return render_template("seguranca/redefinir_senha.html")


# ==================================================
# NOVA SENHA
# ==================================================

@app.route("/salvar-nova-senha", methods=["POST"])
def salvar_nova_senha():
    codigo = request.form.get("codigoVerificacao")
    nova_senha = request.form.get("novaSenha")
    confirmar_senha = request.form.get("confirmarSenha")

    # 1. Verifica se as duas senhas digitadas são iguais
    if nova_senha != confirmar_senha:
        return render_template(
            "seguranca/redefinir_senha.html",
            erro="As senhas não coincidem. Tente novamente."
        )

    # 2. Simulação de verificação de código
    if codigo != "123456":
        return render_template(
            "seguranca/redefinir_senha.html",
            erro="Código de verificação inválido."
        )

    # 3. Sucesso! Aqui o sistema salvaria a senha no banco de dados.
    print("Senha alterada com sucesso no banco de dados!")

    # 4. Redireciona de volta para a tela de login original
    return redirect(url_for("login"))


# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==================================================
# TELAS INTERNAS DO SISTEMA
# ==================================================

@app.route("/inicio")
@login_obrigatorio
def inicio():
    return render_template("index.html")


@app.route("/nova-triagem")
@login_obrigatorio
def nova_triagem():
    return render_template("nova_triagem.html")


@app.route("/triagem", methods=["POST"])
@login_obrigatorio
def gerar_triagem():
    paciente_id = request.form.get("paciente_id", "")
    paciente_nome = request.form.get("paciente_nome", "Paciente não informado")

    idade = request.form.get("idade", "Não informado")
    genero = request.form.get("genero", "Não informado")

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
O caso deve ser analisado considerando os sinais vitais, o relato do paciente, as palavras-chave informadas e possíveis fatores de risco. Esta pré-análise serve apenas como apoio inicial e não substitui a avaliação profissional.
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
        pre_analise=pre_analise
    )


@app.route("/salvar-triagem", methods=["POST"])
@login_obrigatorio
def salvar_triagem():
    paciente_id = request.form.get("paciente_id")
    paciente_nome = request.form.get("paciente_nome")

    idade = request.form.get("idade")
    genero = request.form.get("genero")

    temperatura = request.form.get("temperatura")
    pressao = request.form.get("pressao")
    frequencia = request.form.get("frequencia")
    glicemia = request.form.get("glicemia")

    medicamentos = request.form.get("medicamentos")
    sintomas = request.form.get("sintomas")
    pre_analise = request.form.get("pre_analise")

    palavras_chave_json = request.form.get("palavras_chave", "[]")

    try:
        palavras_chave = json.loads(palavras_chave_json)
    except json.JSONDecodeError:
        palavras_chave = []

    sinais_vitais_texto = montar_sinais_vitais_texto(
        temperatura=temperatura,
        pressao=pressao,
        frequencia=frequencia,
        glicemia=glicemia
    )

    dados_paciente = {
        "idade": limpar_valor(idade),
        "genero": limpar_valor(genero),
        "sintomas": limpar_valor(sintomas),
        "sinais_vitais": sinais_vitais_texto,
        "medicamentos": limpar_valor(medicamentos)
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

    print("\n📦 JSON enviado para API/LLM:")
    print(json.dumps(dados_paciente, ensure_ascii=False, indent=4))

    try:
        print("\n🚀 Enviando dados clínicos para a API/LLM...")

        resultado_llm = enviar_triagem_para_llm(dados_paciente)

        print("\n" + "=" * 60)
        print("📥 TRIAGEM RECEBIDA DO SERVIDOR:")
        print("=" * 60)

        if resultado_llm.get("sucesso"):
            triagem_gerada = resultado_llm.get("triagem", "Triagem não encontrada na resposta.")

            print(triagem_gerada)

            caminho_resposta_llm = salvar_resposta_llm_temporaria(resultado_llm)

            print("=" * 60)
            print("💾 Resposta da LLM salva em:", caminho_resposta_llm)

        else:
            erro_servidor = resultado_llm.get("erro", "Erro não informado pelo servidor.")
            print("❌ Erro retornado pelo servidor:", erro_servidor)

            caminho_resposta_llm = salvar_resposta_llm_temporaria(resultado_llm)
            print("💾 Resposta de erro salva em:", caminho_resposta_llm)

    except requests.exceptions.ConnectionError:
        print("❌ Falha de conexão com a API/LLM.")
        print("Verifique se a URL_API do .env está correta, se o NGINX está ativo e se a rota existe.")

    except requests.exceptions.Timeout:
        print("❌ Timeout: a API/LLM demorou muito para responder.")

    except requests.exceptions.HTTPError as erro:
        print("❌ Erro HTTP retornado pela API/LLM:", erro)

    except json.JSONDecodeError:
        print("❌ A API respondeu, mas não retornou um JSON válido.")

    except Exception as erro:
        print("❌ Erro inesperado ao enviar para a API/LLM:", erro)

    return redirect(url_for("inicio"))


# ==================================================
# PACIENTES
# ==================================================

ARQUIVO_PACIENTES = PASTA_TEMP_TRIAGEM / "pacientes.json"


def carregar_pacientes():
    """
    Carrega os pacientes salvos temporariamente em JSON.
    Depois pode ser substituído por banco de dados.
    """
    PASTA_TEMP_TRIAGEM.mkdir(parents=True, exist_ok=True)

    if not ARQUIVO_PACIENTES.exists():
        return []

    try:
        with open(ARQUIVO_PACIENTES, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)

            if isinstance(dados, list):
                return dados

            return []

    except json.JSONDecodeError:
        return []


def salvar_pacientes(pacientes):
    """
    Salva a lista de pacientes em arquivo JSON temporário.
    """
    PASTA_TEMP_TRIAGEM.mkdir(parents=True, exist_ok=True)

    with open(ARQUIVO_PACIENTES, "w", encoding="utf-8") as arquivo:
        json.dump(pacientes, arquivo, ensure_ascii=False, indent=4)


def gerar_id_paciente():
    """
    Gera um ID simples para o paciente.
    """
    return "PAC" + datetime.now().strftime("%Y%m%d%H%M%S%f")


def formatar_cpf(cpf_numerico):
    """
    Recebe somente números e retorna o CPF formatado.
    Exemplo: 12345678901 -> 123.456.789-01
    """
    return f"{cpf_numerico[:3]}.{cpf_numerico[3:6]}.{cpf_numerico[6:9]}-{cpf_numerico[9:]}"


@app.route("/cadastrar-paciente", methods=["GET", "POST"])
@login_obrigatorio
def cadastrar_paciente():
    if request.method == "POST":
        pacientes = carregar_pacientes()

        nome_completo = request.form.get("nome_completo", "").strip()
        cpf = request.form.get("cpf", "").strip()
        cpf_numerico = "".join(filter(str.isdigit, cpf))

        data_nascimento = request.form.get("data_nascimento", "").strip()
        idade = request.form.get("idade", "").strip()
        genero = request.form.get("genero", "").strip()
        telefone = request.form.get("telefone", "").strip()
        endereco = request.form.get("endereco", "").strip()
        cidade = request.form.get("cidade", "").strip()
        alergias = request.form.get("alergias", "").strip()
        medicamentos = request.form.get("medicamentos", "").strip()
        observacoes = request.form.get("observacoes", "").strip()

        if not nome_completo:
            return render_template(
                "cadastrar_paciente.html",
                erro="O nome completo do paciente é obrigatório."
            )

        if not cpf_numerico:
            return render_template(
                "cadastrar_paciente.html",
                erro="O CPF do paciente é obrigatório."
            )

        if len(cpf_numerico) != 11:
            return render_template(
                "cadastrar_paciente.html",
                erro="O CPF deve conter exatamente 11 dígitos."
            )

        cpf_formatado = formatar_cpf(cpf_numerico)

        for paciente in pacientes:
            cpf_salvo = paciente.get("cpf", "")
            cpf_salvo_numerico = "".join(filter(str.isdigit, cpf_salvo))

            if cpf_salvo_numerico == cpf_numerico:
                return render_template(
                    "cadastrar_paciente.html",
                    erro="Já existe um paciente cadastrado com este CPF."
                )

        novo_paciente = {
            "id": gerar_id_paciente(),
            "nome_completo": nome_completo,
            "cpf": cpf_formatado,
            "data_nascimento": data_nascimento,
            "idade": idade,
            "genero": genero,
            "telefone": telefone,
            "endereco": endereco,
            "cidade": cidade,
            "alergias": alergias,
            "medicamentos": medicamentos,
            "observacoes": observacoes,
            "data_cadastro": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        }

        pacientes.append(novo_paciente)
        salvar_pacientes(pacientes)

        return render_template(
            "cadastrar_paciente.html",
            sucesso="Paciente cadastrado com sucesso."
        )

    return render_template("cadastrar_paciente.html")

# ==================================================
# INICIA O PROJETO
# ==================================================

if __name__ == "__main__":
    app.run(debug=False)