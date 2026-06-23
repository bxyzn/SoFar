import eventlet
eventlet.monkey_patch()
import os
import requests
from flask import Flask, render_template, url_for, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from dotenv import load_dotenv  # <-- New import

# Load environment variables from a .env file if it exists
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_frame_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Fetch the webhook URL from the environment variable securely
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

current_photo = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@socketio.on('connect')
def handle_connect():
    if current_photo:
        emit('update_image', {'url': url_for('uploaded_file', filename=current_photo)})

@socketio.on('upload_image')
def handle_upload(data):
    global current_photo
    file_data = data.get('file')
    filename = secure_filename(data.get('filename'))
    
    if file_data and filename:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(filepath, 'wb') as f:
            f.write(file_data)
        
        current_photo = filename
        image_url = url_for('uploaded_file', filename=filename)
        emit('update_image', {'url': image_url}, broadcast=True)

        # Send to Discord securely
        if DISCORD_WEBHOOK_URL:
            try:
                files = {'file': (filename, file_data)}
                payload = {'content': '📸 **New photo uploaded to SoFar!**'}
                requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
            except Exception as e:
                print(f"Failed to send to Discord: {e}")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
