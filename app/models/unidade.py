from app.database import db

#Atendimento
#	paciente
#	horário
#	unidade(posto de saúde)
class Unidade(db.Model):
    __tablename__ = "unidades"

    idUnidade = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    cep = db.Column(db.String(20), nullable=False)
    bairro = db.Column(db.String(2), nullable=False)
    bairro = db.Column(db.String(120), nullable=False)
    logradouro = db.Column(db.String(120), nullable=False)
    numero = db.Column(db.Integer, nullable=False)
   

    def __repr__(self):
        return f"<Unidade {self.nome}>"