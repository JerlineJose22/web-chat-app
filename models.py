'''Database Models for the web chat'''
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    '''Table for users'''
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.Text, nullable=False)

class Message(db.Model):
    '''Table for Messages'''
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(20), nullable=False)
    recipient = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    is_read = db.Column(db.Boolean, server_default='f', nullable=False)
