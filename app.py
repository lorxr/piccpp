from flask import Flask, render_template, request, redirect

app = Flask(__name__)


@app.route("/")
def abrir_login():
    return render_template("seguranca/login.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuarioLogin")
        senha = request.form.get("senhaLogin")

        print("Usuário:", usuario)
        print("Senha:", senha)

        return redirect("/inicio")

    return render_template("seguranca/login.html")


@app.route("/inicio")
def inicio():
    return render_template("index.html")


@app.route("/nova-triagem")
def nova_triagem():
    return render_template("nova_triagem.html")


@app.route("/triagem", methods=["POST"])
def processar_triagem():
    dados = {
        "nome": request.form.get("nome"),
        "temperatura": request.form.get("temperatura"),
        "pressao": request.form.get("pressao"),
        "frequencia": request.form.get("frequencia"),
        "sintomas": request.form.get("sintomas")
    }

    print("Dados recebidos da enfermagem:", dados)

    return "Dados recebidos com sucesso! Olhe o terminal do VS Code."


if __name__ == "__main__":
    app.run(debug=True)