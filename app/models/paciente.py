from app.database import db


class Paciente(db.Model):
    __tablename__ = "pacientes"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    idade = db.Column(db.Integer, nullable=False)
    sexo = db.Column(db.String(20), nullable=False)
    sintomas = db.Column(db.Text, nullable=False)
    temperatura = db.Column(db.Float, nullable=True)
    pressao_arterial = db.Column(db.String(20), nullable=True)
    frequencia_cardiaca = db.Column(db.Integer, nullable=True)
    medicamento_uso_continuo = db.Column(db.Text, nullable=True)
    glicemia = db.Column(db.Float, nullable=True)
    classificacao = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f"<Paciente {self.nome}>"