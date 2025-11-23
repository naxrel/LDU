# loginpage.py (Versi Final dengan Login Wajah DAN Delay Login Password 3 Detik)
import os
import cv2
import io
import requests
import time
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, 
    QPushButton, QMessageBox, QDialog
)
from PySide6.QtGui import QFont, QImage, QPixmap
from PySide6.QtCore import Qt, QThread, QObject, Signal, Slot

# --- Konstanta Global untuk Biometrik ---
CASCADE_PATH = "fm/haarcascade_frontalface_default.xml"
API_URL = "https://morsz.azeroth.site" # Ganti dengan URL server Anda

#
# --- [DARI CONTOH] Class Worker untuk Login Wajah ---
#
class FaceLoginWorker(QObject):
    """
    Menjalankan pengambilan wajah dan otentikasi jaringan di thread terpisah.
    """
    frame_updated = Signal(QImage)
    status_updated = Signal(str)
    login_success = Signal(str) # Mengirimkan username jika sukses
    login_failed = Signal(str)  # Mengirimkan pesan error jika gagal
    finished = Signal()
    
    def __init__(self, camera_index=0):
        super().__init__()
        self.camera_index = camera_index
        self._is_running = True

    @Slot()
    def run(self):
        # ... (Logika FaceLoginWorker run() tetap sama, tidak diubah) ...
        try:
            if not os.path.exists(CASCADE_PATH):
                raise FileNotFoundError(f"Haar cascade not found at {CASCADE_PATH}")

            face_detector = cv2.CascadeClassifier(CASCADE_PATH)
            
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                raise IOError(f"Cannot open webcam at index {self.camera_index}.")

            start_time = time.time()
            captured_frame = None
            
            while time.time() - start_time < 10.0 and self._is_running:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_flipped = cv2.flip(frame, 1)
                gray = cv2.cvtColor(frame_flipped, cv2.COLOR_BGR2GRAY)
                faces = face_detector.detectMultiScale(gray, 1.3, 5)

                status_text = "Looking for face..."

                if len(faces) > 0:
                    (x, y, w, h) = faces[0]
                    cv2.rectangle(frame_flipped, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    status_text = "Face found... Authenticating..."
                    captured_frame = cv2.flip(frame_flipped, 1) # Un-flip
                
                rgb_image = cv2.cvtColor(frame_flipped, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                
                self.frame_updated.emit(qt_image)
                self.status_updated.emit(status_text)
                
                if captured_frame is not None:
                    break
                
                time.sleep(0.05)

            cap.release()

            if not self._is_running:
                self.login_failed.emit("Login canceled by user.")
                self.finished.emit()
                return

            if captured_frame is None:
                raise Exception("No face detected. Please try again.")

            self.status_updated.emit("Authenticating with server...")
            is_success, buffer = cv2.imencode(".jpg", captured_frame)
            if not is_success:
                raise Exception("Failed to encode image.")

            image_bytes = io.BytesIO(buffer.tobytes())
            
            files = {'file': ('login_image.jpg', image_bytes, 'image/jpeg')}
            response = requests.post(f"{API_URL}/login-face", files=files, timeout=30)

            result = response.json()
            if response.status_code == 200 and result.get("success"):
                self.login_success.emit(result.get("username"))
            else:
                self.login_failed.emit(result.get("message", "Unknown error"))

        except Exception as e:
            self.login_failed.emit(f"Error: {e}")
        finally:
            if 'cap' in locals() and cap.isOpened():
                cap.release()
            self.finished.emit()

    def stop(self):
        self._is_running = False

#
# --- [BARU] Class Worker untuk Login Password (Dengan Delay 3 Detik) ---
#
class PasswordLoginWorker(QObject):
    """
    Menjalankan verifikasi password di thread terpisah dengan delay minimal 3 detik.
    """
    login_success = Signal(str) # Mengirimkan username jika sukses
    login_failed = Signal(str)  # Mengirimkan pesan error jika gagal
    finished = Signal()
    
    def __init__(self, user_manager, username, password):
        super().__init__()
        self.user_manager = user_manager
        self.username = username
        self.password = password

    @Slot()
    def run(self):
        start_time = time.time()
        try:
            # Panggil fungsi verifikasi (asumsi return boolean)
            is_valid = self.user_manager.verify_user(self.username, self.password)
            
            # Hitung sisa waktu delay
            elapsed = time.time() - start_time
            if elapsed < 3.0:
                time.sleep(3.0 - elapsed) # Tahan thread ini (bukan GUI)
                
            # Kirim sinyal berdasarkan hasil
            if is_valid:
                self.login_success.emit(self.username)
            else:
                self.login_failed.emit("Username atau password salah.") # Pesan default
                
        except Exception as e:
            # Tangani error koneksi/lainnya
            elapsed = time.time() - start_time
            if elapsed < 3.0:
                time.sleep(3.0 - elapsed) # Tetap delay 3 detik
            self.login_failed.emit(f"Gagal terhubung ke server: {e}")
        finally:
            self.finished.emit()

#
# --- [DARI CONTOH] Class Dialog Pop-up untuk Login Wajah ---
#
class FaceLoginDialog(QDialog):
    # ... (Class FaceLoginDialog tetap sama, tidak diubah) ...
    """
    Ini adalah jendela pop-up baru yang menampilkan feed webcam.
    """
    login_success = Signal(str)
    
    def __init__(self, camera_index, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        
        self.thread = None
        self.worker = None

        self.setWindowTitle("Login with Face")
        self.setModal(True)
        self.setMinimumSize(640, 550)
        
        self.video_label = QLabel("Starting camera...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; border-radius: 10px;")
        self.video_label.setFixedSize(600, 450)

        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.video_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        layout.addWidget(self.cancel_button)
        
        self.apply_styles()
        
    def apply_styles(self):
        """
        [MODIFIKASI] Menggunakan palet warna dari LoginPage
        """
        self.setStyleSheet(f"""
            QDialog {{ background-color: {LoginPage.COLOR_BACKGROUND}; }}
            QLabel {{ 
                color: {LoginPage.COLOR_TEXT}; 
                font-size: 11pt; 
                background-color: transparent;
            }}
        """)
        # Styling tombol cancel
        self.cancel_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {LoginPage.COLOR_RED};
                color: {LoginPage.COLOR_TEXT};
                padding: 10px;
                border: none;
                border-radius: 22px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {LoginPage.COLOR_RED_HOVER}; }}
            QPushButton:pressed {{ background-color: {LoginPage.COLOR_RED_PRESSED}; }}
        """)

    def start_capture(self):
        self.thread = QThread()
        self.worker = FaceLoginWorker(self.camera_index)
        self.worker.moveToThread(self.thread)

        self.worker.frame_updated.connect(self.update_frame)
        self.worker.status_updated.connect(self.status_label.setText)
        self.worker.login_success.connect(self.on_login_success)
        self.worker.login_failed.connect(self.on_login_failed)
        self.thread.started.connect(self.worker.run)
        
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()

    @Slot(QImage)
    def update_frame(self, qt_image):
        if qt_image:
            pixmap = QPixmap.fromImage(qt_image)
            self.video_label.setPixmap(pixmap.scaled(
                self.video_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))
        
    @Slot(str)
    def on_login_success(self, username):
        self.login_success.emit(username)
        self.accept()

    @Slot(str)
    def on_login_failed(self, message):
        QMessageBox.warning(self, "Login Failed", message)
        self.reject()

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        event.accept()

#
# --- [FILE ASLI ANDA] Class Utama LoginPage (Telah Dimodifikasi) ---
#
class LoginPage(QWidget):
    
    # --- [ASLI] Palet Warna dari Dashboard ---
    COLOR_BACKGROUND = "#1A1B2E"
    COLOR_PANE_LEFT = "#272540" 
    COLOR_CARD_BG = "#272540"
    COLOR_CARD = "#3E3C6E"     
    COLOR_TEXT = "#F0F0F5"
    COLOR_TEXT_SUBTLE = "#A9A8C0"
    COLOR_GOLD = "#D4AF37"
    COLOR_GOLD_HOVER = "#F0C44F"
    COLOR_GOLD_PRESSED = "#B8860B"
    COLOR_RED = "#D9455F" 
    COLOR_RED_HOVER = "#F06A7F"
    COLOR_RED_PRESSED = "#B32A40"
    # -----------------------------------------------

    def __init__(self, switch_to_dashboard, switch_to_register, user_manager):
        super().__init__()
        self.switch_to_dashboard = switch_to_dashboard
        self.switch_to_register = switch_to_register
        self.user_manager = user_manager
        
        self.login_dialog = None # Untuk menampung dialog wajah
        
        # [BARU] Atribut untuk thread login password
        self.password_thread = None
        self.password_worker = None
        
        self.setAutoFillBackground(True) 
        self.init_ui()
        self.apply_styles()
        
    def init_ui(self):
        # ... (init_ui() tetap sama, tidak diubah) ...
        self.resize(480, 480) 
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Welcome Back 💙")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("titleLabel")

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Username")
        self.user_input.setFixedHeight(45)

        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Password")
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.returnPressed.connect(self.handle_login) 
        self.pass_input.setFixedHeight(45)

        self.login_btn = QPushButton("Login")
        self.login_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.login_btn.clicked.connect(self.handle_login)
        self.login_btn.setObjectName("loginButton") 
        self.login_btn.setFixedHeight(45)

        self.face_btn = QPushButton("Login with Face")
        self.face_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.face_btn.clicked.connect(self.handle_login_face)
        self.face_btn.setObjectName("faceButton")
        self.face_btn.setFixedHeight(45)

        self.register_btn = QPushButton("Don't have an account? Register")
        self.register_btn.setFont(QFont("Segoe UI", 10))
        self.register_btn.clicked.connect(self.switch_to_register)
        self.register_btn.setObjectName("registerButton") 

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setObjectName("statusLabel")

        layout.addWidget(title)
        layout.addSpacing(15)
        layout.addWidget(self.user_input)
        layout.addWidget(self.pass_input)
        layout.addSpacing(10)
        layout.addWidget(self.login_btn)
        layout.addWidget(self.face_btn)
        layout.addWidget(self.register_btn)
        layout.addWidget(self.status_label)

    def apply_styles(self):
        # ... (apply_styles() tetap sama, tidak diubah) ...
        self.setStyleSheet(f"""
            LoginPage {{
                background-color: {self.COLOR_BACKGROUND};
            }}
            
            QLabel {{
                color: {self.COLOR_TEXT};
                background-color: transparent;
            }}
            
            QLabel#titleLabel {{
                color: {self.COLOR_GOLD};
            }}
            
            QLabel#statusLabel {{
                color: {self.COLOR_TEXT_SUBTLE};
                font-size: 10pt;
            }}
            
            QLineEdit {{
                font-family: "Segoe UI";
                font-size: 14px;
                padding: 10px 20px;
                background-color: {self.COLOR_CARD};
                color: {self.COLOR_TEXT};
                border: 2px solid {self.COLOR_GOLD};
                border-radius: 22px;
            }}
            QLineEdit:focus {{
                border: 2px solid {self.COLOR_GOLD_HOVER};
            }}
            
            QPushButton#loginButton {{
                background-color: {self.COLOR_GOLD};
                color: {self.COLOR_PANE_LEFT};
                padding: 10px;
                border: none;
                border-radius: 22px;
                font-weight: bold;
            }}
            QPushButton#loginButton:hover {{
                background-color: {self.COLOR_GOLD_HOVER};
            }}
            QPushButton#loginButton:pressed {{
                background-color: {self.COLOR_GOLD_PRESSED};
            }}
            
            QPushButton#faceButton {{
                background-color: {self.COLOR_CARD};
                color: {self.COLOR_GOLD};
                padding: 10px;
                border: 2px solid {self.COLOR_GOLD};
                border-radius: 22px;
                font-weight: bold;
            }}
            QPushButton#faceButton:hover {{
                background-color: {self.COLOR_CARD_BG};
            }}
            QPushButton#faceButton:pressed {{
                background-color: {self.COLOR_CARD};
            }}
            
            QPushButton#registerButton {{
                background-color: transparent;
                color: {self.COLOR_TEXT_SUBTLE};
                font-size: 9pt;
                border: none;
                text-decoration: underline;
                padding: 5px;
            }}
            QPushButton#registerButton:hover {{
                color: {self.COLOR_TEXT};
            }}
        """)

    def set_ui_busy(self, is_busy):
        # ... (set_ui_busy() tetap sama, tidak diubah) ...
        self.login_btn.setEnabled(not is_busy)
        self.face_btn.setEnabled(not is_busy)
        self.user_input.setEnabled(not is_busy)
        self.pass_input.setEnabled(not is_busy)
        self.register_btn.setEnabled(not is_busy)

    def handle_login(self):
        """
        [MODIFIKASI TOTAL]
        Memindahkan logika verifikasi ke PasswordLoginWorker
        untuk memastikan delay minimal 3 detik.
        """
        username = self.user_input.text()
        password = self.pass_input.text()
        
        if not username or not password:
            QMessageBox.warning(self, "Login Failed", "Username dan password tidak boleh kosong.")
            return
        
        self.set_ui_busy(True)
        self.status_label.setText("Verifying password...")
        
        # Buat thread dan worker baru
        self.password_thread = QThread()
        self.password_worker = PasswordLoginWorker(
            user_manager=self.user_manager,
            username=username,
            password=password
        )
        self.password_worker.moveToThread(self.password_thread)
        
        # Hubungkan sinyal
        self.password_worker.login_success.connect(self.on_password_login_success)
        self.password_worker.login_failed.connect(self.on_password_login_failed)
        self.password_thread.started.connect(self.password_worker.run)
        
        # Bersihkan thread setelah selesai
        self.password_worker.finished.connect(self.password_thread.quit)
        self.password_worker.finished.connect(self.password_worker.deleteLater)
        self.password_thread.finished.connect(self.password_thread.deleteLater)
        
        # Mulai thread
        self.password_thread.start()

    # --- [BARU] Slot untuk hasil dari PasswordLoginWorker ---
    @Slot(str)
    def on_password_login_success(self, username):
        """Dipanggil oleh PasswordLoginWorker ketika login sukses."""
        self.user_input.clear()
        self.pass_input.clear()
        self.status_label.setText("")
        self.set_ui_busy(False)
        self.switch_to_dashboard(username)

    @Slot(str)
    def on_password_login_failed(self, message):
        """Dipanggil oleh PasswordLoginWorker ketika login gagal."""
        QMessageBox.warning(self, "Login Failed", message)
        self.pass_input.clear()
        self.set_ui_busy(False)
        self.status_label.setText("")

    # --- Logika Login Wajah (Tidak Diubah) ---
    def handle_login_face(self):
        self.status_label.setText("Starting face login...")
        self.set_ui_busy(True)
    
        CAMERA_INDEX_TO_USE = 0 
        
        self.login_dialog = FaceLoginDialog(CAMERA_INDEX_TO_USE, self)
        self.login_dialog.login_success.connect(self.on_face_login_success)
        self.login_dialog.finished.connect(lambda: self.set_ui_busy(False)) 
        
        self.login_dialog.show()
        self.login_dialog.start_capture()

    @Slot(str)
    def on_face_login_success(self, username):
        """Dipanggil oleh dialog ketika login sukses."""
        self.set_ui_busy(False)
        self.status_label.setText(f"Welcome, {username}!")
        self.user_input.clear()
        self.pass_input.clear()
        self.switch_to_dashboard(username)