import os
import base64
import requests
import uuid
import hashlib 
import json    
from stegano import lsb
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox,
    QListWidget, QListWidgetItem, QFileDialog,
    QInputDialog, QFrame, QApplication, QDialog,
    QSizePolicy, QListView, QTextEdit
)
from PySide6.QtGui import QFont, QColor, QPixmap
from PySide6.QtCore import Qt, QSize, QTimer
from datetime import datetime, timezone 
import winsound # Diperlukan untuk fitur Audio

# Pastikan utils.py ada di satu folder yang sama dan sudah memiliki fungsi audio
from utils import (
    CryptoEngine, vigenere_encrypt, vigenere_decrypt, 
    encrypt_whitemist, decrypt_whitemist,
    text_to_alien_audio, alien_audio_to_text
)

class ChatPage(QWidget):
    
    # --- Palet Warna ---
    COLOR_BACKGROUND = "#1A1B2E"
    COLOR_PANE_LEFT = "#272540" 
    COLOR_PANE_RIGHT = "#1A1B2E"
    COLOR_CARD_BG = "#272540"
    COLOR_CARD = "#3E3C6E"     
    COLOR_CARD_HOVER = "#504E8A" 
    COLOR_TEXT = "#F0F0F5"
    COLOR_TEXT_SUBTLE = "#A9A8C0"
    COLOR_GOLD = "#D4AF37"
    COLOR_GOLD_HOVER = "#F0C44F"
    COLOR_GOLD_PRESSED = "#B8860B"
    COLOR_RED = "#ed4956"
    COLOR_RED_HOVER = "#ff7d6e"
    COLOR_RED_PRESSED = "#e63946"
    COLOR_BUBBLE_SENT = "#3C506E" 
    COLOR_BUBBLE_RECV = "#3E3C6E"
    # -------------------

    def __init__(self, current_user, recipient_username, shared_password, message_manager, back_callback):
        super().__init__()
        self.current_user = current_user
        self.recipient_username = recipient_username
        self.message_manager = message_manager
        self.back_callback = back_callback
        
        self.chat_id = self.message_manager.get_chat_id(self.current_user, self.recipient_username)
        self.session_crypto = CryptoEngine(shared_password)
        
        self.api_url = "https://morsz.azeroth.site/"
        self.MAX_FILE_SIZE = 2 * 1024 * 1024 # 2MB
        
        script_file_path = os.path.abspath(__file__)
        script_dir = os.path.dirname(script_file_path)
        base_project_dir = os.path.dirname(script_dir)

        self.base_data_dir = os.path.join(base_project_dir, "local_data")
        self.cache_dir = os.path.join(self.base_data_dir, "user_caches")
        self.cache_file = os.path.join(self.cache_dir, f"cache_{self.current_user}.json")
        self.message_cache = self.load_cache()
        
        self.temp_stegano_dir = os.path.join(self.base_data_dir, "temp_stegano")
        self.temp_download_dir = os.path.join(self.base_data_dir, "temp_downloads")
        self.temp_decrypted_dir = os.path.join(self.base_data_dir, "temp_decrypted")
        self.temp_audio_dir = os.path.join(self.base_data_dir, "temp_audio") # [BARU: Folder Audio]
        
        # [OPTIMASI] Set untuk melacak ID pesan yang SUDAH tampil di layar.
        self.rendered_message_ids = set()
        
        # Buat semua folder yang diperlukan
        for folder in [self.base_data_dir, self.cache_dir, self.temp_stegano_dir, self.temp_download_dir, self.temp_decrypted_dir, self.temp_audio_dir]:
            if not os.path.exists(folder):
                os.makedirs(folder)

        self.init_ui() 
        
        # Refresh saat pertama kali masuk
        QTimer.singleShot(0, self.refresh_chat_display)
        
        # Mulai polling data setiap 1 detik (1000ms)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.refresh_chat_display)
        self.poll_timer.start(1000) 

    # --- Cache Functions ---
    def get_message_id(self, metadata):
        msg_type = metadata.get('type')
        if msg_type == 'text':
            return hashlib.md5(metadata.get('data', '').encode('utf-8')).hexdigest()
        elif msg_type in ['stegano', 'file', 'audio_secret']: # [UPDATE: Support Audio ID]
            return metadata.get('file_id')
        return None

    def load_cache(self):
        if not os.path.exists(self.cache_file): return {}
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError): return {} 

    def save_to_cache(self, message_id, data_to_cache):
        if not message_id: return
        self.message_cache[message_id] = data_to_cache
        try:
            if not os.path.exists(self.cache_dir):
                os.makedirs(self.cache_dir)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.message_cache, f, indent=2, ensure_ascii=False)
        except IOError as e: print(f"Peringatan: Gagal menyimpan cache ke file: {e}")
    # -----------------------

    def init_ui(self):
        self.resize(700, 800) 
        self.setStyleSheet(f"background-color: {self.COLOR_BACKGROUND};")
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)

        top_bar_layout = QHBoxLayout()
        back_btn = QPushButton("< Back")
        back_btn.setStyleSheet(self.button_style(
            base=self.COLOR_RED, hover=self.COLOR_RED_HOVER, pressed=self.COLOR_RED_PRESSED, radius=10
        ))
        
        back_btn.clicked.connect(self.handle_back_pressed)
        back_btn.setFixedWidth(100)
        
        title = QLabel(f"Chat with: {self.recipient_username}")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {self.COLOR_GOLD};"); 
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        top_bar_layout.addWidget(back_btn); top_bar_layout.addWidget(title)
        
        self.chat_display = QListWidget()
        self.chat_display.setStyleSheet(f"""
            QListWidget {{ 
                background-color: {self.COLOR_PANE_LEFT}; 
                border: 2px solid {self.COLOR_GOLD};
                border-radius: 12px; 
                color: {self.COLOR_TEXT}; 
            }}
        """)
        self.chat_display.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.chat_display.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chat_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.chat_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # --- [OPTIMASI SCROLL LAG] ---
        self.chat_display.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.chat_display.setUniformItemSizes(False)
        self.chat_display.setLayoutMode(QListView.LayoutMode.Batched)
        self.chat_display.setBatchSize(10)
        self.chat_display.setWordWrap(False)
        # -----------------------------
        
        self.chat_display.itemClicked.connect(self.on_chat_item_clicked)

        input_bar_layout = QHBoxLayout()
        
        # --- BUTTONS ---
        self.attach_btn = QPushButton("🖼️ Gbr"); self.attach_btn.setToolTip("Sembunyikan teks dari input ke dalam Gambar (.png)")
        self.attach_btn.setFont(QFont("Segoe UI", 12)); 
        self.attach_btn.setStyleSheet(self.button_style(
            base=self.COLOR_CARD, hover=self.COLOR_CARD_HOVER, pressed=self.COLOR_CARD_BG, radius=10
        ))
        self.attach_btn.setFixedSize(70, 45)
        self.attach_btn.clicked.connect(self.handle_attach_image_stegano)

        self.attach_file_btn = QPushButton("📂 File"); 
        self.attach_file_btn.setToolTip("Enkripsi file (AES / White-Mist)")
        self.attach_file_btn.setFont(QFont("Segoe UI", 12)); 
        self.attach_file_btn.setStyleSheet(self.button_style(
            base=self.COLOR_CARD, hover=self.COLOR_CARD_HOVER, pressed=self.COLOR_CARD_BG, radius=10
        ))
        self.attach_file_btn.setFixedSize(70, 45)
        self.attach_file_btn.clicked.connect(self.handle_attach_file) 
        
        # [BARU] Tombol Audio
        self.attach_audio_btn = QPushButton("📡 Audio"); 
        self.attach_audio_btn.setToolTip("Ubah teks menjadi Audio Alien (WAV)")
        self.attach_audio_btn.setFont(QFont("Segoe UI", 12)); 
        self.attach_audio_btn.setStyleSheet(self.button_style(
            base=self.COLOR_CARD, hover=self.COLOR_CARD_HOVER, pressed=self.COLOR_CARD_BG, radius=10
        ))
        self.attach_audio_btn.setFixedSize(70, 45)
        self.attach_audio_btn.clicked.connect(self.handle_attach_audio)
        # -------------------

        self.message_input = QLineEdit(); self.message_input.setPlaceholderText("Ketik pesan...")
        self.message_input.setStyleSheet(self.input_style()) 
        self.message_input.returnPressed.connect(self.handle_send_message_super)

        self.send_btn = QPushButton("Send Txt"); self.send_btn.setToolTip("Kirim teks dengan Super Enkripsi (Vigenere -> White Mist -> AES Sesi)")
        self.send_btn.setFont(QFont("Segoe UI", 11, QFont.Bold)); 
        self.send_btn.setStyleSheet(self.button_style(
            base=self.COLOR_GOLD, hover=self.COLOR_GOLD_HOVER, pressed=self.COLOR_GOLD_PRESSED, 
            radius=22, text_color=self.COLOR_PANE_LEFT
        ))
        self.send_btn.setFixedSize(100, 45)
        self.send_btn.clicked.connect(self.handle_send_message_super)

        input_bar_layout.addWidget(self.attach_btn); 
        input_bar_layout.addWidget(self.attach_file_btn)
        input_bar_layout.addWidget(self.attach_audio_btn) # [BARU]
        input_bar_layout.addWidget(self.message_input); 
        input_bar_layout.addWidget(self.send_btn)
        
        layout.addLayout(top_bar_layout); layout.addWidget(self.chat_display); layout.addLayout(input_bar_layout)
        
    def handle_back_pressed(self):
        if hasattr(self, 'poll_timer') and self.poll_timer.isActive():
            self.poll_timer.stop()
            print("ChatPage: Polling timer stopped.")
        self.back_callback()

    def refresh_chat_display(self):
        """
        Logika Refresh Cerdas: Hanya render ID pesan baru.
        """
        all_messages = self.message_manager.load_messages(self.chat_id)
        new_messages_found = False

        for msg_data in all_messages:
            msg_id = self.get_message_id(msg_data)
            
            if msg_id and msg_id not in self.rendered_message_ids:
                align = "sent" if msg_data['sender'] == self.current_user else "received"
                cached_data = self.message_cache.get(msg_id)
                
                self.add_message_to_display(align, msg_data, cached_data)
                
                self.rendered_message_ids.add(msg_id)
                new_messages_found = True
        
        if new_messages_found:
            QApplication.processEvents()
            self.chat_display.scrollToBottom()

    def handle_send_message_super(self):
        message_text = self.message_input.text() 
        if not message_text: return
        user_key, ok = QInputDialog.getText(self, "Kunci Super Enkripsi", "Masukkan Kunci (untuk Vigenere + White Mist):")
        if not (ok and user_key): return 
        self.message_input.clear()
        try:
            vigenere_encrypted_text = vigenere_encrypt(message_text, user_key)
            vigenere_encrypted_bytes = vigenere_encrypted_text.encode('utf-8')
            
            whitemist_encrypted_string = encrypt_whitemist(vigenere_encrypted_bytes, user_key, is_text=True)
            
            data_bytes_for_aes = whitemist_encrypted_string.encode('utf-8')
            encrypted_payload_bytes = self.session_crypto.encrypt(data_bytes_for_aes)
            metadata = { 
                'type': 'text', 
                'sender': self.current_user, 
                'recipient': self.recipient_username, 
                'data': encrypted_payload_bytes.decode('utf-8'), 
                'vigenere_key_debug': user_key,
                'db_timestamp': datetime.now(timezone.utc).astimezone().isoformat()
            }
            self.message_manager.save_message(self.chat_id, metadata)
            message_id = self.get_message_id(metadata)
            self.save_to_cache(message_id, message_text)
            self.refresh_chat_display()
            
        except Exception as e: 
            self.add_message_to_display("error", metadata=None, error_text=f"--- Error Super Enkripsi: {e} ---")

    # [BARU: HANDLER AUDIO ALIEN]
    def handle_attach_audio(self):
        """
        Handler untuk fitur Text-to-Audio (Alien Sound).
        Mengubah teks menjadi file WAV dengan frekuensi unik per karakter.
        """
        text, ok = QInputDialog.getText(self, "Kirim Pesan Audio", "Masukkan teks rahasia (akan diubah jadi Audio):")
        if not ok or not text: return
        
        key, ok_key = QInputDialog.getText(self, "Enkripsi", "Masukkan Kunci VIGENERE (untuk teks di dalam audio):")
        if not ok_key or not key: return
        
        loading_dialog = QDialog(self)
        loading_dialog.setWindowTitle("Processing Audio...")
        loading_dialog.setFixedSize(300, 100)
        l = QVBoxLayout(loading_dialog)
        status_label = QLabel("Mengenkripsi & Generate Audio...")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(status_label)
        loading_dialog.show()
        QApplication.processEvents()
        
        try:
            # 1. Enkripsi Teks (Vigenere -> WhiteMist)
            vigenere_ciphertext = vigenere_encrypt(text, key)
            whitemist_ciphertext = encrypt_whitemist(vigenere_ciphertext.encode('utf-8'), key, is_text=True)
            
            # 2. Generate Audio WAV
            temp_filename = f"audio_{uuid.uuid4().hex}.wav"
            temp_path = os.path.join(self.temp_audio_dir, temp_filename)
            
            success = text_to_alien_audio(whitemist_ciphertext, temp_path)
            if not success:
                raise Exception("Gagal membuat file audio.")
            
            # 3. Upload File WAV
            status_label.setText("Mengupload Audio...")
            QApplication.processEvents()
            
            with open(temp_path, 'rb') as f:
                upload_url = f"{self.api_url}/upload_file/{self.chat_id}"
                files = {'file': (temp_filename, f, 'audio/wav')}
                response = requests.post(upload_url, files=files, timeout=60)
                
            if response.status_code != 200 or not response.json().get("success"):
                raise Exception(f"Gagal upload: {response.text}")
            
            file_id = response.json().get('file_id')
            if not file_id:
                raise Exception("Server tidak mengembalikan file_id.")
            
            # 4. Kirim Pesan Metadata
            message_data = {
                "type": "audio_secret",
                "file_id": file_id,
                "sender": self.current_user,
                "recipient": self.recipient_username,
                "filename": temp_filename,
                "db_timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
                "text_key_debug": key  # Debug only
            }
            
            self.message_manager.save_message(self.chat_id, message_data)
            
            # Simpan pesan asli ke cache agar sender bisa melihat history-nya
            message_id = self.get_message_id(message_data)
            self.save_to_cache(message_id, text)

            loading_dialog.close()
            self.refresh_chat_display()
            
        except Exception as e:
            loading_dialog.close()
            self.add_message_to_display("error", metadata=None, error_text=f"--- Error Audio: {e} ---")

    # --- [FIX: PERBAIKAN ENKRIPSI STEGANO DENGAN HEADER] ---
    def handle_attach_image_stegano(self):
        message_to_hide = self.message_input.text()
        if not message_to_hide:
            QMessageBox.warning(self, "Error", "Tulis dulu pesan di kotak teks untuk disembunyikan ke gambar.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Gambar Pembawa (.png)", "", "Images (*.png)")
        if not file_path: return
        try:
            file_size = os.path.getsize(file_path)
            if file_size > self.MAX_FILE_SIZE:
                QMessageBox.warning(self, "File Terlalu Besar", f"Ukuran file ({file_size // 1024} KB) melebihi batas 2MB ({self.MAX_FILE_SIZE // 1024} KB).")
                return
        except OSError as e: QMessageBox.critical(self, "Error", f"Tidak dapat membaca file: {e}")
        
        text_key, ok = QInputDialog.getText(self, "Kunci Steganografi", "Masukkan Kunci VIGENERE untuk teks yang akan disembunyikan:")
        if not (ok and text_key): return
        
        if not os.path.exists(self.temp_stegano_dir): os.makedirs(self.temp_stegano_dir)
        base_filename = os.path.basename(file_path)
        temp_filename = os.path.join(self.temp_stegano_dir, f"stego_{uuid.uuid4()}.png") 
        
        try:
            # 1. Enkripsi Pesan (Vigenere)
            encrypted_text_raw = vigenere_encrypt(message_to_hide, text_key)
            
            # --- [FIX PENTING: BASE64 ENCODING] ---
            # Ubah karakter aneh Vigenere menjadi Base64 yang aman untuk Stegano
            safe_payload = base64.b64encode(encrypted_text_raw.encode('utf-8')).decode('utf-8')
            
            # 2. Buat Header Panjang
            msg_len = len(safe_payload)
            header = f"<LEN:{msg_len:010d}>"
            
            # 3. Gabungkan: Header + Base64 Payload + Delimiter
            payload_final = header + safe_payload + "|||END_MORSZ|||"
            # --------------------------------------
            
            # 4. Sembunyikan ke Gambar
            secret_image = lsb.hide(file_path, payload_final)
            secret_image.save(temp_filename)
            
            self.add_message_to_display("error", metadata=None, error_text=f"--- Mengunggah {base_filename}... ---")
            
            # Upload Logic (Sama seperti sebelumnya)
            with open(temp_filename, "rb") as f:
                files = {'file': (base_filename, f, 'image/png')}
                upload_url = f"{self.api_url}/upload_file/{self.chat_id}"
                response = requests.post(upload_url, files=files, timeout=30)
            
            if response.status_code != 200 or not response.json().get("success"):
                if response.status_code == 413: raise Exception(f"Gagal unggah: {response.json().get('message')}")
                raise Exception(f"Gagal mengunggah file: {response.json().get('message', 'Error tidak diketahui')}")
                
            file_id = response.json().get("file_id")
            metadata = { 
                'type': 'stegano', 
                'sender': self.current_user, 
                'recipient': self.recipient_username, 
                'data': None, 
                'file_id': file_id, 
                'filename': base_filename, 
                'text_key_debug': text_key, # Debugging help
                'db_timestamp': datetime.now(timezone.utc).astimezone().isoformat()
            }
            self.message_manager.save_message(self.chat_id, metadata)
            
            # Simpan ke cache lokal agar langsung tampil tanpa download ulang
            message_id = self.get_message_id(metadata)
            cached_stego_path = os.path.join(self.temp_stegano_dir, file_id)
            try:
                if not os.path.exists(cached_stego_path):
                    import shutil
                    shutil.copy(temp_filename, cached_stego_path)
            except: pass
            
            cache_data = {"text": message_to_hide, "image_path": cached_stego_path} 
            self.save_to_cache(message_id, cache_data)

            self.refresh_chat_display()
            self.message_input.clear()
            os.remove(temp_filename)
            
        except Exception as e:
            self.add_message_to_display("error", metadata=None, error_text=f"--- Error Steganografi/Upload: {e} ---")
            if os.path.exists(temp_filename): os.remove(temp_filename)
            
    def handle_attach_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih File Untuk Dienkripsi", "", "All Files (*.*)")
        if not file_path: return
        try:
            file_size = os.path.getsize(file_path)
            if file_size > self.MAX_FILE_SIZE:
                QMessageBox.warning(self, "File Terlalu Besar", f"Ukuran file ({file_size // 1024} KB) melebihi batas 2MB ({self.MAX_FILE_SIZE // 1024} KB).")
                return
        except OSError as e: QMessageBox.critical(self, "Error", f"Tidak dapat membaca file: {e}")
        methods = ["AES (Modern)", "White-Mist (Eksperimental)"]
        method, ok = QInputDialog.getItem(self, "Pilih Metode Enkripsi", "Metode:", methods, 0, False)
        if not ok: return
        key, ok = QInputDialog.getText(self, f"Kunci Enkripsi ({method})", f"Masukkan Kunci untuk {method}:", QLineEdit.Password)
        if not (ok and key): return
        try:
            with open(file_path, "rb") as f: data_bytes = f.read()
            filename = os.path.basename(file_path)
            encrypted_payload_bytes = None; metadata = {}
            if method == "AES (Modern)":
                temp_crypto = CryptoEngine(key); encrypted_payload_bytes = temp_crypto.encrypt(data_bytes)
                metadata = { 'type': 'file', 'sender': self.current_user, 'recipient': self.recipient_username, 'data': None, 'encryption_method': 'aes', 'aes_key_debug': key, 'filename': filename }
            elif method == "White-Mist (Eksperimental)":
                encrypted_string = encrypt_whitemist(data_bytes, key); encrypted_payload_bytes = encrypted_string.encode('utf-8')
                metadata = { 'type': 'file', 'sender': self.current_user, 'recipient': self.recipient_username, 'data': None, 'encryption_method': 'whitemist', 'aes_key_debug': key, 'filename': filename }
            else: return 
            
            self.add_message_to_display("error", metadata=None, error_text=f"--- Mengunggah {filename} ({method})... ---")
            
            files = {'file': (f"{filename}.enc", encrypted_payload_bytes, 'application/octet-stream')}
            upload_url = f"{self.api_url}/upload_file/{self.chat_id}"
            response = requests.post(upload_url, files=files, timeout=60)
            if response.status_code != 200 or not response.json().get("success"):
                if response.status_code == 413: raise Exception(f"Gagal unggah: {response.json().get('message')}")
                raise Exception(f"Gagal mengunggah file: {response.json().get('message', 'Error tidak diketahui')}")
            file_id = response.json().get("file_id")
            metadata['file_id'] = file_id 
            metadata['db_timestamp'] = datetime.now(timezone.utc).astimezone().isoformat()
            
            self.message_manager.save_message(self.chat_id, metadata)
            
            self.refresh_chat_display()
            
        except Exception as e: 
            self.add_message_to_display("error", metadata=None, error_text=f"--- Error File Encryption/Upload: {e} ---")

    def show_loading_dialog(self, filename):
        dialog = QDialog(self)
        dialog.setModal(True)
        dialog.setWindowTitle("Mengunduh...")
        dialog.setStyleSheet(f"background-color: {self.COLOR_BACKGROUND}; color: {self.COLOR_TEXT}; font-size: 14px;")
        layout = QVBoxLayout()
        label = QLabel(f"Sedang mengunduh file:\n{filename}\n\nHarap tunggu...")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.setFixedSize(300, 150)
        
        dialog.show()
        QApplication.processEvents() 
        return dialog

    def on_chat_item_clicked(self, item):
        metadata = item.data(Qt.UserRole)
        if not metadata: return
        
        msg_box = QMessageBox(self)
        msg_type = metadata.get('type')
        file_id = metadata.get('file_id')
        
        try:
            if msg_type == 'text':
                message_id = self.get_message_id(metadata)
                encrypted_data_b64 = metadata.get('data')
                if not encrypted_data_b64:
                    QMessageBox.information(self, "Info", "Pesan ini sudah dalam bentuk teks biasa.")
                    return
                encrypted_data_b64 = encrypted_data_b64.encode('utf-8')
                key, ok = QInputDialog.getText(self, "Dekripsi Teks", "Masukkan Kunci (White-Mist + Vigenere):")
                if ok and key:
                    decrypted_text = ""
                    try:
                        decrypted_bytes_from_aes = self.session_crypto.decrypt(encrypted_data_b64)
                        whitemist_encrypted_string = decrypted_bytes_from_aes.decode('utf-8')
                        try:
                            vigenere_encrypted_bytes = decrypt_whitemist(whitemist_encrypted_string, key, is_text=True)
                            vigenere_encrypted_text = vigenere_encrypted_bytes.decode('utf-8')
                        except Exception as e_whitemist:
                            print(f"Error WhiteMist/b64: {e_whitemist}")
                            vigenere_encrypted_text = whitemist_encrypted_string 
                        decrypted_text = vigenere_decrypt(vigenere_encrypted_text, key)
                    except Exception as e_aes:
                        print(f"Error AES: {e_aes}")
                        decrypted_text = f"[DEKRIPSI GAGAL: Data korup atau kunci sesi salah.]"
                    if message_id: 
                        self.save_to_cache(message_id, decrypted_text)
                    new_widget = self.create_chat_bubble("received" if metadata['sender'] != self.current_user else "sent", metadata, decrypted_text, item)
                    new_widget.layout().activate()
                    new_widget.adjustSize()
                    real_size = new_widget.size()
                    real_size.setHeight(real_size.height() + 10)
                    item.setSizeHint(real_size)
                    self.chat_display.setItemWidget(item, new_widget)

            elif msg_type == 'file' and file_id:
                local_encrypted_path = os.path.join(self.temp_download_dir, file_id)
                filename = metadata.get('filename', 'file.enc')
                if not os.path.exists(local_encrypted_path):
                    loading_dialog = self.show_loading_dialog(filename)
                    download_url = f"{self.api_url}/download_file/{self.chat_id}/{file_id}"
                    response = requests.get(download_url, timeout=60)
                    loading_dialog.close() 
                    if response.status_code != 200: raise Exception("Gagal mengunduh file dari server.")
                    with open(local_encrypted_path, "wb") as f: f.write(response.content)
                    self.add_message_to_display("error", metadata=None, error_text=f"--- Unduhan Selesai. Disimpan di cache. ---")
                else:
                    self.add_message_to_display("error", metadata=None, error_text=f"--- Membuka {filename} dari cache... ---")
                key, ok = QInputDialog.getText(self, "Dekripsi File", "Masukkan Kunci untuk file ini:", QLineEdit.Password)
                if not (ok and key): return
                with open(local_encrypted_path, "rb") as f: encrypted_bytes = f.read()
                decrypted_bytes = None; method = metadata.get('encryption_method', 'aes')
                if method == 'aes':
                    self.add_message_to_display("error", metadata=None, error_text=f"--- Mendekripsi (AES)... ---")
                    temp_crypto = CryptoEngine(key); decrypted_bytes = temp_crypto.decrypt(encrypted_bytes)
                elif method == 'whitemist':
                    self.add_message_to_display("error", metadata=None, error_text=f"--- Mendekripsi (White-Mist)... ---")
                    encrypted_string = encrypted_bytes.decode('utf-8'); 
                    decrypted_bytes = decrypt_whitemist(encrypted_string, key)
                else: raise ValueError(f"Metode enkripsi '{method}' tidak dikenal.")
                decrypted_path = os.path.join(self.temp_decrypted_dir, f"DECRYPTED_{filename}")
                with open(decrypted_path, "wb") as f: f.write(decrypted_bytes)
                msg_box.setWindowTitle("File Didekripsi"); msg_box.setText(f"File '{filename}' ({method}) berhasil didekripsi!")
                msg_box.setInformativeText(f"Disimpan di: {decrypted_path}"); msg_box.exec()

            # --- [FIX: PERBAIKAN DEKRIPSI STEGANO DENGAN HEADER] ---
            elif msg_type == 'stegano' and file_id:
                filename = metadata.get('filename', f"{file_id}.png")
                local_stegano_path = os.path.join(self.temp_stegano_dir, file_id) 
                
                # Download logic (sama)
                if not os.path.exists(local_stegano_path):
                    loading_dialog = self.show_loading_dialog(filename)
                    download_url = f"{self.api_url}/download_file/{self.chat_id}/{file_id}"
                    try:
                        response = requests.get(download_url, timeout=60)
                        loading_dialog.close() 
                        if response.status_code != 200: raise Exception("Gagal unduh gambar.")
                        with open(local_stegano_path, "wb") as f: f.write(response.content)
                    except:
                        loading_dialog.close(); raise
                
                msg_box.setWindowTitle("Pesan Gambar")
                pixmap = QPixmap(local_stegano_path).scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                msg_box.setIconPixmap(pixmap)
                msg_box.setText("Gambar Steganografi diterima.")
                decrypt_button = msg_box.addButton("Dekripsi Pesan", QMessageBox.AcceptRole)
                msg_box.addButton(QMessageBox.Close); msg_box.exec()
                
                if msg_box.clickedButton() == decrypt_button:
                    key, ok = QInputDialog.getText(self, "Dekripsi", "Masukkan Kunci VIGENERE:")
                    if ok and key:
                        try:
                            # 1. Ambil data mentah dari gambar
                            raw_revealed = lsb.reveal(local_stegano_path)
                            if not raw_revealed: raise ValueError("Gambar kosong/bukan stegano.")
                            
                            clean_payload = raw_revealed
                            
                            # 2. Parsing Header <LEN:...>
                            if raw_revealed.startswith("<LEN:") and len(raw_revealed) >= 16:
                                len_str = raw_revealed[5:15]
                                expected_len = int(len_str)
                                start_idx = 16
                                end_idx = 16 + expected_len
                                clean_payload = raw_revealed[start_idx:end_idx]
                            elif "|||END_MORSZ|||" in raw_revealed:
                                clean_payload = raw_revealed.split("|||END_MORSZ|||")[0]
                            
                            # --- [FIX PENTING: DECODE BASE64 DULU] ---
                            # Sebelum didekripsi Vigenere, kembalikan dari Base64
                            try:
                                # Coba decode base64. Jika gagal, mungkin format lama (langsung vigenere)
                                vigenere_ciphertext = base64.b64decode(clean_payload).decode('utf-8')
                            except Exception:
                                # Fallback untuk pesan lama yang belum pakai Base64
                                print("Gagal Base64 decode, mencoba raw text (legacy)...")
                                vigenere_ciphertext = clean_payload

                            # 3. Dekripsi Vigenere
                            decrypted_message = vigenere_decrypt(vigenere_ciphertext, key)
                            
                            # Simpan Cache & Tampilkan
                            message_id = self.get_message_id(metadata)
                            if message_id:
                                cache_data = {"text": decrypted_message, "image_path": local_stegano_path}
                                self.save_to_cache(message_id, cache_data)
                            
                            # --- [MODIFIKASI: Scrollable Dialog] ---
                            result_dialog = QDialog(self)
                            result_dialog.setWindowTitle("Pesan Tersembunyi")
                            result_dialog.resize(500, 400)
                            res_layout = QVBoxLayout(result_dialog)
                            
                            info_lbl = QLabel("Isi Pesan (Decrypted):")
                            info_lbl.setStyleSheet(f"color: {self.COLOR_GOLD}; font-weight: bold;")
                            res_layout.addWidget(info_lbl)
                            
                            text_area = QTextEdit()
                            text_area.setPlainText(decrypted_message)
                            text_area.setReadOnly(True)
                            text_area.setStyleSheet(f"background-color: {self.COLOR_PANE_LEFT}; color: {self.COLOR_TEXT}; border: 1px solid {self.COLOR_GOLD};")
                            res_layout.addWidget(text_area)
                            
                            close_btn = QPushButton("Tutup")
                            close_btn.setStyleSheet(self.button_style(base=self.COLOR_RED, hover=self.COLOR_RED_HOVER, pressed=self.COLOR_RED_PRESSED))
                            close_btn.clicked.connect(result_dialog.accept)
                            res_layout.addWidget(close_btn)
                            
                            result_dialog.exec()
                            # ---------------------------------------
                            
                            # Update UI Bubble
                            new_widget = self.create_chat_bubble("received" if metadata['sender'] != self.current_user else "sent", metadata, cache_data, item)
                            new_widget.layout().activate(); new_widget.adjustSize()
                            real_size = new_widget.size(); real_size.setHeight(real_size.height() + 10)
                            item.setSizeHint(real_size); self.chat_display.setItemWidget(item, new_widget)
                            
                        except Exception as e:
                            QMessageBox.critical(self, "Gagal Dekripsi", f"Error: {e}\nKey mungkin salah atau data korup.")

            # --- [BARU: Handle Audio Secret Click] ---
            elif msg_type == 'audio_secret' and file_id:
                filename = metadata.get('filename', f"{file_id}.wav")
                local_audio_path = os.path.join(self.temp_audio_dir, file_id)
                
                # Download jika belum ada
                if not os.path.exists(local_audio_path):
                    loading_dialog = self.show_loading_dialog(filename)
                    download_url = f"{self.api_url}/download_file/{self.chat_id}/{file_id}"
                    try:
                        response = requests.get(download_url, timeout=30)
                        if response.status_code == 200:
                            with open(local_audio_path, 'wb') as f:
                                f.write(response.content)
                        else:
                            loading_dialog.close()
                            QMessageBox.critical(self, "Error", f"Gagal download audio: {response.status_code}")
                            return
                    except Exception as e:
                        loading_dialog.close()
                        QMessageBox.critical(self, "Error", f"Error download: {e}")
                        return
                    loading_dialog.close()
                
                # Tampilkan opsi: Play atau Decrypt
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Pesan Audio (Alien)")
                msg_box.setText("Pilih aksi untuk pesan audio ini:")
                play_btn = msg_box.addButton("🔊 Play Audio", QMessageBox.ActionRole)
                decrypt_btn = msg_box.addButton("🔐 Dekripsi Pesan", QMessageBox.ActionRole)
                msg_box.addButton(QMessageBox.Cancel)
                msg_box.exec()
                
                if msg_box.clickedButton() == play_btn:
                    try:
                        winsound.PlaySound(local_audio_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Gagal memutar audio: {e}")
                        
                elif msg_box.clickedButton() == decrypt_btn:
                    key, ok = QInputDialog.getText(self, "Dekripsi Audio", "Masukkan Kunci VIGENERE:")
                    if not ok or not key:
                        return
                    
                    try:
                        # 1. Decode audio -> encrypted text
                        encrypted_text = alien_audio_to_text(local_audio_path)
                        if not encrypted_text:
                            raise Exception("Gagal decode audio menjadi text. File mungkin korup atau bukan audio alien.")
                        
                        # 2. Decrypt White-Mist
                        whitemist_decrypted_bytes = decrypt_whitemist(encrypted_text, key)
                        vigenere_ciphertext = whitemist_decrypted_bytes.decode('utf-8')
                        
                        # 3. Decrypt Vigenere
                        decrypted_message = vigenere_decrypt(vigenere_ciphertext, key)
                        
                        # Tampilkan hasil
                        result_dialog = QDialog(self)
                        result_dialog.setWindowTitle("Pesan Audio Terdekripsi")
                        result_dialog.setMinimumSize(500, 400)
                        result_dialog.setStyleSheet(f"background-color: {self.COLOR_BACKGROUND}; color: {self.COLOR_TEXT};")
                        
                        layout = QVBoxLayout(result_dialog)
                        layout.addWidget(QLabel("Isi Pesan:"))
                        text_edit = QTextEdit()
                        text_edit.setPlainText(decrypted_message)
                        text_edit.setReadOnly(True)
                        text_edit.setStyleSheet(f"""
                            QTextEdit {{
                                background-color: {self.COLOR_PANE_LEFT};
                                color: {self.COLOR_TEXT};
                                border: 2px solid {self.COLOR_GOLD};
                                border-radius: 8px;
                                padding: 10px;
                                font-size: 14px;
                            }}
                        """)
                        layout.addWidget(text_edit)
                        
                        close_btn = QPushButton("Tutup")
                        close_btn.clicked.connect(result_dialog.close)
                        close_btn.setStyleSheet(self.button_style(
                            base=self.COLOR_GOLD, hover=self.COLOR_GOLD_HOVER, 
                            pressed=self.COLOR_GOLD_PRESSED, radius=10, text_color=self.COLOR_PANE_LEFT
                        ))
                        layout.addWidget(close_btn)
                        
                        # Cache hasil dekripsi
                        message_id = self.get_message_id(metadata)
                        self.save_to_cache(message_id, decrypted_message)
                        
                        result_dialog.exec()
                        
                        # Update bubble
                        new_widget = self.create_chat_bubble("received" if metadata['sender'] != self.current_user else "sent", metadata, decrypted_message, item)
                        new_widget.layout().activate()
                        new_widget.adjustSize()
                        real_size = new_widget.size()
                        real_size.setHeight(real_size.height() + 10)
                        item.setSizeHint(real_size)
                        self.chat_display.setItemWidget(item, new_widget)
                        
                    except Exception as e:
                        QMessageBox.critical(self, "Gagal Dekripsi", f"Error: {e}\nKey mungkin salah atau data korup.")

        except Exception as e:
            print(f"Error di on_chat_item_clicked: {e}")
            debug_key = metadata.get('aes_key_debug') or metadata.get('text_key_debug', 'TIDAK DIKETAHUI')
            QMessageBox.critical(self, "Error Dekripsi", f"Terjadi error: {e}\n\n(Debug: Kunci yg benar mungkin '{debug_key}')")

    def create_chat_bubble(self, align, metadata, cached_data=None, item=None):
        bubble_container = QWidget()
        container_layout = QHBoxLayout(bubble_container)
        container_layout.setContentsMargins(5, 5, 5, 5)
        container_layout.setSpacing(0)

        bubble_frame = QFrame()
        bubble_frame.setFrameShape(QFrame.Shape.StyledPanel)
        bubble_frame.setFrameShadow(QFrame.Shadow.Plain)
        bubble_frame.setLineWidth(0)
        
        bubble_frame.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        bubble_frame.setMinimumWidth(self.width() * 0.3)
        bubble_frame.setMaximumWidth(self.width() * 0.7)

        bubble_content_layout = QVBoxLayout(bubble_frame)
        bubble_content_layout.setContentsMargins(12, 10, 12, 8)
        bubble_content_layout.setSpacing(8)
        
        msg_type = metadata.get('type', 'unknown')
        content_max_width = (self.width() * 0.7) - 24
        
        # --- SENDER NAME ---
        if align == "sent":
            name_label = QLabel("YOU")
            name_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
            name_label.setStyleSheet(f"color: {self.COLOR_GOLD};")
            bubble_content_layout.addWidget(name_label)
        elif align == "received":
            prefix = metadata.get('sender', 'Unknown')
            name_label = QLabel(prefix)
            name_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
            name_label.setStyleSheet(f"color: {self.COLOR_GOLD};")
            bubble_content_layout.addWidget(name_label)
        
        # --- CONTENT ---
        if msg_type == 'text':
            display_text = cached_data if cached_data else "[Pesan Teks Super-Terenkripsi]"
            content_label = QLabel(display_text)
            content_label.setWordWrap(True)
            content_label.setMaximumWidth(content_max_width)
            content_label.setStyleSheet(f"color: {self.COLOR_TEXT}; font-size: 14px;")
            content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            content_label.setMinimumHeight(30)
            bubble_content_layout.addWidget(content_label)

        elif msg_type == 'stegano':
            filename = metadata.get('filename', 'unknown.png')
            if cached_data and isinstance(cached_data, dict):
                secret_text = cached_data.get('text', '[ERROR CACHE]')
                image_path = cached_data.get('image_path')
                
                if image_path and os.path.exists(image_path):
                    pixmap = QPixmap(image_path).scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    img_label = QLabel()
                    img_label.setPixmap(pixmap)
                    img_label.setMinimumSize(200, 150)
                    bubble_content_layout.addWidget(img_label)
                else:
                    stegano_label = QLabel(f"🖼️ Stegano: {filename}")
                    stegano_label.setMaximumWidth(content_max_width)
                    stegano_label.setWordWrap(True)
                    bubble_content_layout.addWidget(stegano_label)
                
                text_label = QLabel(f"Pesan: {secret_text}")
                text_label.setWordWrap(True)
                text_label.setMaximumWidth(content_max_width)
                text_label.setStyleSheet(f"color: {self.COLOR_TEXT}; font-size: 14px; font-style: italic;")
                text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                text_label.setMinimumHeight(30)
                bubble_content_layout.addWidget(text_label)
            else:
                content_label = QLabel(f"🖼️ Stegano Image: {filename}")
                content_label.setWordWrap(True)
                content_label.setMaximumWidth(content_max_width)
                content_label.setStyleSheet(f"color: {self.COLOR_TEXT_SUBTLE}; font-size: 14px; font-style: italic;")
                content_label.setMinimumHeight(30)
                bubble_content_layout.addWidget(content_label)

        elif msg_type == 'file':
            filename = metadata.get('filename', 'unknown_file')
            method = metadata.get('encryption_method', 'aes').upper()
            content_label = QLabel(f"📂 File ({method}): {filename}")
            content_label.setWordWrap(True)
            content_label.setMaximumWidth(content_max_width)
            content_label.setStyleSheet(f"color: {self.COLOR_TEXT_SUBTLE}; font-size: 14px; font-style: italic;")
            content_label.setMinimumHeight(30)
            bubble_content_layout.addWidget(content_label)
        
        # [BARU: BUBBLE AUDIO ALIEN]
        elif msg_type == 'audio_secret':
            icon_lbl = QLabel("📡")
            icon_lbl.setFont(QFont("Segoe UI", 24))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bubble_content_layout.addWidget(icon_lbl)
            
            lbl = QLabel("Pesan Suara (Alien)")
            lbl.setStyleSheet("font-weight: bold; font-style: italic;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bubble_content_layout.addWidget(lbl)

            if cached_data:
                # Jika sudah didekripsi/cache, tampilkan teksnya juga
                decrypted_lbl = QLabel(f'"{cached_data}"')
                decrypted_lbl.setWordWrap(True)
                decrypted_lbl.setStyleSheet(f"color: {self.COLOR_TEXT}; font-style: italic; margin-top: 5px;")
                decrypted_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                bubble_content_layout.addWidget(decrypted_lbl)
            
            hint = QLabel("(Klik untuk Putar/Dekripsi)")
            hint.setStyleSheet(f"color: {self.COLOR_TEXT_SUBTLE}; font-size: 10px;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bubble_content_layout.addWidget(hint)
        # ---------------------------

        else:
            content_label = QLabel("[Pesan tidak dikenal]")
            content_label.setMaximumWidth(content_max_width)
            content_label.setStyleSheet(f"color: {self.COLOR_RED}; font-size: 14px;")
            content_label.setMinimumHeight(30)
            bubble_content_layout.addWidget(content_label)
        
        # --- FOOTER (Time & Refresh) ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 5, 0, 0)
        
        timestamp_str = "..."
        timestamp_iso = metadata.get('db_timestamp')
        if timestamp_iso:
            try:
                dt_obj = datetime.fromisoformat(timestamp_iso)
                if dt_obj.tzinfo is None:
                    dt_obj = dt_obj.replace(tzinfo=timezone.utc)
                dt_local = dt_obj.astimezone()
                timestamp_str = dt_local.strftime("%H:%M") 
            except ValueError:
                timestamp_str = "err"
        
        time_label = QLabel(timestamp_str)
        time_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        time_label.setStyleSheet(f"color: {self.COLOR_TEXT_SUBTLE}; font-size: 10px; padding-top: 5px;")
        
        refresh_btn = QPushButton("🔄") 
        refresh_btn.setFixedSize(25, 25)
        refresh_btn.setToolTip("Dekripsi ulang pesan ini")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; border: none; color: {self.COLOR_TEXT_SUBTLE}; font-size: 14px; }}
            QPushButton:hover {{ color: {self.COLOR_GOLD_HOVER}; }}
        """)
        
        if item:
            refresh_btn.clicked.connect(lambda: self.on_chat_item_clicked(item))
            
        bottom_layout.addWidget(time_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(refresh_btn)
        
        bubble_content_layout.addLayout(bottom_layout)
        
        if align == "sent":
            bubble_frame.setStyleSheet(f"QFrame {{ background-color: {self.COLOR_BUBBLE_SENT}; border-radius: 12px; border-bottom-right-radius: 0px; }}")
            container_layout.addStretch()
            container_layout.addWidget(bubble_frame)
        else: # received
            bubble_frame.setStyleSheet(f"QFrame {{ background-color: {self.COLOR_BUBBLE_RECV}; border-radius: 12px; border-bottom-left-radius: 0px; }}")
            container_layout.addWidget(bubble_frame)
            container_layout.addStretch()

        return bubble_container

    def add_message_to_display(self, align, metadata, cached_data=None, error_text=None, is_loading_history=False):
        
        item = QListWidgetItem() 
        item.setData(Qt.UserRole, metadata)
        
        if error_text:
            item.setText(error_text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(self.COLOR_RED))
            item.setSizeHint(QSize(0, 30))
            self.chat_display.addItem(item)
        else:
            bubble_widget = self.create_chat_bubble(align, metadata, cached_data, item)
            
            bubble_widget.layout().activate() 
            bubble_widget.adjustSize()
            
            real_size = bubble_widget.size()
            real_size.setHeight(real_size.height() + 10) 
            
            item.setSizeHint(real_size) 
            self.chat_display.addItem(item)
            self.chat_display.setItemWidget(item, bubble_widget)

    # --- Helper Styling ---
    def input_style(self):
        return f"""
            QLineEdit {{
                background-color: {self.COLOR_CARD};
                border: 2px solid {self.COLOR_GOLD};
                border-radius: 22px;
                padding: 10px 20px;
                color: {self.COLOR_TEXT};
                font-size: 14px;
                min-height: 25px; 
            }}
            QLineEdit:focus {{ border-color: {self.COLOR_GOLD_HOVER}; }}
        """

    def button_style(self, base, hover, pressed, radius=12, text_color=None):
        text_col = text_color if text_color else self.COLOR_TEXT
        return f"""
            QPushButton {{
                background-color: {base}; color: {text_col};
                border: none; border-radius: {radius}px;
                padding: 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
            QPushButton:pressed {{ background-color: {pressed}; }}
        """