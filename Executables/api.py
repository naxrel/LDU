import os
import json
import uuid 
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import zipfile  # [NEW]
import io       # [NEW]
import threading# [NEW]
import cv2      # [NEW]
import numpy as np # [NEW]
from datetime import datetime, timezone # [WAJIB] Impor timezone

import face_service

# --- Konfigurasi ---
app = Flask(__name__)
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'app.db')

# File/Folder paths
upload_folder = os.path.join(base_dir, 'temp_uploads')
face_dataset_dir = os.path.join(base_dir, 'face_dataset')
face_model_dir = os.path.join(base_dir, 'face_model')   

# [NEW] Model file paths
CASCADE_FILE = os.path.join(base_dir, "haarcascade_frontalface_default.xml")
MODEL_FILE = os.path.join(face_model_dir, "model.yml")
MAPPING_FILE = os.path.join(face_model_dir, "name_mapping.json")

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = upload_folder 
MAX_FILE_SIZE = 2 * 1024 * 1024 
db = SQLAlchemy(app)

RECOGNIZER = None
ID_TO_NAME_MAP = {}
FACE_DETECTOR = None

# --- Definisi Database (Model) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    salt_hex = db.Column(db.String(32), nullable=False)
    hash_hex = db.Column(db.String(64), nullable=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(160), nullable=False, index=True)
    sender = db.Column(db.String(80), nullable=False)
    recipient = db.Column(db.String(80), nullable=False)
    message_data_json = db.Column(db.Text, nullable=False)
    
    # [PERBAIKAN BUG #1] Gunakan lambda untuk default agar selalu aware-timezone (UTC)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# --- HTML TEMPLATE (Tidak berubah) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head><meta charset="UTF-8"><title>API Status</title>
    <style>
        body { margin: 0; padding: 0; font-family: 'Segoe UI', sans-serif;
            background-image: url('https://i.ibb.co/68q5g1Q/bg-dark-blue.jpg');
            background-size: cover; background-repeat: no-repeat;
            background-position: center; color: white; text-align: center; }
        .overlay { background: rgba(0,0,0,0.6); height: 100vh;
            display: flex; flex-direction: column; justify-content: center; }
        h1 { font-size: 2.5em; margin-bottom: 0.3em; font-weight: 300; }
        p { font-size: 1.1em; color: #dfe6e9; font-weight: 300; }
    </style>
</head>
<body><div class="overlay"><h1>API Berjalan</h1><p>Layanan Kriptografi Aktif.</p></div></body>
</html>
"""

# --- Endpoint API (Dasar) ---
@app.route('/')
def hello():
    return render_template_string(HTML_TEMPLATE)

@app.route('/register', methods=['POST'])
def register_user():
    data = request.json
    username = data['username']
    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "Username sudah ada."}), 400
    new_user = User(
        username=username, salt_hex=data['salt_hex'], hash_hex=data['hash_hex']
    )
    db.session.add(new_user); db.session.commit()
    return jsonify({"success": True, "message": "Akun berhasil dibuat!"})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"salt_hex": "00000000000000000000000000000000", "hash_hex": "0000000000000000000000000000000000000000000000000000000000000000"})
    return jsonify({"salt_hex": user.salt_hex, "hash_hex": user.hash_hex})

@app.route('/save_message', methods=['POST'])
def save_message():
    data = request.json
    chat_id = data['chat_id']; sender = data['sender']; recipient = data['recipient']
    if 'data' in data and data.get('type') in ['stegano', 'file']:
        data['data'] = None 
    message_json = json.dumps(data)
    new_message = Message(
        chat_id=chat_id, sender=sender, recipient=recipient, message_data_json=message_json
    )
    db.session.add(new_message); db.session.commit()
    return jsonify({"success": True})

@app.route('/load_messages/<chat_id>', methods=['GET'])
def load_messages(chat_id):
    # [PERBAIKAN BUG #1] Sertakan timestamp (sekarang sudah aware-timezone)
    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.id.asc()).all()
    message_list = []
    for msg in messages:
        try:
            data = json.loads(msg.message_data_json)
            # Pastikan timestamp adalah aware-UTC sebelum dikirim
            timestamp = msg.timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
                
            data['db_timestamp'] = timestamp.isoformat()
            message_list.append(data)
        except json.JSONDecodeError:
            print(f"Peringatan: Melewatkan message id {msg.id} karena JSON korup.")
            
    return jsonify(message_list)

# --- LOGIKA VIGENERE (Tidak berubah) ---
def vigenere_encrypt_logic(plain_text, key):
    encrypted_text = ""; key_index = 0; key = key.lower()
    if not key: key = "defaultkey"
    for char in plain_text:
        if 'a' <= char <= 'z':
            key_char = key[key_index % len(key)]; key_offset = ord(key_char) - ord('a')
            new_char_code = (ord(char) - ord('a') + key_offset) % 26
            encrypted_text += chr(new_char_code + ord('a')); key_index += 1
        elif 'A' <= char <= 'Z':
            key_char = key[key_index % len(key)]; key_offset = ord(key_char) - ord('a')
            new_char_code = (ord(char) - ord('A') + key_offset) % 26
            encrypted_text += chr(new_char_code + ord('A')); key_index += 1
        else: encrypted_text += char
    return encrypted_text

def vigenere_decrypt_logic(encrypted_text, key):
    decrypted_text = ""; key_index = 0; key = key.lower()
    if not key: key = "defaultkey"
    for char in encrypted_text:
        if 'a' <= char <= 'z':
            key_char = key[key_index % len(key)]; key_offset = ord(key_char) - ord('a')
            new_char_code = (ord(char) - ord('a') - key_offset) % 26
            decrypted_text += chr(new_char_code + ord('a')); key_index += 1
        elif 'A' <= char <= 'Z':
            key_char = key[key_index % len(key)]; key_offset = ord(key_char) - ord('a')
            new_char_code = (ord(char) - ord('A') - key_offset) % 26
            decrypted_text += chr(new_char_code + ord('A')); key_index += 1
        else: decrypted_text += char
    return decrypted_text

# --- ENDPOINT API VIGENERE (Tidak berubah) ---
@app.route('/encrypt/vigenere', methods=['POST'])
def api_vigenere_encrypt():
    data = request.json
    plain_text = data.get('text'); key = data.get('key')
    if not plain_text or key is None:
        return jsonify({"error": "Butuh 'text' dan 'key'"}), 400
    encrypted_text = vigenere_encrypt_logic(plain_text, key)
    return jsonify({"result": encrypted_text})

@app.route('/decrypt/vigenere', methods=['POST'])
def api_vigenere_decrypt():
    data = request.json
    encrypted_text = data.get('text'); key = data.get('key')
    if not encrypted_text or key is None:
        return jsonify({"error": "Butuh 'text' dan 'key'"}), 400
    decrypted_text = vigenere_decrypt_logic(encrypted_text, key)
    return jsonify({"result": decrypted_text})

# --- ENDPOINT DASHBOARD (Tidak berubah) ---
@app.route('/get_chats/<username>', methods=['GET'])
def get_chats(username):
    try:
        sent_to = db.session.query(Message.recipient).filter(Message.sender == username).distinct()
        received_from = db.session.query(Message.sender).filter(Message.recipient == username).distinct()
        contacts = set()
        for r in sent_to: contacts.add(r.recipient)
        for s in received_from: contacts.add(s.sender)
        return jsonify({"success": True, "contacts": list(contacts)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --- ENDPOINT FILE (Tidak berubah) ---
@app.route('/upload_file/<chat_id>', methods=['POST'])
def upload_file(chat_id):
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file"}), 400
    try:
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > MAX_FILE_SIZE:
            return jsonify({"success": False, "message": f"File melebihi batas 2MB."}), 413
        original_filename = file.filename
        extension = os.path.splitext(original_filename)[1]
        unique_filename = f"{uuid.uuid4()}{extension}"
        chat_upload_path = os.path.join(app.config['UPLOAD_FOLDER'], chat_id)
        if not os.path.exists(chat_upload_path):
            os.makedirs(chat_upload_path)
        save_path = os.path.join(chat_upload_path, unique_filename)
        file.save(save_path)
        return jsonify({"success": True, "file_id": unique_filename})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/download_file/<chat_id>/<file_id>', methods=['GET'])
def download_file(chat_id, file_id):
    try:
        chat_upload_path = os.path.join(app.config['UPLOAD_FOLDER'], chat_id)
        return send_from_directory(chat_upload_path, file_id, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"success": False, "message": "File not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --- Jalankan Aplikasi ---
def run_training_in_background(app_context, dataset_dir, model_path, mapping_path):
    """Helper function to run slow training in a thread."""
    global RECOGNIZER, ID_TO_NAME_MAP # [NEW] Tell it to update globals
    with app_context:
        print("Background training started...")
        success = face_service.train_model(dataset_dir, model_path, mapping_path)
        print(f"Background training finished. Success: {success}")
        
        # [NEW] After training, reload the models into memory
        if success:
            try:
                RECOGNIZER = cv2.face.LBPHFaceRecognizer_create()
                RECOGNIZER.read(MODEL_FILE)
                with open(MAPPING_FILE, 'r') as f:
                    name_mapping = json.load(f)
                    ID_TO_NAME_MAP = {v: k for k, v in name_mapping.items()}
                print("Models reloaded into server memory.")
            except Exception as e:
                print(f"Error reloading models after training: {e}")


@app.route('/register-face', methods=['POST'])
def register_face():
    if 'username' not in request.form:
        return jsonify({"success": False, "message": "Username diperlukan."}), 400
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Zip file gambar diperlukan."}), 400

    username = request.form['username']
    file = request.files['file'] # This will be the zip file

    # Check if user exists in the main DB
    if not User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "Username not registered in main database."}), 404

    # Create the user's dataset folder on the server
    user_dataset_path = os.path.join(face_dataset_dir, username)
    os.makedirs(user_dataset_path, exist_ok=True)

    # Unzip the file and save the images
    try:
        zip_data = io.BytesIO(file.read())
        with zipfile.ZipFile(zip_data, 'r') as z:
            z.extractall(user_dataset_path)
        print(f"Successfully extracted {len(z.namelist())} images for {username}.")
    except Exception as e:
        print(f"Error unzipping file: {e}")
        return jsonify({"success": False, "message": f"Error reading zip file: {e}"}), 500

    # Start the training in a separate thread
    app_context = app.app_context()
    threading.Thread(target=run_training_in_background, args=(
        app_context, face_dataset_dir, MODEL_FILE, MAPPING_FILE
    )).start()

    return jsonify({"success": True, "message": "Images received. Training has started in the background."})


@app.route('/login-face', methods=['POST'])
def login_face():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "File gambar diperlukan."}), 400
    
    file = request.files['file']

    # Check if models are loaded
    if RECOGNIZER is None or not ID_TO_NAME_MAP or FACE_DETECTOR is None:
        return jsonify({"success": False, "message": "Server models are not loaded. Please train a user first."}), 503

    # Call our recognition service
    (name, message) = face_service.recognize_face(
        file.stream, 
        RECOGNIZER, 
        ID_TO_NAME_MAP, 
        FACE_DETECTOR, 
        confidence_threshold=65 # Your threshold
    )

    if name and name != "Unknown":
        # SUCCESS!
        return jsonify({"success": True, "username": name})
    else:
        # FAILURE
        return jsonify({"success": False, "message": message})


# [ ... (kode api lainnya) ... ]

# --- Inisialisasi Aplikasi (PINDAHKAN KE SINI) ---
# Pindahkan semua logika startup ke scope global
# agar Gunicorn dapat menjalankannya saat impor.
with app.app_context():
    # Ensure all folders exist
    os.makedirs(upload_folder, exist_ok=True)
    os.makedirs(face_dataset_dir, exist_ok=True)
    os.makedirs(face_model_dir, exist_ok=True)  
    
    # Create DB tables
    db.create_all()
    
    # Load models into memory on startup
    print("Loading face recognition models into server memory...")
    try:
        if not os.path.exists(CASCADE_FILE):
            print(f"FATAL ERROR: Cascade file not found at {CASCADE_FILE}")
        else:
            FACE_DETECTOR = cv2.CascadeClassifier(CASCADE_FILE)
            print("Face detector loaded.")

        if not os.path.exists(MODEL_FILE) or not os.path.exists(MAPPING_FILE):
            print(f"Warning: Model files not found. Please register a face to create them.")
        else:
            RECOGNIZER = cv2.face.LBPHFaceRecognizer_create()
            RECOGNIZER.read(MODEL_FILE)
            with open(MAPPING_FILE, 'r') as f:
                name_mapping = json.load(f)
                # Create the {1: "user", 2: "admin"} mapping
                ID_TO_NAME_MAP = {int(v): k for k, v in name_mapping.items()}
            print("Recognizer model and name mapping loaded.")
    except Exception as e:
        print(f"Error loading models: {e}")

# --- Jalankan Aplikasi ---
# HANYA app.run() yang boleh ada di sini.
if __name__ == '__main__':
    # Blok ini hanya akan berjalan jika Anda menggunakan: python3 api.py
    # Gunicorn akan MELEWATI blok ini.
    app.run(host='0.0.0.0', port=5000, debug=True)