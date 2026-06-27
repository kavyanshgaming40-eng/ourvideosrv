import os
import sys
import time
import socketio
import logging
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt, QThread, QPropertyAnimation, QEvent
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QSlider, QFileDialog, QMessageBox,
    QTextEdit, QSplitter, QFrame, QSizePolicy, QDialog, QStackedWidget,
    QGraphicsOpacityEffect
)
from PyQt6.QtGui import QFont, QColor, QPalette, QKeyEvent, QShortcut, QKeySequence

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Attempt to import vlc. The user must have VLC player installed (32-bit/64-bit matching Python arch)
try:
    import vlc
except ImportError:
    logging.error("python-vlc package is missing. Install with: pip install python-vlc")
    vlc = None

# Custom styling sheets for a modern Dark Theme (Discord/Plex inspired)
DARK_STYLE = """
QMainWindow {
    background-color: #000000;
}
QWidget {
    color: #f1f5f9;
    font-family: "Segoe UI", -apple-system, sans-serif;
    font-size: 13px;
}
QFrame#controlBar {
    background-color: rgba(15, 17, 26, 0.85);
    border: none;
    border-radius: 8px;
}
QDialog {
    background-color: #0f111a;
    border: 1px solid #1e293b;
    border-radius: 12px;
}
QPushButton {
    background-color: #5f3dc4;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #7048e8;
}
QPushButton:pressed {
    background-color: #512fdb;
}
QPushButton:disabled {
    background-color: #212529;
    color: #495057;
}
QPushButton#playBtn, QPushButton#fullscreenBtn, QPushButton#openFileBtn, QPushButton#chatToggleBtn, QPushButton#settingsBtn {
    background-color: transparent;
    border: none;
    color: #adb5bd;
    font-size: 15px;
    padding: 4px;
}
QPushButton#playBtn:hover, QPushButton#fullscreenBtn:hover, QPushButton#openFileBtn:hover, QPushButton#chatToggleBtn:hover, QPushButton#settingsBtn:hover {
    color: #f1f5f9;
}
QLineEdit {
    background-color: #1a1b26;
    border: 1px solid #2e3047;
    border-radius: 6px;
    padding: 5px 8px;
    color: #ffffff;
}
QLineEdit:focus {
    border: 1px solid #5f3dc4;
}
QSlider::groove:horizontal {
    border: none;
    height: 4px;
    background: #212529;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #5f3dc4;
    border: none;
    width: 10px;
    height: 10px;
    margin: -3px 0;
    border-radius: 5px;
}
QSlider::handle:horizontal:hover {
    background: #7048e8;
    width: 12px;
    height: 12px;
    border-radius: 6px;
}
QSlider::add-page:horizontal {
    background: #212529;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #5f3dc4;
    border-radius: 2px;
}
QTextEdit {
    background-color: rgba(15, 17, 26, 0.9);
    border: none;
    border-radius: 8px;
    color: #e2e8f0;
    padding: 6px;
}
"""

class ToastNotification(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            background-color: rgba(22, 23, 30, 0.95);
            border: 1px solid #5f3dc4;
            color: #ffffff;
            border-radius: 16px;
            padding: 8px 20px;
            font-size: 12px;
            font-weight: bold;
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.hide()
        
    def show_toast(self, text, duration_ms=2500):
        self.setText(text)
        self.adjustSize()
        
        if self.parentWidget():
            p_geom = self.parentWidget().geometry()
            # Position at top center
            x = (p_geom.width() - self.width()) // 2
            y = 50
            self.move(x, y)
            
        self.show()
        self.raise_()
        
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(250)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        
        QTimer.singleShot(duration_ms, self.fade_out)
        
    def fade_out(self):
        self.anim_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_out.setDuration(400)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.finished.connect(self.hide)
        self.anim_out.start()


class EmptyStateWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #08090d;")
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)
        
        icon_label = QLabel("🍿")
        icon_label.setFont(QFont("Segoe UI", 56))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        title = QLabel("ourvideo")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("Synchronized cinema for two")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet("color: #64748b;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        
        self.open_btn = QPushButton("Select Video File")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setStyleSheet("""
            background-color: #5f3dc4;
            color: white;
            font-size: 13px;
            font-weight: bold;
            border-radius: 8px;
            padding: 10px 24px;
        """)
        self.open_btn.clicked.connect(parent.open_file if parent else lambda: None)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.open_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.info_label = QLabel("Or click the gear icon ⚙ at the bottom to connect to your partner")
        self.info_label.setFont(QFont("Segoe UI", 11))
        self.info_label.setStyleSheet("color: #475569;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)


class ConnectionDialog(QDialog):
    def __init__(self, parent, current_url, current_code):
        super().__init__(parent)
        self.setWindowTitle("Settings & Connection")
        self.setFixedWidth(360)
        self.setStyleSheet(parent.styleSheet())
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        layout.addWidget(QLabel("<b>Server URL</b>"))
        self.url_input = QLineEdit(current_url)
        self.url_input.setPlaceholderText("https://ourvideosrv.onrender.com")
        layout.addWidget(self.url_input)
        
        self.connect_btn = QPushButton("Connect" if not parent.network.sio.connected else "Disconnect")
        self.connect_btn.clicked.connect(self.handle_connection)
        layout.addWidget(self.connect_btn)
        
        # Line separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: #2e3047;")
        layout.addWidget(sep)
        
        layout.addWidget(QLabel("<b>Room Settings</b>"))
        self.create_btn = QPushButton("Create Room (Get Code)")
        self.create_btn.setEnabled(parent.network.sio.connected)
        self.create_btn.clicked.connect(self.handle_create)
        layout.addWidget(self.create_btn)
        
        self.code_input = QLineEdit(current_code)
        self.code_input.setPlaceholderText("Enter 6-digit Code")
        self.code_input.setMaxLength(6)
        
        join_layout = QHBoxLayout()
        join_layout.addWidget(self.code_input)
        self.join_btn = QPushButton("Join Room")
        self.join_btn.setEnabled(parent.network.sio.connected)
        self.join_btn.clicked.connect(self.handle_join)
        join_layout.addWidget(self.join_btn)
        
        layout.addLayout(join_layout)
        
        self.parent_win = parent
        
    def handle_connection(self):
        self.parent_win.server_url_input.setText(self.url_input.text().strip())
        self.parent_win.toggle_connection()
        # Small delay to let connection state update, then refresh button states
        QTimer.singleShot(800, self.update_states)
        
    def handle_create(self):
        self.parent_win.network.create_room()
        self.accept()
        
    def handle_join(self):
        code = self.code_input.text().strip()
        if len(code) == 6 and code.isdigit():
            self.parent_win.room_code_input.setText(code)
            self.parent_win.join_room()
            self.accept()
        else:
            QMessageBox.warning(self, "Input Error", "Please enter a valid 6-digit room code.")
            
    def update_states(self):
        connected = self.parent_win.network.sio.connected
        self.connect_btn.setText("Disconnect" if connected else "Connect")
        self.create_btn.setEnabled(connected)
        self.join_btn.setEnabled(connected)


class NetworkWorker(QObject):
    """
    Handles background socket connection, heartbeats for ping/latency calculation,
    and event handling. Uses Qt signals to communicate with the main thread.
    """
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    room_created = pyqtSignal(str, str)
    room_joined = pyqtSignal(str, str)
    join_error = pyqtSignal(str)
    partner_disconnected = pyqtSignal(str)
    file_status = pyqtSignal(bool, str)
    sync_received = pyqtSignal(dict)
    latency_updated = pyqtSignal(float)
    chat_received = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=5, reconnection_delay=1)
        self.latency = 0.0 # in seconds
        self.last_ping_time = 0.0
        self.room_code = None
        self.server_url = ""
        self.setup_handlers()

    def setup_handlers(self):
        @self.sio.on('connect')
        def on_connect():
            logging.info("Connected to server.")
            self.connected.emit()

        @self.sio.on('disconnect')
        def on_disconnect():
            logging.info("Disconnected from server.")
            self.disconnected.emit()

        @self.sio.on('room_created')
        def on_room_created(data):
            self.room_code = data.get("room_code")
            self.room_created.emit(self.room_code, data.get("status", ""))

        @self.sio.on('room_joined')
        def on_room_joined(data):
            self.room_code = data.get("room_code")
            self.room_joined.emit(self.room_code, data.get("status", ""))

        @self.sio.on('join_error')
        def on_join_error(data):
            self.join_error.emit(data.get("message", "Error joining room."))

        @self.sio.on('partner_disconnected')
        def on_partner_disconnected(data):
            self.partner_disconnected.emit(data.get("status", "Partner disconnected."))

        @self.sio.on('file_status')
        def on_file_status(data):
            self.file_status.emit(data.get("match", False), data.get("message", ""))

        @self.sio.on('sync_receive')
        def on_sync_receive(data):
            self.sync_received.emit(data)

        @self.sio.on('pong_client')
        def on_pong(data):
            sent_time = data.get("client_time", 0.0)
            rtt = time.time() - sent_time
            # Latency is half the Round Trip Time (RTT)
            self.latency = rtt / 2.0
            self.latency_updated.emit(self.latency * 1000.0) # emit in ms

        # Optional chat event
        @self.sio.on('chat_msg')
        def on_chat(data):
            self.chat_received.emit(data.get("sender", "Partner"), data.get("message", ""))

    def connect_server(self, url):
        try:
            self.server_url = url
            if self.sio.connected:
                self.sio.disconnect()
            self.sio.connect(url, wait_timeout=5)
        except Exception as e:
            logging.error(f"Connection failed: {e}")
            self.disconnected.emit()

    def disconnect_server(self):
        if self.sio.connected:
            self.sio.disconnect()

    def create_room(self):
        if self.sio.connected:
            self.sio.emit('create_room')

    def join_room(self, code):
        if self.sio.connected:
            self.sio.emit('join_room', {"room_code": code})

    def send_file_info(self, filename, size, duration):
        if self.sio.connected:
            self.sio.emit('file_info', {
                "filename": filename,
                "size": size,
                "duration": duration
            })

    def send_sync(self, event_type, current_time):
        """
        Sends synchronization payload with event type, player timestamp,
        and current Unix time for latency calculations.
        """
        if self.sio.connected:
            payload = {
                "event": event_type,
                "time": float(current_time),
                "timestamp": time.time()
            }
            self.sio.emit('sync_event', payload)

    def send_chat(self, msg):
        if self.sio.connected and self.room_code:
            # We emit through room broadcast (or standard sync channel)
            # To keep server code clean without adding a custom chat route on server,
            # we can reuse Flask-SocketIO's broadcasting to room.
            # However, since room chat isn't specifically coded in sync_event,
            # we'll emit 'sync_event' with a special format, or we'll just check
            # if we can emit. Wait, since server broadcasts sync_event directly,
            # we can inject a 'chat' type sync event! That keeps server code simple.
            payload = {
                "event": "chat",
                "message": msg,
                "sender": "Partner",
                "timestamp": time.time()
            }
            self.sio.emit('sync_event', payload)

    def ping_server(self):
        if self.sio.connected:
            self.sio.emit('ping_server', {"client_time": time.time()})


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ourvideo - Synced Movie Player")
        self.setMinimumSize(1280, 720)
        self.setStyleSheet(DARK_STYLE)

        # Networking core
        self.network = NetworkWorker()
        
        # Player state
        self.vlc_instance = None
        self.media_player = None
        self.is_playing = False
        self.duration = 0.0
        self.ignore_slider_update = False
        
        # Sync control flags
        self.block_outgoing_sync = False
        self.sync_enabled = False
        
        # File info
        self.current_filepath = ""
        self.current_filesize = 0
        
        # Mute and Volume tracking
        self.is_muted = False
        self.previous_volume = 80
        
        # Initialize VLC
        self.init_vlc()

        # Build UI
        self.init_ui()
        
        # Connect signals
        self.connect_signals()

        # Latency & ping timer (every 5 seconds)
        self.ping_timer = QTimer(self)
        self.ping_timer.timeout.connect(self.network.ping_server)
        
        # Main slider & player state update timer
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(200)
        self.update_timer.timeout.connect(self.update_player_state)

        # Control Auto-Hiding Timer
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(3000)
        self.hide_timer.timeout.connect(self.hide_controls)
        
        # Enable Mouse tracking on main window
        self.setMouseTracking(True)

        # Global Keyboard Shortcuts (Window scope to ensure they work when clicking sliders/buttons)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.on_shortcut_space)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self.on_shortcut_f)
        QShortcut(QKeySequence(Qt.Key.Key_M), self, self.on_shortcut_m)
        QShortcut(QKeySequence(Qt.Key.Key_C), self, self.on_shortcut_c)
        QShortcut(QKeySequence(Qt.Key.Key_S), self, self.on_shortcut_s)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self.on_shortcut_left)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self.on_shortcut_right)

    def init_vlc(self):
        if not vlc:
            QMessageBox.critical(self, "VLC Error", "VLC bindings not found. Make sure python-vlc is installed and VLC Player is installed on your system.")
            return

        # Initialize with hardware acceleration parameters for Windows
        args = [
            '--no-xlib',
            '--quiet',
            '--video-title-show',
            '--no-video-title-show',
            '--avcodec-hw=any'  # Use hardware decoder
        ]
        try:
            self.vlc_instance = vlc.Instance(args)
            if not self.vlc_instance:
                raise Exception("vlc.Instance returned None. The libvlc library could not be loaded.")
            self.media_player = self.vlc_instance.media_player_new()
        except Exception as e:
            self.vlc_instance = None
            self.media_player = None
            logging.error(f"VLC initialization failed: {e}")
            QMessageBox.critical(
                self, 
                "VLC Load Error", 
                "Could not load VLC. Please verify:\n\n"
                "1. VLC Media Player is installed on this PC.\n"
                "2. Your VLC architecture matches your Python installation:\n"
                "   - If your Python is 64-bit (default), you MUST install 64-bit VLC.\n"
                "   - If your Python is 32-bit, you MUST install 32-bit VLC.\n\n"
                "Error details: " + str(e)
            )

    def init_ui(self):
        # Allow mouse tracking on the main window
        self.setMouseTracking(True)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Background components (instantiated but kept out of layout to maintain state logic)
        self.server_url_input = QLineEdit("https://ourvideosrv.onrender.com")
        self.room_code_input = QLineEdit()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.create_room_btn = QPushButton("Create Room")
        self.create_room_btn.clicked.connect(self.network.create_room)
        self.join_room_btn = QPushButton("Join Room")
        self.join_room_btn.clicked.connect(self.join_room)

        # ----------------- PREMIUM TOP BAR -----------------
        self.top_bar_container = QWidget()
        self.top_bar_container.setObjectName("topBarContainer")
        self.top_bar_container.setStyleSheet("background-color: rgba(12, 13, 18, 0.85); border-bottom: 1px solid #1a1b26;")
        self.top_bar_container.setFixedHeight(45)
        
        top_bar_layout = QHBoxLayout(self.top_bar_container)
        top_bar_layout.setContentsMargins(15, 0, 15, 0)
        
        logo = QLabel("ourvideo 🍿")
        logo.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        logo.setStyleSheet("color: #6c5ce7;")
        
        self.top_file_label = QLabel("No Video Loaded")
        self.top_file_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        self.top_file_label.setStyleSheet("color: #94a3b8;")
        self.top_file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.top_status_label = QLabel("🔴 Disconnected")
        self.top_status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.top_status_label.setStyleSheet("color: #ef4444;")
        self.top_status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        top_bar_layout.addWidget(logo)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.top_file_label)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.top_status_label)
        
        main_layout.addWidget(self.top_bar_container)

        # ----------------- CENTER BODY (PLAYER & CHAT SPLIT) -----------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #1a1b26; }")
        
        # Left side: QStackedWidget to manage Empty State & Video Player
        self.stacked_widget = QStackedWidget()
        
        # Page 0: Empty state
        self.empty_state = EmptyStateWidget(self)
        self.stacked_widget.addWidget(self.empty_state)
        
        # Page 1: Video widget container
        self.video_container = QWidget()
        self.video_container.setStyleSheet("background-color: black;")
        self.video_container.setMouseTracking(True)
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        self.video_widget = QFrame()
        self.video_widget.setStyleSheet("background-color: black;")
        self.video_widget.setMouseTracking(True)
        self.video_widget.installEventFilter(self) # Capture mouse moves
        video_layout.addWidget(self.video_widget)
        
        self.stacked_widget.addWidget(self.video_container)
        
        splitter.addWidget(self.stacked_widget)
        splitter.setStretchFactor(0, 4) # 80% width

        # Right side: Chat panel (300px width, hidden by default)
        self.chat_container = QWidget()
        self.chat_container.setFixedWidth(300)
        self.chat_container.setStyleSheet("background-color: #08090d; border-left: 1px solid #1a1b26;")
        self.chat_container.hide() # Collapsed by default
        
        chat_layout = QVBoxLayout(self.chat_container)
        chat_layout.setContentsMargins(10, 10, 10, 10)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("Welcome to ourvideo! Click the settings gear to connect and chat.")
        
        chat_input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type message...")
        self.chat_input.returnPressed.connect(self.send_chat_message)
        
        self.send_chat_btn = QPushButton("Send")
        self.send_chat_btn.clicked.connect(self.send_chat_message)
        
        chat_input_layout.addWidget(self.chat_input)
        chat_input_layout.addWidget(self.send_chat_btn)
        
        chat_title = QLabel("<b>Room Chat</b>")
        chat_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        chat_layout.addWidget(chat_title)
        chat_layout.addWidget(self.chat_display)
        chat_layout.addLayout(chat_input_layout)
        
        splitter.addWidget(self.chat_container)
        splitter.setStretchFactor(1, 1) # 20% width
        
        main_layout.addWidget(splitter, stretch=1)

        # ----------------- BOTTOM BAR (CONTROLS) -----------------
        self.control_bar_container = QWidget()
        self.control_bar_container.setStyleSheet("background-color: #000000; padding: 5px 10px 10px 10px;")
        self.control_bar_container.setMouseTracking(True)
        control_bar_layout = QVBoxLayout(self.control_bar_container)
        control_bar_layout.setContentsMargins(0, 0, 0, 0)
        control_bar_layout.setSpacing(5)

        control_bar = QFrame()
        control_bar.setObjectName("controlBar")
        control_bar.setMouseTracking(True)
        control_layout = QVBoxLayout(control_bar)
        control_layout.setContentsMargins(12, 8, 12, 8)
        control_layout.setSpacing(6)

        # Progress slider & Time label row
        progress_layout = QHBoxLayout()
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 1000)
        self.time_slider.sliderPressed.connect(self.on_slider_pressed)
        self.time_slider.sliderMoved.connect(self.on_slider_moved)
        self.time_slider.sliderReleased.connect(self.on_slider_released)
        
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.time_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        
        progress_layout.addWidget(self.time_slider)
        progress_layout.addWidget(self.time_label)
        control_layout.addLayout(progress_layout)

        # Controls buttons row
        buttons_layout = QHBoxLayout()
        
        self.open_file_btn = QPushButton("📁")
        self.open_file_btn.setObjectName("openFileBtn")
        self.open_file_btn.setToolTip("Open Video File (Ctrl+O)")
        self.open_file_btn.clicked.connect(self.open_file)
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("playBtn")
        self.play_btn.setFixedWidth(30)
        self.play_btn.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setEnabled(False)

        self.file_label = QLabel("No File Selected")
        self.file_label.setStyleSheet("color: #64748b; font-size: 12px;")
        self.file_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 11px; margin-right: 10px;")
        
        self.latency_label = QLabel("")
        self.latency_label.setStyleSheet("color: #64748b; font-size: 11px; margin-right: 10px;")

        # Smart volume control button + slider
        self.volume_btn = QPushButton("🔊")
        self.volume_btn.setObjectName("volumeBtn")
        self.volume_btn.setStyleSheet("background-color: transparent; border: none; font-size: 14px; padding: 4px;")
        self.volume_btn.setToolTip("Mute/Unmute (M)")
        self.volume_btn.clicked.connect(self.toggle_mute)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(70)
        self.volume_slider.valueChanged.connect(self.change_volume)
        
        self.chat_toggle_btn = QPushButton("💬")
        self.chat_toggle_btn.setObjectName("chatToggleBtn")
        self.chat_toggle_btn.setToolTip("Toggle Chat (C)")
        self.chat_toggle_btn.clicked.connect(self.toggle_chat)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setToolTip("Settings & Connection (S)")
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.setObjectName("fullscreenBtn")
        self.fullscreen_btn.setFixedWidth(30)
        self.fullscreen_btn.setToolTip("Toggle Fullscreen (F)")
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)

        buttons_layout.addWidget(self.open_file_btn)
        buttons_layout.addWidget(self.play_btn)
        buttons_layout.addWidget(self.file_label)
        buttons_layout.addWidget(self.latency_label)
        buttons_layout.addWidget(self.status_label)
        buttons_layout.addWidget(self.volume_btn)
        buttons_layout.addWidget(self.volume_slider)
        buttons_layout.addWidget(self.chat_toggle_btn)
        buttons_layout.addWidget(self.settings_btn)
        buttons_layout.addWidget(self.fullscreen_btn)
        
        control_layout.addLayout(buttons_layout)
        control_bar_layout.addWidget(control_bar)
        main_layout.addWidget(self.control_bar_container)

        # Set main widget
        central_widget = QWidget()
        central_widget.setMouseTracking(True)
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # ----------------- TOAST CONTAINER -----------------
        self.toast = ToastNotification(self)

    def toggle_chat(self):
        self.chat_container.setVisible(not self.chat_container.isVisible())
        self.show_toast("Chat Panel Opened" if self.chat_container.isVisible() else "Chat Panel Hidden", 1500)

    def open_settings_dialog(self):
        dialog = ConnectionDialog(self, self.server_url_input.text(), self.room_code_input.text())
        dialog.exec()

    # ----------------- EVENT FILTER FOR MOUSE MOVE & AUTO-HIDE -----------------
    def eventFilter(self, obj, event):
        if obj == self.video_widget:
            if event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.HoverMove):
                self.show_controls()
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        self.show_controls()
        super().mouseMoveEvent(event)

    def show_controls(self):
        self.control_bar_container.show()
        self.top_bar_container.show()
        # Reset auto-hide timer if movie is playing and in Fullscreen mode
        if self.is_playing and self.isFullScreen():
            self.hide_timer.start()
        else:
            self.hide_timer.stop()

    def hide_controls(self):
        # Only hide controls when playing AND in Fullscreen mode
        # This keeps the layout perfectly stable in windowed mode
        if self.is_playing and self.isFullScreen():
            self.control_bar_container.hide()
            self.top_bar_container.hide()

    def show_toast(self, text, duration_ms=2500):
        if hasattr(self, 'toast'):
            self.toast.show_toast(text, duration_ms)

    # ----------------- AUDIO & SMART VOLUME MUTE LOGIC -----------------
    def toggle_mute(self):
        if not self.media_player:
            return
            
        if self.is_muted:
            # Unmute
            self.is_muted = False
            self.media_player.audio_set_mute(False)
            self.volume_slider.setValue(self.previous_volume)
            self.update_volume_icon(self.previous_volume)
            self.show_toast(f"Volume: {self.previous_volume}%", 1500)
        else:
            # Mute
            self.is_muted = True
            self.previous_volume = self.volume_slider.value()
            self.media_player.audio_set_mute(True)
            self.volume_slider.setValue(0)
            self.update_volume_icon(0)
            self.show_toast("Muted", 1500)

    def update_volume_icon(self, val):
        if val == 0 or self.is_muted:
            self.volume_btn.setText("🔇")
        elif val < 30:
            self.volume_btn.setText("🔈")
        elif val < 70:
            self.volume_btn.setText("🔉")
        else:
            self.volume_btn.setText("🔊")

    def connect_signals(self):
        # Network signals
        self.network.connected.connect(self.on_network_connected)
        self.network.disconnected.connect(self.on_network_disconnected)
        self.network.room_created.connect(self.on_room_created)
        self.network.room_joined.connect(self.on_room_joined)
        self.network.join_error.connect(self.on_join_error)
        self.network.partner_disconnected.connect(self.on_partner_disconnected)
        self.network.file_status.connect(self.on_file_status)
        self.network.sync_received.connect(self.on_sync_received)
        self.network.latency_updated.connect(self.on_latency_updated)
        self.network.chat_received.connect(self.on_chat_received)

    def toggle_connection(self):
        if self.connect_btn.text() == "Connect":
            url = self.server_url_input.text().strip()
            self.status_label.setText("Connecting...")
            self.status_label.setStyleSheet("color: #f1c40f; font-weight: bold;")
            # Run connection in background thread to prevent UI freezing
            class ConnectThread(QThread):
                def __init__(self, net, target_url):
                    super().__init__()
                    self.net = net
                    self.target_url = target_url
                def run(self):
                    self.net.connect_server(self.target_url)
            
            self.conn_thread = ConnectThread(self.network, url)
            self.conn_thread.start()
        else:
            self.network.disconnect_server()

    def on_network_connected(self):
        self.status_label.setText("Connected")
        self.status_label.setStyleSheet("color: #eab308; font-weight: bold; font-size: 11px;")
        self.top_status_label.setText("🟢 Connected")
        self.top_status_label.setStyleSheet("color: #22c55e;")
        self.connect_btn.setText("Disconnect")
        self.create_room_btn.setEnabled(True)
        self.join_room_btn.setEnabled(True)
        self.ping_timer.start(5000)
        self.show_toast("Connected to server!", 2000)

    def on_network_disconnected(self):
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 11px;")
        self.top_status_label.setText("🔴 Disconnected")
        self.top_status_label.setStyleSheet("color: #ef4444;")
        self.connect_btn.setText("Connect")
        self.create_room_btn.setEnabled(False)
        self.join_room_btn.setEnabled(False)
        self.ping_timer.stop()
        self.sync_enabled = False
        self.show_toast("Disconnected from server", 2000)

    def on_room_created(self, code, status):
        self.status_label.setText(f"Room: {code}")
        self.status_label.setStyleSheet("color: #3b82f6; font-weight: bold; font-size: 11px;")
        self.top_status_label.setText(f"🔵 Room: {code}")
        self.top_status_label.setStyleSheet("color: #3b82f6;")
        self.room_code_input.setText(code)
        self.chat_display.append(f"<font color='#5f3dc4'>[System] Room created. Share code: {code}</font>")
        self.show_toast(f"Room {code} created!", 2500)

    def on_room_joined(self, code, status):
        self.status_label.setText(f"Room: {code}")
        self.status_label.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 11px;")
        self.top_status_label.setText(f"🟢 Room: {code} (Connected)")
        self.top_status_label.setStyleSheet("color: #22c55e;")
        self.room_code_input.setText(code)
        self.chat_display.append("<font color='#22c55e'>[System] Connected to partner.</font>")
        self.sync_enabled = True
        self.show_toast("Partner connected!", 2500)
        
        # Share file metadata if already loaded
        self.send_file_metadata()

    def on_join_error(self, message):
        QMessageBox.warning(self, "Room Error", message)
        self.status_label.setText("Connected")
        self.status_label.setStyleSheet("color: #eab308; font-weight: bold; font-size: 11px;")
        self.show_toast(f"Join error: {message}", 3000)

    def on_partner_disconnected(self, status):
        self.status_label.setText("Partner disconnected")
        self.status_label.setStyleSheet("color: #eab308; font-weight: bold; font-size: 11px;")
        self.top_status_label.setText(f"🔵 Room: {self.network.room_code} (Waiting...)")
        self.top_status_label.setStyleSheet("color: #eab308;")
        self.chat_display.append("<font color='#eab308'>[System] Partner disconnected.</font>")
        self.sync_enabled = False
        self.show_toast("Partner disconnected", 2500)

    def on_file_status(self, matched, message):
        if matched:
            self.chat_display.append("<font color='#22c55e'>[System] File verification successful! Watching is synchronized.</font>")
            self.show_toast("File verification successful!", 2500)
        else:
            self.chat_display.append(f"<font color='#e74c3c'>[System] Verification Failed: {message}</font>")
            self.show_toast("File mismatch detected!", 3000)
            QMessageBox.critical(self, "File Mismatch", message)

    def on_latency_updated(self, latency_ms):
        self.latency_label.setText(f"Ping: {int(latency_ms)} ms")

    def join_room(self):
        code = self.room_code_input.text().strip()
        if len(code) == 6 and code.isdigit():
            self.network.join_room(code)
        else:
            QMessageBox.warning(self, "Input Error", "Please enter a valid 6-digit room code.")

    # ----------------- PLAYBACK LOGIC -----------------
    def open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Video File", "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.m4v *.flv *.webm);;All Files (*)"
        )
        if not filepath:
            return

        if not self.vlc_instance:
            QMessageBox.critical(self, "VLC Error", "VLC player not initialized.")
            return

        self.current_filepath = os.path.abspath(filepath)
        self.current_filesize = os.path.getsize(self.current_filepath)
        
        # Setup media
        media = self.vlc_instance.media_new(self.current_filepath)
        self.media_player.set_media(media)
        
        # Direct VLC to output to our frame
        if sys.platform.startswith('win'):
            self.media_player.set_hwnd(int(self.video_widget.winId()))
        elif sys.platform.startswith('linux'):
            self.media_player.set_xwindow(int(self.video_widget.winId()))
        elif sys.platform.startswith('darwin'):
            self.media_player.set_nsobject(int(self.video_widget.winId()))

        # Start brief play then pause to extract duration & initialize renderer
        self.media_player.play()
        
        # Small delay to let media load and extract parameters
        QTimer.singleShot(500, self.finish_media_loading)

    def finish_media_loading(self):
        if not self.media_player:
            return
            
        self.media_player.pause()
        self.is_playing = False
        self.play_btn.setText("▶")
        self.play_btn.setEnabled(True)
        
        # Switch stacked widget to VLC player view (index 1)
        self.stacked_widget.setCurrentIndex(1)
        
        # Get duration in seconds
        duration_ms = self.media_player.get_length()
        self.duration = duration_ms / 1000.0
        
        # Load subtitle automatically if matching srt exists
        base_path, _ = os.path.splitext(self.current_filepath)
        srt_path = base_path + ".srt"
        if os.path.exists(srt_path):
            self.media_player.video_set_subtitle_file(srt_path)
            self.chat_display.append(f"<font color='#5865f2'>[System] Automatically loaded subtitles: {os.path.basename(srt_path)}</font>")
            self.show_toast("Auto-loaded matching subtitles", 2000)

        # Extract resolution if possible
        res_text = ""
        width = self.media_player.video_get_width()
        height = self.media_player.video_get_height()
        if width > 0 and height > 0:
            res_text = f" ({width}x{height})"

        filename_only = os.path.basename(self.current_filepath)
        self.file_label.setText(f"{filename_only}{res_text}")
        self.top_file_label.setText(f"{filename_only}{res_text} • {self.format_time(self.duration)}")
        
        # Update progress tracking
        self.update_timer.start()
        
        # Send details to server
        self.send_file_metadata()
        
        self.show_toast(f"Loaded: {filename_only}", 2500)

    def send_file_metadata(self):
        if self.sync_enabled and self.current_filepath:
            self.network.send_file_info(
                os.path.basename(self.current_filepath),
                self.current_filesize,
                self.duration
            )

    def toggle_play(self):
        if not self.current_filepath:
            return
            
        if self.is_playing:
            self.pause_playback()
            if self.sync_enabled and not self.block_outgoing_sync:
                self.network.send_sync("pause", self.media_player.get_time() / 1000.0)
            self.show_toast("Paused", 1000)
        else:
            self.start_playback()
            if self.sync_enabled and not self.block_outgoing_sync:
                self.network.send_sync("play", self.media_player.get_time() / 1000.0)
            self.show_toast("Playing", 1000)

    def start_playback(self):
        if self.media_player:
            self.media_player.play()
            self.is_playing = True
            self.play_btn.setText("⏸")
            self.hide_timer.start() # Begin autohiding controls

    def pause_playback(self):
        if self.media_player:
            self.media_player.pause()
            self.is_playing = False
            self.play_btn.setText("▶")
            self.hide_timer.stop()
            self.show_controls()

    def change_volume(self, value):
        if self.media_player:
            self.media_player.audio_set_volume(value)
            self.is_muted = (value == 0)
            self.update_volume_icon(value)

    def toggle_fullscreen(self):
        is_fs = self.isFullScreen()
        if is_fs:
            self.showNormal()
            self.show_toast("Window Mode", 1500)
        else:
            self.showFullScreen()
            self.show_toast("Fullscreen Mode (ESC to exit)", 2000)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        # Space bar triggers play/pause
        if key == Qt.Key.Key_Space:
            self.toggle_play()
        # Escape or F exits/enters fullscreen
        elif key == Qt.Key.Key_F:
            self.toggle_fullscreen()
        elif key == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
            self.show_toast("Window Mode", 1500)
        # M toggles mute
        elif key == Qt.Key.Key_M:
            self.toggle_mute()
        # C toggles chat panel
        elif key == Qt.Key.Key_C:
            self.toggle_chat()
        # S opens connection settings
        elif key == Qt.Key.Key_S:
            self.open_settings_dialog()
        # Left arrow seeks back 5s
        elif key == Qt.Key.Key_Left and self.media_player:
            curr_ms = self.media_player.get_time()
            target_ms = max(0, curr_ms - 5000)
            self.media_player.set_time(target_ms)
            if self.sync_enabled and not self.block_outgoing_sync:
                self.network.send_sync("seek", target_ms / 1000.0)
            self.show_toast("Seek -5s", 1000)
        # Right arrow seeks forward 5s
        elif key == Qt.Key.Key_Right and self.media_player:
            curr_ms = self.media_player.get_time()
            target_ms = min(int(self.duration * 1000), curr_ms + 5000)
            self.media_player.set_time(target_ms)
            if self.sync_enabled and not self.block_outgoing_sync:
                self.network.send_sync("seek", target_ms / 1000.0)
            self.show_toast("Seek +5s", 1000)
        else:
            super().keyPressEvent(event)

    # ----------------- SLIDER SEEK LOGIC -----------------
    def on_slider_pressed(self):
        self.ignore_slider_update = True

    def on_slider_moved(self, value):
        # Show dynamic time update in label while dragging
        target_sec = (value / 1000.0) * self.duration
        self.time_label.setText(f"{self.format_time(target_sec)} / {self.format_time(self.duration)}")

    def on_slider_released(self):
        if not self.duration:
            self.ignore_slider_update = False
            return
            
        value = self.time_slider.value()
        target_sec = (value / 1000.0) * self.duration
        
        # Seek local player
        self.media_player.set_time(int(target_sec * 1000.0))
        
        # Sync with partner
        if self.sync_enabled and not self.block_outgoing_sync:
            self.network.send_sync("seek", target_sec)
            
        # Re-enable slider update after a short delay (500ms) to let VLC seek settle
        QTimer.singleShot(500, self.re_enable_slider_update)

    def re_enable_slider_update(self):
        self.ignore_slider_update = False

    def update_player_state(self):
        try:
            if not self.media_player or self.ignore_slider_update:
                return
                
            # Accessing native player functions before media is loaded can cause Access Violations
            media = self.media_player.get_media()
            if not media:
                return
                
            curr_time_ms = self.media_player.get_time()
            if curr_time_ms < 0:
                curr_time_ms = 0
                
            curr_sec = curr_time_ms / 1000.0
            
            # Update text labels
            self.time_label.setText(f"{self.format_time(curr_sec)} / {self.format_time(self.duration)}")
            
            # Update progress slider position
            if self.duration > 0:
                slider_pos = int((curr_sec / self.duration) * 1000)
                self.time_slider.setValue(slider_pos)
        except OSError as e:
            # Handle native C-level exceptions from libVLC gracefully
            logging.warning(f"LibVLC state warning in update loop: {e}")
        except Exception as e:
            logging.error(f"Error in player state update loop: {e}")

    def format_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    # ----------------- REAL-TIME SYNC LOGIC -----------------
    def on_sync_received(self, data):
        """
        Receives sync instructions from partner: play, pause, or seek.
        Includes network latency compensation using half of calculated RTT.
        """
        event = data.get("event")
        if event == "chat":
            self.on_chat_received(data.get("sender"), data.get("message"))
            return
            
        partner_time = data.get("time", 0.0)
        partner_timestamp = data.get("timestamp", time.time())
        
        # Temporary block outgoing sync to avoid echo loops
        self.block_outgoing_sync = True
        
        try:
            if event == "play":
                # Network compensation calculation:
                # Time elapsed since the partner sent the action + RTT/2 latency
                elapsed_network_time = time.time() - partner_timestamp
                compensated_time = partner_time + elapsed_network_time + self.network.latency
                
                logging.info(f"Sync Play received. Compensation applied: {elapsed_network_time + self.network.latency:.3f}s")
                
                # Seek to target and start
                self.media_player.set_time(int(compensated_time * 1000.0))
                self.start_playback()
                
            elif event == "pause":
                logging.info(f"Sync Pause received at: {partner_time}s")
                self.media_player.set_time(int(partner_time * 1000.0))
                self.pause_playback()
                
            elif event == "seek":
                logging.info(f"Sync Seek received to: {partner_time}s")
                
                # Show dynamic Buffering feedback to prevent desync during large seeks
                self.chat_display.append("<font color='#e74c3c'>[System] Buffering sync action...</font>")
                self.media_player.set_time(int(partner_time * 1000.0))
                
                # Buffer for 1 second as required
                def resume_after_buffer():
                    # If local state is playing, continue playing, else stay paused
                    if self.is_playing:
                        self.start_playback()
                    else:
                        self.pause_playback()
                    self.chat_display.append("<font color='#2ecc71'>[System] Buffer sync completed.</font>")
                
                QTimer.singleShot(1000, resume_after_buffer)
        finally:
            # Short timeout before re-enabling outgoing syncs to let VLC state settle
            QTimer.singleShot(500, self.unblock_sync)

    def unblock_sync(self):
        self.block_outgoing_sync = False

    # ----------------- CHAT PANEL LOGIC -----------------
    def send_chat_message(self):
        msg = self.chat_input.text().strip()
        if not msg:
            return
            
        self.chat_input.clear()
        self.chat_display.append(f"<b>You:</b> {msg}")
        
        if self.sync_enabled:
            self.network.send_chat(msg)

    def on_chat_received(self, sender, message):
        self.chat_display.append(f"<b>{sender}:</b> {message}")
        if not self.chat_container.isVisible():
            self.show_toast(f"New message from {sender}", 2000)

    def resizeEvent(self, event):
        if hasattr(self, 'toast') and self.toast.isVisible():
            x = (self.width() - self.toast.width()) // 2
            y = 50
            self.toast.move(x, y)
        super().resizeEvent(event)

    def on_shortcut_space(self):
        if not self.chat_input.hasFocus():
            self.toggle_play()

    def on_shortcut_f(self):
        if not self.chat_input.hasFocus():
            self.toggle_fullscreen()

    def on_shortcut_m(self):
        if not self.chat_input.hasFocus():
            self.toggle_mute()

    def on_shortcut_c(self):
        if not self.chat_input.hasFocus():
            self.toggle_chat()

    def on_shortcut_s(self):
        if not self.chat_input.hasFocus():
            self.open_settings_dialog()

    def on_shortcut_left(self):
        if not self.chat_input.hasFocus() and self.media_player:
            curr_ms = self.media_player.get_time()
            target_ms = max(0, curr_ms - 5000)
            self.media_player.set_time(target_ms)
            if self.sync_enabled and not self.block_outgoing_sync:
                self.network.send_sync("seek", target_ms / 1000.0)
            self.show_toast("Seek -5s", 1000)

    def on_shortcut_right(self):
        if not self.chat_input.hasFocus() and self.media_player:
            curr_ms = self.media_player.get_time()
            target_ms = min(int(self.duration * 1000), curr_ms + 5000)
            self.media_player.set_time(target_ms)
            if self.sync_enabled and not self.block_outgoing_sync:
                self.network.send_sync("seek", target_ms / 1000.0)
            self.show_toast("Seek +5s", 1000)

    def closeEvent(self, event):
        # Shut down player and disconnect socket on exit
        if self.media_player:
            self.media_player.stop()
            self.media_player.release()
        if self.vlc_instance:
            self.vlc_instance.release()
        self.network.disconnect_server()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
