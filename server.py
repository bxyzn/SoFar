import eventlet
eventlet.monkey_patch()
import os
import requests
from flask import Flask, render_template, url_for, send_from_directory, request  # Added request import
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_frame_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

socketio = SocketIO(
    app, 
    async_mode='eventlet', 
    cors_allowed_origins="*", 
    max_decode_size=16 * 1024 * 1024
)

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

# Handles uploads robustly over standard HTTP to prevent 0-byte corrupt files
@app.route('/upload', methods=['POST'])
def upload_file_http():
    global current_photo
    
    if 'file' not in request.files:
        return {'error': 'No file part'}, 400
        
    file = request.files['file']
    if file.filename == '':
        return {'error': 'No selected file'}, 400
        
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Stream and save directly to disk
        file.save(filepath)
        
        current_photo = filename
        image_url = url_for('uploaded_file', filename=filename)
        
        # Broadcast via WebSocket so every client screen refreshes immediately
        socketio.emit('update_image', {'url': image_url})

        # Send to Discord securely
        if DISCORD_WEBHOOK_URL:
            try:
                file.seek(0)
                file_data = file.read()
                files = {'file': (filename, file_data)}
                payload = {'content': '📸 **New photo uploaded to SoFar!**'}
                requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
            except Exception as e:
                print(f"Failed to send to Discord: {e}")
                
        return {'success': True, 'url': image_url}, 200

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)