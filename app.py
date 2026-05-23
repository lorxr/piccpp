import json
from flask import Flask, render_template, request, redirect, session, url_for, abort
from functools import wraps

app = Flask(__name__)

# Chave usada pelo Flask para controlar a sessão do usuário.
# Depois o ideal é colocar isso em um arquivo .env.
app.secret_key = "chave-secreta-do-projeto-pi"

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

        # SE ERRAR A SENHA, RENDERIZA O LOGIN NOVAMENTE E ENVIA O ERRO
        return render_template("seguranca/login.html", erro="Usuário ou Senha inválidos")

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
            
            return render_template("seguranca/escolher_metodo.html", 
                                   email=email_censurado, 
                                   sms=sms_censurado)
                                   
        return render_template("seguranca/esqueci_senha.html", erro="Usuário não encontrado.")
        
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
        return render_template("seguranca/redefinir_senha.html", erro="As senhas não coincidem. Tente novamente.")

    # 2. Simulação de verificação de código (vamos fingir que o código certo é "123456")
    if codigo != "123456":
        return render_template("seguranca/redefinir_senha.html", erro="Código de verificação inválido.")

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

    print("=== TRIAGEM SALVA ===")
    print("Paciente ID:", paciente_id)
    print("Paciente:", paciente_nome)
    print("Temperatura:", temperatura)
    print("Pressão:", pressao)
    print("Frequência:", frequencia)
    print("Glicemia:", glicemia)
    print("Medicamentos:", medicamentos)
    print("Sintomas:", sintomas)
    print("Palavras-chave:", palavras_chave)
    print("Pré-análise:", pre_analise)

    return redirect(url_for("inicio"))


# ==================================================
# INICIA O PROJETO
# ==================================================

if __name__ == "__main__":
    app.run(debug=True)