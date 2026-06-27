# ourvideo

A synchronized video player for 2 people (couples) to watch movies together in real-time.

## Features

- **Decentralized Playback**: Video files are **never** uploaded. Playback is performed locally while only play/pause/seek synchronization signals are transmitted.
- **VLC Core**: Built with libVLC bindings (`python-vlc`), offering native support for all video formats (MP4, MKV, AVI, HEVC, 10-bit) with hardware acceleration.
- **Real-Time Sync**: Real-time room server utilizing WebSockets via Flask-SocketIO.
- **Latency Compensation**: RTT-based sync adjustments keeping users within `<500ms` difference.
- **Verification System**: Validates file metadata (filename, file size, duration) to ensure both clients are watching identical files before synchronization starts.
- **In-App Chat**: Quick sidebar drawer for messaging.

---

## Setup & Running Locally

### Prerequisites

1. **Python 3.8+** must be installed.
2. **VLC Media Player** must be installed on your Windows system.
   - **Important**: Your VLC installation architecture (32-bit or 64-bit) **must** match your Python architecture. For most users, this means installing 64-bit VLC for 64-bit Python.

### Installation

Clone this repository, navigate to the folder, and install dependencies:

```bash
pip install -r requirements.txt
```

### 1. Run the Server

Start the Flask-SocketIO synchronization server locally:

```bash
python server/app.py
```
By default, the server runs on `http://localhost:5000`.

### 2. Run the Client(s)

Start the PyQt6 desktop client:

```bash
python client/main.py
```

*To test locally, you can open two instances of the client on your PC, connect to `http://localhost:5000`, have one user click **Create Room**, copy the 6-digit code, paste it into the other client, and click **Join Room**.*

---

## Deployment to Render.com

Render's free tier is fully capable of running this server.

1. **Create a Web Service** on Render.
2. Link your GitHub repository.
3. Configure the following service settings:
   - **Environment**: `Python`
   - **Build Command**: `pip install -r server/requirements.txt`
   - **Start Command**: `python server/app.py`
4. Deploy the service. Once live, copy your service URL (e.g., `https://ourvideo-sync.onrender.com`) and paste it into the client application.

---

## Building the `.exe` Executable

To compile the client into a standalone Windows executable (`ourvideo.exe`):

```bash
python build_client.py
```
This generates a single executable inside the `dist` folder.

*Note: The end-users running the `.exe` still need VLC Player installed on their system so that the app can access `libvlc.dll`.*
