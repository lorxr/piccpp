from flask import Flask, render_template, request

app = Flask(__name__)

# Rota 1: Acessou o site puro (localhost:5000/)
@app.route("/")
def home():
    # Renderiza o index.html com a mensagem padrão de boas-vindas
    return render_template("index.html")

# Rota 2: Clicou em "Nova Triagem" no menu
# Rota que abre a tela de triagem
# Mude de "/nova_triagem" para "/nova-triagem"
@app.route("/nova-triagem")
def tela_nova_triagem():
    # O nome do arquivo HTML continua com underline
    return render_template("nova_triagem.html")

# Rota 3: Onde o formulário envia os dados
@app.route("/triagem", methods=['POST'])
def processar_triagem():
    dados = {
        "nome": request.form.get("nome"),
        "temperatura": request.form.get("temperatura"),
        "pressao": request.form.get("pressao"),
        "frequencia": request.form.get("frequencia"),
        "sintomas": request.form.get("sintomas")
    }
    
    print("Dados recebidos da enfermagem:", dados)
    
    # Aqui futuramente você vai passar 'dados' para a IA e salvar no Banco
    return "Dados recebidos com sucesso! Olhe o terminal do VS Code."

if __name__ == "__main__":
    app.run(debug=True)