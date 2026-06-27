# ourvideo - Developer & AI Agent Guide (AGENTS.md)

Welcome! This guide outlines the system architecture, codebases, file structures, synchronization protocols, and development quirks of the **ourvideo** co-watching platform. Use this document to onboard developers or guide AI coding models reviewing or extending the project.

---

## 1. Project Directory Structure

```text
ourvideo/
├── client/
│   └── main.py             # Desktop Client (PyQt6 + python-vlc + python-socketio)
├── server/
│   └── app.py              # Flask-SocketIO Backend Server (latency compensation)
├── build_client.bat        # Compiles Python client to standalone executable (PyInstaller)
├── push_to_github.bat      # Helper script for remote git repository push via browser-auth
├── README.md               # User-facing project overview
└── AGENTS.md               # This system architecture & developer guide (onboarding)
```

---

## 2. Server Architecture (`/server/app.py`)

The server is a lightweight **Flask-SocketIO** (WebSockets) coordinator. It does not store user accounts or database entries. Instead, it manages temporary, in-memory sync rooms.

### Key Data Structures (In-Memory)
* `ROOMS`: A dictionary mapping room codes (e.g. `12345`) to room data:
  ```json
  {
    "users": ["sid_1", "sid_2"],
    "files": {
      "sid_1": {"filename": "movie.mp4", "size": 1048576, "duration": 7200.0},
      "sid_2": {"filename": "movie.mp4", "size": 1048576, "duration": 7200.0}
    }
  }
  ```
* `SID_TO_ROOM`: Fast lookup mapping user Socket.io session IDs (`sid`) to active room codes.

### Key Protocols
1. **Room Creation**: Users send `create_room`. Server generates a unique 5-character alphanumeric room code, registers the user, and puts them in a WebSocket room.
2. **Room Joining & Initial State Catch-up Sync**:
   * When a second user joins, the server sends a `request_playback_state` event specifically to the **Host** (the first user in the room).
   * The Host reports their current timestamp and playing/paused state via `report_playback_state`.
   * The server relays this state to the newcomer via `set_playback_state`, letting them jump to the host's exact position instantly.
3. **File Verification**: When both users join and upload file info, the server compares the name, size, and duration. It emits `file_status` (`match: true` or `match: false`) so clients get visual warnings if they are playing different files.
4. **Disconnect Cleanups**: If a client disconnects, the server leaves the room, notifies the remaining partner, and deletes the room from memory if both users have left.

---

## 3. Client Architecture (`/client/main.py`)

The client is a premium desktop video player built with **PyQt6** and **python-vlc** bindings. It implements a beautiful, dark-themed, glassmorphic layout.

### UI Components Hierarchy
* `MainWindow` (QMainWindow):
  * **Top Header Glass Bar**: Shows brand logo, loaded video metadata, ping latency, connection status dot, and a clipboard copy button.
  * **Stacked Pages (Empty vs Player)**:
    * Index 0: `EmptyStateWidget` (cinema-themed landing screen with CTA drag-and-drop / Select Video button).
    * Index 1: `video_container` frame (holds the player output widget).
  * **Floating Toast System**: `ToastNotification` overlay banner that fades in/out on the top center of the screen to notify actions (seek times, connection events, volumes).
  * **Chat Sidebar Panel**: Collapsible panel for room text chat (toggled with `💬` or keybind `C`).
  * **Bottom Netflix-Style Control Bar**: Hosts Play/Pause, Open File, Settings Modal trigger, chat toggle, volume button (with dynamic icons `🔇`/`🔈`/`🔉`/`🔊`), and the timeline slider.

### Critical Custom Subclasses & Handlers
1. **`ClickableSlider`** (subclassed from `QSlider`):
   * Standard Qt sliders only allow page-step movements on click.
   * `ClickableSlider` overrides mouse presses (`mousePressEvent`), moves (`mouseMoveEvent`), and releases (`mouseReleaseEvent`).
   * It calculates the click coordinate relative to the slider width, translates it to absolute value, and triggers seeks immediately on mouse release. This permits YouTube-like click-scrubbing.
2. **`ToastNotification`** (subclassed from `QLabel`):
   * Uses `QGraphicsOpacityEffect` and `QPropertyAnimation` to fade in, remain visible, and fade out smoothly.
3. **Window state change (`changeEvent`)**:
   * Overridden to detect fullscreen transitions. When entering fullscreen, it runs a 200ms delayed trigger to hide controls (Netflix-style autohide after 3 seconds).
   * In windowed mode, autohide is disabled to keep layouts stable and prevent native VLC Win32 handle overlaps.
4. **Global Keybind Shortcuts (`QShortcut`)**:
   * Bound to window scope so they work even if sliders or buttons have active focus.
   * Shortcut keys: `Space` (Play/Pause), `Left/Right` (Seek 5s), `M` (Mute), `F` (Fullscreen), `C` (Chat Drawer), `S` (Settings Modal).
   * They automatically bypass actions if the chat input box has keyboard focus (`chat_input.hasFocus()`).

---

## 4. Latency & Clock Synchronization Protocol

To compensate for network latency during real-time seeking:
* Every 5 seconds, the client pings the server to calculate **Round-Trip Time (RTT)**.
  $$\text{Latency} = \text{RTT} / 2$$
* When User A performs a seek, play, or pause, the payload includes the video time and User A's local UNIX machine timestamp.
* When User B receives it, User B calculates the latency offset:
  $$\text{Latency Offset} = (\text{Current UNIX Time} - \text{Sender's UNIX Timestamp}) + \text{Latency}$$
* User B seeks to:
  $$\text{Target Video Time} + \text{Latency Offset}$$
* A 1-second buffer pause is applied to let the VLC decoder buffer the seek and stabilize before resuming playback.

---

## 5. Deployment & System Quirks

### VLC Binary Architecture Quirks
* **Architecture Mismatch**: On Windows, the client requires the VLC desktop application to be installed. Crucially, the **architecture of Python and VLC MUST match**. If you run 64-bit Python, you must install 64-bit VLC. If you run 32-bit Python, you must install 32-bit VLC. Otherwise, `vlc.Instance()` will fail to load with `OSError`.
* **Hardware Acceleration**: Windows VLC initialization fails on certain older graphics drivers if hardware decoding flags (like `--d3d11-hw-dec=1`) are forced. The code uses `--avcodec-hw=any` for broad driver compatibility.
* **C-level Access Violations**: Calling native methods like `.get_time()` on the player while it is in an uninitialized state or actively seeking (asynchronous seek) can cause C-level Access Violations (Segmentation Faults). We guard the update loop by checking `self.media_player.get_media()`, delaying update timers by 500ms during seeks, and wrapping the loop in `try...except OSError:` blocks.

### Server Deployment
* The backend is deployed on Render at: `https://ourvideosrv.onrender.com`.
* **Render Free Tier Spin Down**: The container goes to sleep after 15 minutes of inactivity. When a client first connects, it might experience a timeout due to Render's cold start (50s wakeup time). We set the client's `wait_timeout=30` to tolerate cold starts. Visiting the Render URL via a browser wakes up the instance instantly.
