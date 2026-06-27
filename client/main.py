import os
import sys
import time
import socketio
import logging
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt, QThread
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QSlider, QFileDialog, QMessageBox,
    QTextEdit, QSplitter, QFrame, QSizePolicy
)
from PyQt6.QtGui import QFont, QColor, QPalette, QKeyEvent

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
    background-color: #1e1f22;
}
QWidget {
    color: #dbdee1;
    font-family: "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 13px;
}
QFrame#controlBar, QFrame#topBar {
    background-color: #2b2d31;
    border-radius: 8px;
}
QPushButton {
    background-color: #5865f2;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #4752c4;
}
QPushButton:pressed {
    background-color: #3c45a5;
}
QPushButton:disabled {
    background-color: #4f545c;
    color: #72767d;
}
QPushButton#playBtn, QPushButton#fullscreenBtn {
    background-color: #313338;
    border: 1px solid #4e5058;
}
QPushButton#playBtn:hover, QPushButton#fullscreenBtn:hover {
    background-color: #35373c;
}
QLineEdit {
    background-color: #1e1f22;
    border: 1px solid #3f4147;
    border-radius: 4px;
    padding: 4px 8px;
    color: #f2f3f5;
}
QLineEdit:focus {
    border: 1px solid #5865f2;
}
QSlider::groove:horizontal {
    border: 1px solid #2b2d31;
    height: 6px;
    background: #4e5058;
    margin: 2px 0;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #5865f2;
    border: none;
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #7289da;
}
QSlider::add-page:horizontal {
    background: #4e5058;
}
QSlider::sub-page:horizontal {
    background: #5865f2;
}
QTextEdit {
    background-color: #2b2d31;
    border: 1px solid #3f4147;
    border-radius: 6px;
    color: #dbdee1;
}
"""

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
            '--avcodec-hw=any', # Use hardware decoder
            '--d3d11-hw-dec=1'  # Direct3D11 hardware acceleration
        ]
        try:
            self.vlc_instance = vlc.Instance(args)
            self.media_player = self.vlc_instance.media_player_new()
        except Exception as e:
            QMessageBox.critical(self, "VLC Init Error", f"Failed to initialize VLC: {e}")

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ----------------- TOP BAR (CONNECTION / ROOMS) -----------------
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 5, 10, 5)

        self.server_url_input = QLineEdit("https://ourvideosrv.onrender.com")
        self.server_url_input.setPlaceholderText("Server URL")
        self.server_url_input.setFixedWidth(200)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)

        self.create_room_btn = QPushButton("Create Room")
        self.create_room_btn.setEnabled(False)
        self.create_room_btn.clicked.connect(self.network.create_room)

        self.room_code_input = QLineEdit()
        self.room_code_input.setPlaceholderText("6-digit Code")
        self.room_code_input.setFixedWidth(100)
        self.room_code_input.setMaxLength(6)

        self.join_room_btn = QPushButton("Join Room")
        self.join_room_btn.setEnabled(False)
        self.join_room_btn.clicked.connect(self.join_room)

        self.status_label = QLabel("Status: Disconnected")
        self.status_label.setStyleSheet("color: #ff3333; font-weight: bold;")
        
        self.latency_label = QLabel("Ping: -- ms")
        self.latency_label.setStyleSheet("color: #72767d;")

        top_layout.addWidget(QLabel("Server:"))
        top_layout.addWidget(self.server_url_input)
        top_layout.addWidget(self.connect_btn)
        top_layout.addWidget(QFrame()) # spacer
        top_layout.addWidget(self.create_room_btn)
        top_layout.addWidget(self.room_code_input)
        top_layout.addWidget(self.join_room_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.latency_label)
        top_layout.addWidget(self.status_label)

        main_layout.addWidget(top_bar)

        # ----------------- CENTER BODY (PLAYER & CHAT SPLIT) -----------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Video player container
        self.video_container = QWidget()
        self.video_container.setStyleSheet("background-color: black; border-radius: 8px;")
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        # Under windows, we pass the handle of the video widget to VLC
        self.video_widget = QFrame()
        self.video_widget.setStyleSheet("background-color: black;")
        video_layout.addWidget(self.video_widget)
        
        splitter.addWidget(self.video_container)
        splitter.setStretchFactor(0, 4) # 80% width

        # Right side: Chat panel (300px width limit)
        chat_container = QWidget()
        chat_container.setFixedWidth(300)
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("Welcome to ourvideo! Connect to a server and join/create a room to chat.")
        
        chat_input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type message...")
        self.chat_input.returnPressed.connect(self.send_chat_message)
        
        self.send_chat_btn = QPushButton("Send")
        self.send_chat_btn.clicked.connect(self.send_chat_message)
        
        chat_input_layout.addWidget(self.chat_input)
        chat_input_layout.addWidget(self.send_chat_btn)
        
        chat_layout.addWidget(QLabel("<b>Room Chat</b>"))
        chat_layout.addWidget(self.chat_display)
        chat_layout.addLayout(chat_input_layout)
        
        splitter.addWidget(chat_container)
        splitter.setStretchFactor(1, 1) # 20% width
        
        main_layout.addWidget(splitter, stretch=1)

        # ----------------- BOTTOM BAR (CONTROLS) -----------------
        control_bar = QFrame()
        control_bar.setObjectName("controlBar")
        control_layout = QVBoxLayout(control_bar)
        control_layout.setContentsMargins(10, 10, 10, 10)

        # Progress slider & Time label row
        progress_layout = QHBoxLayout()
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 1000)
        self.time_slider.sliderPressed.connect(self.on_slider_pressed)
        self.time_slider.sliderMoved.connect(self.on_slider_moved)
        self.time_slider.sliderReleased.connect(self.on_slider_released)
        
        self.time_label = QLabel("00:00:00 / 00:00:00")
        
        progress_layout.addWidget(self.time_slider)
        progress_layout.addWidget(self.time_label)
        control_layout.addLayout(progress_layout)

        # Controls buttons row
        buttons_layout = QHBoxLayout()
        
        self.open_file_btn = QPushButton("Open File")
        self.open_file_btn.clicked.connect(self.open_file)
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("playBtn")
        self.play_btn.setFixedWidth(50)
        self.play_btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setEnabled(False)

        self.file_label = QLabel("No File Selected")
        self.file_label.setStyleSheet("color: #b5bac1;")
        self.file_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.valueChanged.connect(self.change_volume)
        
        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.setObjectName("fullscreenBtn")
        self.fullscreen_btn.setFixedWidth(40)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)

        buttons_layout.addWidget(self.open_file_btn)
        buttons_layout.addWidget(self.play_btn)
        buttons_layout.addWidget(self.file_label)
        buttons_layout.addWidget(QLabel("Vol:"))
        buttons_layout.addWidget(self.volume_slider)
        buttons_layout.addWidget(self.fullscreen_btn)
        
        control_layout.addLayout(buttons_layout)
        main_layout.addWidget(control_bar)

        # Set main widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

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
        self.status_label.setText("Connected (No Room)")
        self.status_label.setStyleSheet("color: #f1c40f; font-weight: bold;")
        self.connect_btn.setText("Disconnect")
        self.create_room_btn.setEnabled(True)
        self.join_room_btn.setEnabled(True)
        self.ping_timer.start(5000)

    def on_network_disconnected(self):
        self.status_label.setText("Status: Disconnected")
        self.status_label.setStyleSheet("color: #ff3333; font-weight: bold;")
        self.connect_btn.setText("Connect")
        self.create_room_btn.setEnabled(False)
        self.join_room_btn.setEnabled(False)
        self.ping_timer.stop()
        self.sync_enabled = False

    def on_room_created(self, code, status):
        self.status_label.setText(f"Room: {code} | {status}")
        self.status_label.setStyleSheet("color: #3498db; font-weight: bold;")
        self.room_code_input.setText(code)
        self.chat_display.append("<font color='#5865f2'>[System] Room created. Share the code with your partner!</font>")

    def on_room_joined(self, code, status):
        self.status_label.setText(f"Room: {code} | {status}")
        self.status_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
        self.room_code_input.setText(code)
        self.chat_display.append("<font color='#2ecc71'>[System] Connected to partner.</font>")
        self.sync_enabled = True
        
        # Share file metadata if already loaded
        self.send_file_metadata()

    def on_join_error(self, message):
        QMessageBox.warning(self, "Room Error", message)
        self.status_label.setText("Connected (No Room)")
        self.status_label.setStyleSheet("color: #f1c40f; font-weight: bold;")

    def on_partner_disconnected(self, status):
        self.status_label.setText(f"Room: {self.network.room_code} | {status}")
        self.status_label.setStyleSheet("color: #f1c40f; font-weight: bold;")
        self.chat_display.append("<font color='#f1c40f'>[System] Partner disconnected.</font>")
        self.sync_enabled = False

    def on_file_status(self, matched, message):
        if matched:
            self.chat_display.append("<font color='#2ecc71'>[System] File verification successful! Watching is synchronized.</font>")
        else:
            self.chat_display.append(f"<font color='#e74c3c'>[System] Verification Failed: {message}</font>")
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
        self.media_player.pause()
        self.is_playing = False
        self.play_btn.setText("▶")
        self.play_btn.setEnabled(True)
        
        # Get duration in seconds
        duration_ms = self.media_player.get_length()
        self.duration = duration_ms / 1000.0
        
        # Load subtitle automatically if matching srt exists
        base_path, _ = os.path.splitext(self.current_filepath)
        srt_path = base_path + ".srt"
        if os.path.exists(srt_path):
            self.media_player.video_set_subtitle_file(srt_path)
            self.chat_display.append(f"<font color='#5865f2'>[System] Automatically loaded subtitles: {os.path.basename(srt_path)}</font>")

        # Extract resolution if possible
        tracks = self.media_player.video_get_track_description()
        # Fallback description
        res_text = ""
        width = self.media_player.video_get_width()
        height = self.media_player.video_get_height()
        if width > 0 and height > 0:
            res_text = f" ({width}x{height})"

        self.file_label.setText(f"{os.path.basename(self.current_filepath)}{res_text}")
        
        # Update progress tracking
        self.update_timer.start()
        
        # Send details to server
        self.send_file_metadata()

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
        else:
            self.start_playback()
            if self.sync_enabled and not self.block_outgoing_sync:
                self.network.send_sync("play", self.media_player.get_time() / 1000.0)

    def start_playback(self):
        self.media_player.play()
        self.is_playing = True
        self.play_btn.setText("⏸")

    def pause_playback(self):
        self.media_player.pause()
        self.is_playing = False
        self.play_btn.setText("▶")

    def change_volume(self, value):
        if self.media_player:
            self.media_player.audio_set_volume(value)

    def toggle_fullscreen(self):
        # Simply toggle window state or VLC fullscreen mode
        is_fs = self.isFullScreen()
        if is_fs:
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event: QKeyEvent):
        # Space bar triggers play/pause
        if event.key() == Qt.Key.Key_Space:
            self.toggle_play()
        # Escape exits fullscreen
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
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
            
        self.ignore_slider_update = False

    def update_player_state(self):
        if not self.media_player or self.ignore_slider_update:
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
