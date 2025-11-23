# registerpage.py (Versi Final dengan Registrasi Wajah)
import os
import cv2
import io
import zipfile
import requests
import time
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QMessageBox, QDialog, QProgressBar
)
from PySide6.QtGui import QFont, QImage, QPixmap
from PySide6.QtCore import Qt, QThread, QObject, Signal, Slot

# --- Konstanta Global untuk Biometrik ---
CASCADE_PATH = "fm/haarcascade_frontalface_default.xml"
API_URL = "https://morsz.azeroth.site" # Ganti dengan URL server Anda

#
# --- [DARI CONTOH] Class Worker untuk Registrasi Wajah ---
#
class FaceRegisterWorker(QObject):
    """
    Menjalankan pengambilan wajah dan upload di thread terpisah.
    """
    progress_frame = Signal(QImage, str) # (video_frame, status_text)
    progress_value = Signal(int)         # Persentase progress bar
    finished = Signal(bool, str)         # (success, message)
    
    def __init__(self, username, camera_index=0):
        super().__init__()
        self.username = username
        self.camera_index = camera_index
        self.images_to_capture = 50
        self._is_running = True

    @Slot()
    def run(self):
        try:
            if not os.path.exists(CASCADE_PATH):
                raise FileNotFoundError(f"Haar cascade not found at {CASCADE_PATH}")

            face_detector = cv2.CascadeClassifier(CASCADE_PATH)
            
            cap = cv2.VideoCapture(self.camera_index) 
            if not cap.isOpened():
                raise IOError(f"Cannot open webcam at index {self.camera_index}.")

            image_list = []
            count = 0
            
            while count < self.images_to_capture and self._is_running:
                ret, frame = cap.read()
                if not ret:
                    self.progress_frame.emit(QImage(), "Uploading to server...")
                    break
                
                frame = cv2.flip(frame, 1)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_detector.detectMultiScale(gray, 1.3, 5)

                status_text = "Looking for face..."
                
                if len(faces) > 0:
                    (x, y, w, h) = faces[0]
                    face_roi = gray[y:y+h, x:x+w]
                    
                    if face_roi.size > 0:
                        image_list.append(face_roi)
                        count += 1
                        status_text = f"Captured image {count}/{self.images_to_capture}"
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                        time.sleep(0.1) 
                
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                
                self.progress_frame.emit(qt_image, status_text)
                self.progress_value.emit(int((count / self.images_to_capture) * 100))
            
            cap.release()
            
            if not self._is_running:
                self.finished.emit(False, "Capture canceled by user.")
                return

            if len(image_list) < self.images_to_capture:
                raise Exception(f"Capture failed. Only got {len(image_list)} images.")

            self.progress_frame.emit(None, f"Captured {len(image_list)} images. Zipping...")
            self.progress_value.emit(100)

            mem_zip = io.BytesIO()
            with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, image_array in enumerate(image_list):
                    is_success, buffer = cv2.imencode(".jpg", image_array)
                    if is_success:
                        zf.writestr(f"image_{i}.jpg", buffer.tobytes())
            
            mem_zip.seek(0)
            self.progress_frame.emit(None, "Uploading to server...")

            files = {'file': ('faces.zip', mem_zip, 'application/zip')}
            data = {'username': self.username}
            response = requests.post(f"{API_URL}/register-face", files=files, data=data, timeout=60)

            if response.status_code == 200:
                self.finished.emit(True, "Face registered successfully! Training started.")
            else:
                self.finished.emit(False, f"Server error: {response.json().get('message', 'Unknown error')}")

        except Exception as e:
            self.finished.emit(False, f"Error: {e}")
        finally:
            if 'cap' in locals() and cap.isOpened():
                cap.release()

    def stop(self):
        self._is_running = False

#
# --- [DARI CONTOH] Class Dialog Pop-up untuk Registrasi Wajah ---
#
class FaceCaptureDialog(QDialog):
    """
    Ini adalah jendela pop-up baru yang menampilkan feed webcam.
    """
    registration_complete = Signal()
    
    def __init__(self, username, camera_index, parent=None):
        super().__init__(parent)
        self.username = username
        self.camera_index = camera_index
        
        self.thread = None
        self.worker = None

        self.setWindowTitle("Register Face")
        self.setModal(True)
        self.setMinimumSize(640, 580)
        
        self.video_label = QLabel("Starting camera...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; border-radius: 10px;")
        self.video_label.setFixedSize(600, 450)

        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.video_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.cancel_button)
        
        self.apply_styles()
        
    def apply_styles(self):
        """
        [MODIFIKASI] Menggunakan palet warna dari RegisterPage
        """
        self.setStyleSheet(f"""
            QDialog {{ background-color: {RegisterPage.COLOR_BACKGROUND}; }}
            QLabel {{ 
                color: {RegisterPage.COLOR_TEXT}; 
                font-size: 11pt; 
                background-color: transparent;
            }}
            QProgressBar {{ 
                text-align: center; 
                color: {RegisterPage.COLOR_PANE_LEFT};
                font-weight: bold;
                background-color: {RegisterPage.COLOR_CARD};
                border: 1px solid {RegisterPage.COLOR_CARD_BG};
                border-radius: 5px;
            }}
            QProgressBar::chunk {{ 
                background-color: {RegisterPage.COLOR_GOLD}; 
                border-radius: 5px;
            }}
        """)
        # Styling tombol cancel
        self.cancel_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {RegisterPage.COLOR_RED};
                color: {RegisterPage.COLOR_TEXT};
                padding: 10px;
                border: none;
                border-radius: 22px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {RegisterPage.COLOR_RED_HOVER}; }}
            QPushButton:pressed {{ background-color: {RegisterPage.COLOR_RED_PRESSED}; }}
        """)

    def start_capture(self):
        self.thread = QThread()
        self.worker = FaceRegisterWorker(self.username, self.camera_index)
        self.worker.moveToThread(self.thread)

        self.worker.progress_frame.connect(self.update_frame)
        self.worker.progress_value.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_finished)
        self.thread.started.connect(self.worker.run)
        
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()

    @Slot(QImage, str)
    def update_frame(self, qt_image, status_text):
        if qt_image:
            pixmap = QPixmap.fromImage(qt_image)
            self.video_label.setPixmap(pixmap.scaled(
                self.video_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))
        self.status_label.setText(status_text)
        
    @Slot(bool, str)
    def on_finished(self, success, message):
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.warning(self, "Failed", message)
            
        self.registration_complete.emit()
        self.accept()

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        self.registration_complete.emit()
        event.accept()

#
# --- [FILE ASLI ANDA] Class Utama RegisterPage (Telah Dimodifikasi) ---
#
class RegisterPage(QWidget):

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
    # [BARU] Warna untuk tombol "Cancel" di dialog
    COLOR_RED = "#D9455F" 
    COLOR_RED_HOVER = "#F06A7F"
    COLOR_RED_PRESSED = "#B32A40"
    # -----------------------------------------------

    def __init__(self, switch_to_login, user_manager):
        super().__init__()
        self.switch_to_login = switch_to_login
        self.user_manager = user_manager
        
        self.capture_dialog = None # [BARU] Untuk menampung dialog
        
        self.setAutoFillBackground(True) 
        self.init_ui()
        self.apply_styles()
        
    def init_ui(self):
        # [MODIFIKASI] Ukuran disesuaikan untuk tombol baru
        self.resize(480, 520) 
        layout = QVBoxLayout(self)
        
        layout.setSpacing(15) # Diubah dari 20 ke 15
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Create New Account 💜")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("titleLabel")

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Username")
        self.user_input.setFixedHeight(45)

        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Password")
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.setFixedHeight(45)

        self.confirm_input = QLineEdit()
        self.confirm_input.setPlaceholderText("Confirm Password")
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.returnPressed.connect(self.handle_register)
        self.confirm_input.setFixedHeight(45)

        # --- [MODIFIKASI] Layout Tombol (Horizontal) ---
        button_layout = QHBoxLayout()
        self.create_btn = QPushButton("Create Account")
        self.create_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.create_btn.clicked.connect(self.handle_register)
        self.create_btn.setObjectName("create_btn") # Ganti nama ID
        self.create_btn.setFixedHeight(45)
        
        self.face_btn = QPushButton("Register with Face")
        self.face_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.face_btn.clicked.connect(self.handle_register_face)
        self.face_btn.setObjectName("face_btn") # ID Baru
        self.face_btn.setFixedHeight(45)
        
        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(self.face_btn)
        # ------------------------------------------------

        self.back_btn = QPushButton("Back to Login") # [BARU] Ganti nama ke self
        self.back_btn.setFont(QFont("Segoe UI", 10))
        self.back_btn.clicked.connect(self.switch_to_login)
        self.back_btn.setObjectName("backButton") 

        # --- [BARU] Label Status ---
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setObjectName("statusLabel")
        # -----------------------------

        layout.addWidget(title)
        layout.addSpacing(15)
        layout.addWidget(self.user_input)
        layout.addWidget(self.pass_input)
        layout.addWidget(self.confirm_input)
        layout.addSpacing(10)
        layout.addLayout(button_layout) # [MODIFIKASI] Tambahkan HBox
        layout.addWidget(self.back_btn)
        layout.addWidget(self.status_label) # [BARU] Tambahkan label status

    def apply_styles(self):
        """
        [MODIFIKASI] Menambahkan style untuk #face_btn,
        #statusLabel, dan mengubah nama #createButton -> #create_btn
        """
        self.setStyleSheet(f"""
            RegisterPage {{
                background-color: {self.COLOR_BACKGROUND};
            }}
            
            QLabel {{
                color: {self.COLOR_TEXT};
                background-color: transparent;
            }}

            QLabel#titleLabel {{
                color: {self.COLOR_GOLD};
            }}
            
            /* [BARU] Style untuk label status */
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
            
            /* [GANTI NAMA] Style untuk tombol Create Account (Emas) */
            QPushButton#create_btn {{
                background-color: {self.COLOR_GOLD};
                color: {self.COLOR_PANE_LEFT};
                padding: 10px;
                border: none;
                border-radius: 22px;
                font-weight: bold;
            }}
            QPushButton#create_btn:hover {{
                background-color: {self.COLOR_GOLD_HOVER};
            }}
            QPushButton#create_btn:pressed {{
                background-color: {self.COLOR_GOLD_PRESSED};
            }}
            
            /* [BARU] Style untuk tombol Register Wajah (Sekunder) */
            QPushButton#face_btn {{
                background-color: {self.COLOR_CARD};
                color: {self.COLOR_GOLD};
                padding: 10px;
                border: 2px solid {self.COLOR_GOLD};
                border-radius: 22px;
                font-weight: bold;
            }}
            QPushButton#face_btn:hover {{
                background-color: {self.COLOR_CARD_BG};
            }}
            QPushButton#face_btn:pressed {{
                background-color: {self.COLOR_CARD};
            }}
            
            /* Style untuk tombol Back (Link) */
            QPushButton#backButton {{
                background-color: transparent;
                color: {self.COLOR_TEXT_SUBTLE};
                font-size: 9pt;
                border: none;
                text-decoration: underline;
                padding: 5px;
            }}
            QPushButton#backButton:hover {{
                color: {self.COLOR_TEXT};
            }}
        """)

    # --- [BARU] Fungsi untuk menonaktifkan UI ---
    def set_ui_busy(self, is_busy):
        self.create_btn.setEnabled(not is_busy)
        self.face_btn.setEnabled(not is_busy)
        self.user_input.setEnabled(not is_busy)
        self.pass_input.setEnabled(not is_busy)
        self.confirm_input.setEnabled(not is_busy)
        self.back_btn.setEnabled(not is_busy)

    def handle_register(self, show_success_popup=True):
        """
        [MODIFIKASI] Logika dari `register examples.py`.
        Handle registrasi password. 
        Mengembalikan True jika sukses, False jika gagal.
        """
        user = self.user_input.text()
        p1 = self.pass_input.text()
        p2 = self.confirm_input.text()
        
        if not user or not p1 or not p2:
            QMessageBox.warning(self, "Error", "Semua field harus diisi.")
            return False
        
        if p1 != p2: 
            QMessageBox.warning(self, "Error", "Password tidak sama.")
            self.pass_input.clear()
            self.confirm_input.clear()
            return False

        try:
            self.status_label.setText("Registering account...")
            self.set_ui_busy(True)
            
            # PENTING: Panggil API Anda
            success, message = self.user_manager.register_user(user, p1)
            
            if success:
                if show_success_popup:
                    QMessageBox.information(self, "Success", f"{message} 💙")
                
                self.user_input.clear()
                self.pass_input.clear()
                self.confirm_input.clear()
                self.status_label.setText("")
                self.set_ui_busy(False)
                return True # Sukses
            else:
                QMessageBox.warning(self, "Error", message)
                self.status_label.setText("Registration failed.")
                self.set_ui_busy(False)
                return False # Gagal
                
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Gagal terhubung ke server: {e}")
            self.status_label.setText("Connection failed.")
            self.set_ui_busy(False)
            return False # Gagal
        
    # --- [BARU] Logika dari `register examples.py` ---
    def handle_register_face(self):
        username = self.user_input.text()
        if not username:
            QMessageBox.warning(self, "Error", "Harap isi semua field (username/password) terlebih dahulu.")
            return
            
        # 1. Daftar via password terlebih dahulu
        # show_success_popup=False agar tidak ada 2 pop-up
        if not self.handle_register(show_success_popup=False):
            # Registrasi password gagal, hentikan
            return 
        
        # 2. Jika registrasi password sukses, lanjutkan ke wajah
        self.status_label.setText("Starting face capture...")
        self.set_ui_busy(True)

        # Ganti 0 jika Anda ingin menggunakan kamera lain
        CAMERA_INDEX_TO_USE = 0 
        
        self.capture_dialog = FaceCaptureDialog(username, CAMERA_INDEX_TO_USE, self)
        self.capture_dialog.registration_complete.connect(self.on_face_reg_complete)
        
        self.capture_dialog.show()
        self.capture_dialog.start_capture()

    @Slot()
    def on_face_reg_complete(self):
        """Dipanggil saat dialog wajah ditutup."""
        self.status_label.setText("")
        self.set_ui_busy(False)
        # Opsional: langsung pindah ke halaman login
        # self.switch_to_login()