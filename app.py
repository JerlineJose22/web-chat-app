'''
Web chat application
using kafak as communication portocol
'''
from flask import Flask, render_template, redirect, url_for, session, request, jsonify, flash
from flask_bcrypt import Bcrypt
import threading
import os
from models import db, User, Message
import json
from kafka import KafkaProducer, KafkaConsumer
from collections import deque
from datetime import datetime

# Initialize Flask app and extensions
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI']=os.getenv('DATABASE_URL',
                                            'postgresql://postgres:9626831649@localhost/postgres')
bcrypt = Bcrypt(app)
db.init_app(app)

#initiat kafka producer
producer = KafkaProducer(bootstrap_servers='localhost:9092',
                         value_serializer=lambda v: json.dumps(v).encode('utf-8'))

message_queue = {}  # Store recent messages in memory

class KafkaConsumerThread(threading.Thread):
    '''
    Initial the kafka consumer to consume the from toppic
    '''
    def __init__(self, topic, username):
        threading.Thread.__init__(self)
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers='localhost:9092',
            enable_auto_commit=True,
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        self.username = username  # Store the username associated with this thread
        self.daemon = True

    def run(self):
        for message in self.consumer:
            data = message.value
            recipient= data['recipient']
            if recipient in message_queue:
                message_queue[recipient].append(data)
            print(f"Received message for {self.username}: {data}")  # Debug print

# Store consumer threads
consumer_threads = {}

@app.route('/')
def home():
    ''' Redirect the user to login page to login '''
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    ''' 
    Get the username and password from user.
    And store the username and password in DB for validation
    '''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose a different username.', 'error')
            return redirect(url_for('register'))
        user = User(username=username, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    ''' Get the username and password and validate the details '''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            session['username'] = user.username
            flash('You have been logged in!', 'success')
            if username not in message_queue:
                message_queue[username]=deque(maxlen=100)
            # Start a Kafka consumer for this user if not already running
            if username not in consumer_threads:
                consumer_thread = KafkaConsumerThread(username, username)
                consumer_thread.start()
                consumer_threads[username] = consumer_thread
            return redirect(url_for('chat'))
        flash('Wrong Username/Passsword, Please check!!  ', 'warning')
    return render_template('login.html')

@app.route('/logout')
def logout():
    '''Logout the user and clear the session'''
    session.pop('username', None)
    flash ('You have been Logged out ! ! ','success')
    return redirect(url_for('login'))

@app.route('/chat')
def chat():
    ''' Redirect the user to chat page with login authentication '''
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', username=session['username'])

@app.route('/send_message', methods=['POST'])
def send_message():
    '''
    receives data from frontend
    produce through kafka
    write to db
    '''
    data = request.json
    sender = data['sender']
    recipient = data['recipient']
    message = data['message']
    timestamp = datetime.utcnow().isoformat()
    # Produce the message to Kafka topic for the recipient
    producer.send(recipient,value={'sender': sender,
                                    'recipient': recipient,
                                    'message': message,
                                    'timestamp': timestamp})
    producer.flush()
    #Save the message in the database
    new_message = Message(sender=sender, recipient=recipient, content=message)
    db.session.add(new_message)
    db.session.commit()
    return jsonify({'success': True, 'message_id': new_message.id})

@app.route('/get_messages')
def get_messages():
    '''Sending the consumed data to frontend'''
    if 'username' not in session:
        return jsonify([])
    username= session['username']
    if username in message_queue:
        messages=list(message_queue[username])
        message_queue[username].clear()
        return jsonify(messages)
    return jsonify([])

@app.route('/chat_history/<recipient>')
def chat_history(recipient):
    '''Get the chat history from the db'''
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    history = Message.query.filter(
        ((Message.sender == username) & (Message.recipient == recipient)) |
        ((Message.sender == recipient) & (Message.recipient == username))
    ).all()
    for msg in history:
        if msg.recipient == session['username']:
            msg.is_read = True
    db.session.commit()
    return jsonify([{'sender': msg.sender,'recipient': msg.recipient,
                     'content': msg.content,
                     'timestamp': msg.timestamp.isoformat()} for msg in history])

@app.route('/mark_read', methods=['POST'])
def mark_read():
    '''change the is_read column of db true, when the user in the chat'''
    data=request.json
    username = session['username']
    recipient = data['recipient']
    read=Message.query.filter(
        ((Message.sender == username) & (Message.recipient == recipient)) |
        ((Message.sender == recipient) & (Message.recipient == username))
    ).all()
    for msg in read:
        if msg.recipient == session['username']:
            msg.is_read = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/users')
def get_users():
    '''Get the available users from the db and the sent it to the frontend'''
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    all_users = User.query.all()
    users = []
    for user in all_users:
        if user.username != username:
            unread_count = Message.query.filter_by(recipient=username,
                                                   sender=user.username,
                                                   is_read=False).count()
            users.append({'username': user.username, 'unread_count': unread_count})
    return jsonify(users)

if __name__ == '__main__':
    app.run(debug=True)
