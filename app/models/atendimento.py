from app.database import db

class Atendimento(db.Model):
    __tablename__ = "atendimentos"

    idAtend = db.Column(db.Integer, primary_key=True)
    

    paciente_id = db.Column(db.Integer, db.ForeignKey('pacientes.id'), nullable=False)
    unidade_id = db.Column(db.Integer, db.ForeignKey('unidades.idUnidade'), nullable=False)
    
    horarioAtend = db.Column(db.DateTime, nullable=False)
    sintomas = db.Column(db.Text, nullable=False)
    temperatura = db.Column(db.Float, nullable=True)
    pressao_arterial = db.Column(db.String(20), nullable=True)
    frequencia_cardiaca = db.Column(db.Integer, nullable=True)
    glicemia = db.Column(db.Float, nullable=True)
  
    classificacao_ia = db.Column(db.String(50), nullable=True) 
    diagnostico_provavel = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<Atendimento {self.idAtend}>"