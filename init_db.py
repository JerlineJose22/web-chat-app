'''To create all needed tables'''
from app import app, db
with app.app_context():
    db.create_all()
