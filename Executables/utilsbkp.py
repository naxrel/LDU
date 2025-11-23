import os
import sys
from hashlib import pbkdf2_hmac
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import base64  # <-- [BARU] Diperlukan untuk White-Mist
import hashlib
import json
import requests
import threading
from stegano import lsb
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend

# --- [BARU] Impor White-Mist ---
# (Asumsi file WhiteMist.py ada di direktori yang sama)
try:
    import crossCross
except ImportError:
    print("PERINGATAN: Modul WhiteMist tidak ditemukan. Fitur enkripsi White-Mist tidak akan berfungsi.")
    crossCross = None # Hindari crash jika file tidak ada

# --- FUNGSI HELPER PATH (.EXE) ---
# (Tidak berubah)
def get_base_path():
    # ... (kode tidak berubah)
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_resource_path(relative_path):
    # ... (kode tidak berubah)
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

# --- FUNGSI HASH PASSWORD ---
# (Tidak berubah)
def hash_password(password):
    # ... (kode tidak berubah)
    salt = os.urandom(16)
    hashed_password = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex(), hashed_password.hex()

def verify_password(stored_salt_hex, stored_hash_hex, password_to_check):
    # ... (kode tidak berubah)
    try:
        stored_salt = bytes.fromhex(stored_salt_hex)
        stored_hash = bytes.fromhex(stored_hash_hex)
        check_hash = hashlib.pbkdf2_hmac('sha256', password_to_check.encode('utf-8'), stored_salt, 100000)
        return check_hash == stored_hash
    except (ValueError, TypeError):
        return False

# --- [ LOGIKA API KLIEN ] ---
API_BASE_URL = "https://morsz.azeroth.site/" 

# --- MANAJEMEN USER (Tidak berubah) ---
class UserManager:
    # ... (kode tidak berubah)
    def __init__(self):
        self.api_url = API_BASE_URL
        print("UserManager (API Mode) diinisialisasi.")

    def register_user(self, username, password):
        # ... (kode tidak berubah)
        salt_hex, hash_hex = hash_password(password)
        payload = { "username": username, "salt_hex": salt_hex, "hash_hex": hash_hex }
        try:
            response = requests.post(f"{self.api_url}/register", json=payload, timeout=10)
            if response.status_code == 200:
                return True, response.json().get("message", "Akun berhasil dibuat!")
            else:
                return False, response.json().get("message", "Username sudah ada.")
        except requests.exceptions.RequestException as e:
            return False, f"Koneksi ke server gagal: {e}"

    def verify_user(self, username, password):
        # ... (kode tidak berubah)
        try:
            response = requests.post(f"{self.api_url}/login", json={"username": username}, timeout=10)
            if response.status_code != 200: return False 
            data = response.json()
            stored_salt_hex = data['salt_hex']
            stored_hash_hex = data['hash_hex']
            return verify_password(stored_salt_hex, stored_hash_hex, password)
        except requests.exceptions.RequestException as e:
            print(f"Verifikasi gagal: Tidak bisa terhubung ke server. {e}")
            return False
        except Exception as e:
            print(f"Error verifikasi: {e}")
            return False
            
    def get_contacts(self, username):
        # ... (kode tidak berubah)
        try:
            response = requests.get(f"{self.api_url}/get_chats/{username}", timeout=10)
            if response.status_code == 200 and response.json().get("success"):
                return True, response.json().get("contacts", [])
            else:
                print(f"Gagal mengambil kontak: {response.json().get('message')}")
                return False, []
        except requests.exceptions.RequestException as e:
            print(f"Koneksi error ambil kontak: {e}")
            return False, []

# --- MANAJEMEN PESAN (Tidak berubah) ---
class MessageManager:
    # ... (kode tidak berubah)
    def __init__(self):
        self.api_url = API_BASE_URL
        print("MessageManager (API Mode) diinisialisasi.")

    def get_chat_id(self, user1, user2):
        users = sorted([user1, user2])
        return f"{users[0]}_{users[1]}"

    def load_messages(self, chat_id):
        # ... (kode tidak berubah)
        try:
            response = requests.get(f"{self.api_url}/load_messages/{chat_id}", timeout=10)
            if response.status_code == 200:
                return response.json() 
            else:
                return []
        except requests.exceptions.RequestException:
            print("Gagal memuat pesan dari server.")
            return [] 

    def save_message(self, chat_id, message_data):
        # ... (kode tidak berubah)
        message_data_copy = message_data.copy() # [REVISI] Salin data agar tidak merusak metadata lokal
        message_data_copy['chat_id'] = chat_id
        if message_data_copy.get('type') in ['stegano', 'file']:
             message_data_copy['data'] = None
        # Hapus timestamp sisi klien, server akan menambahkannya
        if 'db_timestamp' in message_data_copy:
            del message_data_copy['db_timestamp']
            
        try:
            def send_in_thread():
                try:
                    requests.post(f"{self.api_url}/save_message", json=message_data_copy, timeout=10)
                    print("Pesan (metadata) berhasil dikirim ke server.")
                except requests.exceptions.RequestException as e:
                    print(f"Gagal mengirim pesan: {e}")
            threading.Thread(target=send_in_thread, daemon=True).start()
        except Exception as e:
            print(f"Error memulai thread kirim pesan: {e}")

# --- FUNGSI VIGENERE (Tidak berubah) ---
def vigenere_encrypt(plain_text, key):
    # ... (kode tidak berubah)
    if not key: key = "defaultkey"
    payload = {"text": plain_text, "key": key}
    try:
        response = requests.post(f"{API_BASE_URL}/encrypt/vigenere", json=payload, timeout=5)
        if response.status_code == 200:
            return response.json().get("result", plain_text)
        else:
            print(f"Server error Vigenere Encrypt: {response.status_code}")
            return plain_text 
    except requests.exceptions.RequestException as e:
        print(f"Koneksi error Vigenere Encrypt: {e}")
        return plain_text 

def vigenere_decrypt(encrypted_text, key):
    # ... (kode tidak berubah)
    if not key: key = "defaultkey"
    payload = {"text": encrypted_text, "key": key}
    try:
        response = requests.post(f"{API_BASE_URL}/decrypt/vigenere", json=payload, timeout=5)
        if response.status_code == 200:
            return response.json().get("result", encrypted_text)
        else:
            print(f"Server error Vigenere Decrypt: {response.status_code}")
            return encrypted_text
    except requests.exceptions.RequestException as e:
        print(f"Koneksi error Vigenere Decrypt: {e}")
        return encrypted_text 

# --- CRYPTO ENGINE (Modern - AES) ---
# (Tidak berubah)
class CryptoEngine:
    # ... (kode tidak berubah)
    def __init__(self, password: str):
        self.password = password.encode('utf-8')
    def _derive_key(self, salt: bytes) -> bytes:
        kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1, backend=default_backend())
        return kdf.derive(self.password)
    def encrypt(self, data: bytes) -> bytes:
        salt = os.urandom(16); key = self._derive_key(salt)
        aesgcm = AESGCM(key); nonce = os.urandom(12)
        encrypted_data = aesgcm.encrypt(nonce, data, None)
        return base64.b64encode(salt + nonce + encrypted_data) 
    def decrypt(self, combined_payload_b64: bytes) -> bytes:
        try:
            combined_payload = base64.b64decode(combined_payload_b64)
            salt = combined_payload[:16]; nonce = combined_payload[16:28]
            encrypted_data = combined_payload[28:]
            key = self._derive_key(salt)
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(nonce, encrypted_data, None)
        except Exception as e:
            print(f"CryptoEngine Gagal Dekripsi: {e}")
            raise ValueError("Gagal mendekripsi data: Password salah atau data korup.")

# --- [INSTRUKSI 1: FUNGSI HELPER WHITE-MIST] ---
def encrypt_whitemist(data_bytes: bytes, key: str, is_text: bool = False) -> str:
    """
    Enkripsi bytes menggunakan White-Mist.
    Jika is_text=True, data (vigenere) di-encode utf-8 dan dienkripsi.
    Jika is_text=False (default, untuk file), data di-encode base64 dan dienkripsi.
    """
    if crossCross is None:
        raise ImportError("Modul WhiteMist tidak ditemukan. Tidak bisa enkripsi.")
        
    string_to_encrypt = ""
    if is_text:
        # INSTRUKSI 1: Untuk Teks, langsung encode vigenere (bytes) -> utf-8
        string_to_encrypt = data_bytes.decode('utf-8')
    else:
        # Default (File): Ubah bytes mentah menjadi string base64
        string_to_encrypt = base64.b64encode(data_bytes).decode('utf-8')
    
    # Enkripsi string
    enkripsi = crossCross.state(key=key, salt="Kriptoasik", sugar="FunKripto")
    encrypted_string = enkripsi.letsEncrypt(string_to_encrypt)
    
    return encrypted_string

def decrypt_whitemist(encrypted_string: str, key: str, is_text: bool = False) -> bytes:
    """
    Dekripsi string White-Mist kembali menjadi bytes.
    Jika is_text=True, data didekripsi dan di-encode utf-8 (untuk vigenere).
    Jika is_text=False (default, untuk file), data didekripsi dan di-decode base64.
    """
    if crossCross is None:
        raise ImportError("Modul WhiteMist tidak ditemukan. Tidak bisa dekripsi.")
        
    # 1. Dekripsi string White-Mist
    dekripsi = crossCross.deState(key=key, salt="Kriptoasik", sugar="FunKripto")
    decrypted_string = dekripsi.letsDecrypt(encrypted_string)
    
    # 2. Kembalikan ke bytes
    if is_text:
        # INSTRUKSI 1: Untuk Teks, string dekripsi (vigenere) -> utf-8 bytes
        return decrypted_string.encode('utf-8')
    else:
        # Default (File): Ubah kembali string base64 menjadi bytes
        try:
            decrypted_bytes = base64.b64decode(decrypted_string.encode('utf-8'))
            return decrypted_bytes
        except Exception as e:
            print(f"Error b64decode White-Mist: {e}")
            # [PERBAIKAN] Jika gagal decode B64, mungkin ini adalah teks (instruksi 1)
            # Kembalikan saja sebagai bytes utf-8
            print("Gagal B64Decode, mencoba fallback ke UTF-8 (mungkin pesan teks lama)...")
            return decrypted_string.encode('utf-8')


# --- KONFIGURASI KUNCI USB ---
# (Tidak berubah)
HARDCODED_SECRET = "ini-adalah-kunci-rahasia-saya-yang-sangat-panjang-12345"
# ... (sisa kode tidak berubah)
SALT_SIZE = 16
KEY_SIZE = 32
ITERATIONS = 100000
HASH_ALG = "sha256"

def encrypt_config(plain_text_key, password):
    # ... (kode tidak berubah)
    salt = get_random_bytes(SALT_SIZE)
    key = pbkdf2_hmac(HASH_ALG, password.encode("utf-8"), salt, ITERATIONS, KEY_SIZE)
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(plain_text_key.encode("utf-8"))
    encrypted_data = {
        "salt": salt.hex(), "nonce": cipher.nonce.hex(),
        "tag": tag.hex(), "ciphertext": ciphertext.hex(),
    }
    return json.dumps(encrypted_data).encode("utf-8")

def decrypt_config(encrypted_data_bytes, password):
    # ... (kode tidak berubah)
    try:
        encrypted_data = json.loads(encrypted_data_bytes.decode("utf-8"))
        salt = bytes.fromhex(encrypted_data["salt"])
        nonce = bytes.fromhex(encrypted_data["nonce"])
        tag = bytes.fromhex(encrypted_data["tag"])
        ciphertext = bytes.fromhex(encrypted_data["ciphertext"])
        key = pbkdf2_hmac(HASH_ALG, password.encode("utf-8"), salt, ITERATIONS, KEY_SIZE)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plain_text_bytes = cipher.decrypt_and_verify(ciphertext, tag)
        return plain_text_bytes.decode("utf-8")
    except Exception as e:
        print(f"Gagal dekripsi config: {e}")
        return None

# --- [FITUR BARU: TEXT-TO-AUDIO (ALIEN SOUND)] ---
def text_to_alien_audio(text: str, output_path: str):
    """
    Mengubah teks menjadi file audio WAV (Alien Sound).
    Setiap karakter diubah menjadi nada frekuensi unik.
    Format: WAV, Mono, 44100Hz.
    """
    sample_rate = 44100
    duration_per_char = 0.08  # Detik per karakter
    amplitude = 16000         # Volume (max 32767)
    
    # Base frequency dan step
    base_freq = 300
    step_freq = 30 
    
    try:
        with wave.open(output_path, 'w') as wav_file:
            # Konfigurasi: 1 channel (mono), 2 bytes per sample (16-bit), 44100Hz
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            
            all_samples = bytearray()
            
            for char in text:
                # Mapping Karakter -> Frekuensi
                # Gunakan ord(char) untuk mendapatkan nilai ASCII/Unicode
                # Tambahkan sedikit random noise agar terdengar lebih "Alien" tapi tetap bisa didecode
                # (Noise tidak boleh mengubah frekuensi dominan terlalu jauh)
                
                char_code = ord(char)
                freq = base_freq + (char_code * step_freq)
                
                # Generate samples untuk durasi tertentu
                num_samples = int(sample_rate * duration_per_char)
                
                for i in range(num_samples):
                    t = float(i) / sample_rate
                    # Gelombang Sine Murni
                    value = int(amplitude * math.sin(2 * math.pi * freq * t))
                    
                    # Packing ke 16-bit integer little-endian
                    data = struct.pack('<h', value)
                    all_samples.extend(data)
            
            wav_file.writeframes(all_samples)
        return True
    except Exception as e:
        print(f"Error generate audio: {e}")
        return False

def alien_audio_to_text(input_path: str) -> str:
    """
    Menerjemahkan kembali file audio Alien menjadi teks.
    Menggunakan analisis Zero-Crossing sederhana untuk mendeteksi frekuensi.
    """
    try:
        with wave.open(input_path, 'r') as wav_file:
            sample_rate = wav_file.getframerate()
            n_frames = wav_file.getnframes()
            raw_data = wav_file.readframes(n_frames)
            
            # Konversi bytes ke list of integers (16-bit signed)
            # Format '<h' berarti little-endian short (2 bytes)
            num_samples = len(raw_data) // 2
            samples = struct.unpack(f'<{num_samples}h', raw_data)
            
            duration_per_char = 0.08
            samples_per_char = int(sample_rate * duration_per_char)
            
            decoded_text = ""
            
            base_freq = 300
            step_freq = 30
            
            # Proses per chunk (per karakter)
            for i in range(0, len(samples), samples_per_char):
                chunk = samples[i:i+samples_per_char]
                if len(chunk) < samples_per_char // 2: break # Abaikan sisa chunk kecil
                
                # Hitung Zero Crossings untuk estimasi frekuensi
                zero_crossings = 0
                for j in range(1, len(chunk)):
                    if (chunk[j-1] > 0 and chunk[j] <= 0) or (chunk[j-1] < 0 and chunk[j] >= 0):
                        zero_crossings += 1
                
                # Frekuensi = (Zero Crossings * Sample Rate) / (2 * Jumlah Sample)
                # Karena kita hitung dalam chunk, Jumlah Sample = len(chunk)
                # Tapi rumus umum: Freq = (ZC / 2) / Duration
                chunk_duration = len(chunk) / sample_rate
                estimated_freq = (zero_crossings / 2) / chunk_duration
                
                # Mapping balik Frekuensi -> Karakter
                # Freq = Base + (Char * Step)  =>  Char = (Freq - Base) / Step
                # Gunakan round() karena estimasi tidak sempurna
                char_code = round((estimated_freq - base_freq) / step_freq)
                
                # Validasi range karakter yang masuk akal
                if 0 <= char_code <= 65535: # Unicode range
                    decoded_text += chr(int(char_code))
                else:
                    decoded_text += "?" # Karakter tidak valid/noise
                    
            return decoded_text
            
    except Exception as e:
        print(f"Error decode audio: {e}")
        return ""