import os
import random
import string
import time
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ourvideo-secret-key-12345')

# Enable CORS for socket connection
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# In-memory database
# room_code (str) -> {
#    "users": list of sids (max 2),
#    "files": { sid: {filename, size, duration} }
# }
ROOMS = {}
# sid -> room_code
SID_TO_ROOM = {}

def generate_room_code():
    while True:
        code = "".join(random.choices(string.digits, k=6))
        if code not in ROOMS:
            return code

@app.route('/')
def index():
    return jsonify({"status": "healthy", "service": "ourvideo-server"})

@socketio.on('ping_server')
def handle_ping(data):
    """Echo ping to calculate latency"""
    emit('pong_client', {"client_time": data.get("client_time")})

@socketio.on('create_room')
def handle_create_room():
    sid = request.sid
    # Clean up user's old room if any
    handle_disconnect()
    
    room_code = generate_room_code()
    ROOMS[room_code] = {
        "users": [sid],
        "files": {}
    }
    SID_TO_ROOM[sid] = room_code
    
    join_room(room_code)
    emit('room_created', {
        "room_code": room_code,
        "status": "Waiting for partner..."
    })

@socketio.on('join_room')
def handle_join_room(data):
    sid = request.sid
    room_code = data.get("room_code")
    
    if not room_code:
        emit('join_error', {"message": "Invalid room code."})
        return
        
    if room_code not in ROOMS:
        emit('join_error', {"message": "Room not found."})
        return
        
    room = ROOMS[room_code]
    if len(room["users"]) >= 2:
        emit('join_error', {"message": "Room is full (max 2 users)."})
        return
        
    # Clean up user's old room if any
    handle_disconnect()
    
    room["users"].append(sid)
    SID_TO_ROOM[sid] = room_code
    join_room(room_code)
    
    # Notify both room members
    emit('room_joined', {
        "room_code": room_code,
        "status": "Partner Connected"
    }, to=room_code)
    
    # Request the host (first user) to report their current playback state
    host_sid = room["users"][0]
    emit('request_playback_state', {}, to=host_sid)

@socketio.on('file_info')
def handle_file_info(data):
    sid = request.sid
    room_code = SID_TO_ROOM.get(sid)
    if not room_code or room_code not in ROOMS:
        return
        
    room = ROOMS[room_code]
    room["files"][sid] = {
        "filename": data.get("filename"),
        "size": data.get("size"),
        "duration": data.get("duration")
    }
    
    # If we have 2 users in the room, perform file verification
    if len(room["users"]) == 2:
        user1_sid, user2_sid = room["users"]
        file1 = room["files"].get(user1_sid)
        file2 = room["files"].get(user2_sid)
        
        if file1 and file2:
            # Check matching filename, file size, and duration
            # Use small tolerance for duration (e.g., 2 seconds) due to player metadata differences
            name_match = os.path.basename(file1["filename"]) == os.path.basename(file2["filename"])
            size_match = file1["size"] == file2["size"]
            duration_match = abs(float(file1["duration"]) - float(file2["duration"])) < 2.0
            
            if name_match and size_match and duration_match:
                emit('file_status', {"match": True}, to=room_code)
            else:
                emit('file_status', {
                    "match": False,
                    "message": "Files don't match. Please use same video file."
                }, to=room_code)

@socketio.on('sync_event')
def handle_sync_event(data):
    """
    data format:
    {
      "event": "play" | "pause" | "seek",
      "time": float (seconds),
      "timestamp": float (unix timestamp)
    }
    """
    sid = request.sid
    room_code = SID_TO_ROOM.get(sid)
    if not room_code:
        return
        
    # Broadcast to everyone else in the room
    emit('sync_receive', data, to=room_code, include_self=False)

@socketio.on('report_playback_state')
def handle_report_playback_state(data):
    sid = request.sid
    room_code = SID_TO_ROOM.get(sid)
    if not room_code or room_code not in ROOMS:
        return
    # Forward the host's state to the newly joined partner
    emit('set_playback_state', data, to=room_code, include_self=False)


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    room_code = SID_TO_ROOM.pop(sid, None)
    if not room_code or room_code not in ROOMS:
        return
        
    room = ROOMS[room_code]
    if sid in room["users"]:
        room["users"].remove(sid)
    room["files"].pop(sid, None)
    
    # Leave room
    leave_room(room_code)
    
    if len(room["users"]) == 0:
        # Delete room if empty
        ROOMS.pop(room_code, None)
    else:
        # Notify the remaining user
        emit('partner_disconnected', {
            "status": "Partner disconnected. Waiting..."
        }, to=room_code)

if __name__ == '__main__':
    # Using gevent WebSocket server
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
