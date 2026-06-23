import eventlet
eventlet.monkey_patch()
import os
import requests
from flask import Flask, render_template, url_for, request, make_response  # Replaced send_from_directory
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

# Custom raw-byte file server to bypass buggy Eventlet wsgi.file_wrapper
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    
    if not os.path.exists(filepath):
        return "File not found", 404
        
    # Read raw bytes directly into memory to prevent server deadlocks
    with open(filepath, 'rb') as f:
        file_bytes = f.read()
        
    response = make_response(file_bytes)
    
    # Explicitly map common image headers
    if filename.lower().endswith(('.jpg', '.jpeg')):
        response.headers['Content-Type'] = 'image/jpeg'
    elif filename.lower().endswith('.png'):
        response.headers['Content-Type'] = 'image/png'
    elif filename.lower().endswith('.gif'):
        response.headers['Content-Type'] = 'image/gif'
        
    response.headers['Content-Length'] = len(file_bytes)
    return response

@socketio.on('connect')
def handle_connect():
    if current_photo:
        emit('update_image', {'url': url_for('uploaded_file', filename=current_photo)})

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
        
        # Save the incoming multipart stream cleanly to disk
        file.save(filepath)
        
        current_photo = filename
        image_url = url_for('uploaded_file', filename=filename)
        
        # Wake up all connected clients instantly
        socketio.emit('update_image', {'url': image_url})

        # Send to Discord securely from the saved disk file
        if DISCORD_WEBHOOK_URL:
            try:
                with open(filepath, 'rb') as f:
                    disk_data = f.read()
                files = {'file': (filename, disk_data)}
                payload = {'content': '📸 **New photo uploaded to SoFar!**'}
                # Added timeout=5 to ensure slow external APIs never freeze Gunicorn
                requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files, timeout=5)
            except Exception as e:
                print(f"Failed to send to Discord: {e}")
                
        return {'success': True, 'url': image_url}, 200

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)