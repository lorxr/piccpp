import json
from flask import Flask, render_template, request, redirect, session, url_for, abort
from functools import wraps

app = Flask(__name__)

# Chave usada pelo Flask para controlar a sessão do usuário.
# Depois o ideal é colocar isso em um arquivo .env.
app.secret_key = "chave-secreta-do-projeto-pi"


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

@app.route("/")
def abrir_login():
    return render_template("seguranca/login.html")


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

        return "Usuário ou senha inválidos"

    return render_template("seguranca/login.html")


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