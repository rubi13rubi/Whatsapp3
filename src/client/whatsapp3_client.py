#___________________________________________________________
#main functions
#___________________________________________________________
import os
try: os.add_dll_directory(os.getcwd()) #add working directory to find dll
except: pass #not windows
import time
import socket
import json
from math import ceil, sqrt
import threading
import pyaudio
import opuslib
from collections import deque
import numpy as np
import uuid

class Whatsapp3Client:

    # audio parameters
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000 # 16000 Hz (samples per second)
    CHUNK = 320 # 320 samples per frame (640 bytes), 20 ms per frame
    # jitter buffer parameters
    JITTER_BUFFER_OPTIMAL = 4
    JITTER_BUFFER_MAX = 8
    # buffer states
    BUFFER_WAIT_FILL = 0
    BUFFER_RUNNING = 1
    BUFFER_WAIT_DRAIN = 2

    def __init__(self):
        """
        Initializes the client backend and static settings.
        Dynamic settings (server IP, port, username) are initialized on connect, and reset on disconnect.
        """
        # Server params (initialized on connect)
        self.server_ip = None
        self.chat_port = None
        self.chat_socket = None
        self._recv_buffer = b"" # stores incomplete JSON lines between recv calls
        self.file_port = None # File socket not declared as a new socket is used for each file transfer
        self.voice_port = None
        self.voice_socket = None
        self.username = None
        self.running = False
        # jitter buffer setup
        self.jitter_buffer = deque()
        self.buffer_state = self.BUFFER_WAIT_FILL
        # audio and codec setup
        self.audio = pyaudio.PyAudio()
        self.encoder = opuslib.Encoder(self.RATE, self.CHANNELS, opuslib.APPLICATION_AUDIO)
        self.decoder = opuslib.Decoder(self.RATE, self.CHANNELS)
        self.voice_enabled = False
        self.gain = 1.0
        self.muted = False
        self.voice_id = uuid.uuid4().bytes # Unique ID for this client's voice data, to identify packets

        # Callbacks (will be set by the GUI or other interface layer)
        self.on_chat_message = None     # func(sender, content)
        self.on_system_message = None   # func(content)
        self.on_file_notice = None      # func(sender, filename)
        self.on_disconnect = None       # func(forced)

    def connect(self, server_ip, chat_port, username):
        """
        Connects to the server and initializes the chat socket.
        Args:
            server_ip (str): The IP address of the server to connect to.
            chat_port (int): The port number for the chat socket.
            username (str): The username for the client.
        """
        self.server_ip = socket.gethostbyname(server_ip) # Resolve hostname to IP (in case it is a domain name)
        self.chat_port = chat_port
        self.username = username
        # create chat socket and connect to server
        self.chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.chat_socket.settimeout(5) # 5 second timeout for connection attempts
        try:
            self.chat_socket.connect((self.server_ip, self.chat_port))
            # Connection handshake process
            handshake = {
                    "type": "connect",
                    "username": self.username,
                    "voice_id": self.voice_id.hex()
                }
            self._send_json(handshake)
            reader = self.chat_socket.makefile('r', encoding='utf-8') # This simplifies reading lines of JSON data from the socket.
            # Handshake response
            response_line = reader.readline()
            if not response_line:
                self.disconnect(reason = "Server is not responding.")
                return
            response = json.loads(response_line)
            if response.get("status") == "ok":
                self.file_port = response.get("file_port")
                self.voice_port = response.get("voice_port")
                # Start the message listener thread after successful connection
                self.running = True
                threading.Thread(target=self._receive_loop, daemon=True).start()
                return
            else:
                self.disconnect(reason = "Connection rejected by server: " + response.get("reason", "Unknown reason"))
                return
        except Exception as e:
            self.disconnect(reason = "Error connecting to server. Error details: " + str(e))
            return


    def _send_json(self, data_dict):
        """
        Send a JSON-encoded message through the chat socket.
        Args:
            data_dict (dict): The data to send as a JSON object.
        """
        if self.chat_socket:
            try:
                json_str = json.dumps(data_dict) + "\n" # Add newline as a message delimiter
                self.chat_socket.sendall(json_str.encode('utf-8'))
            except Exception as e:
                self.disconnect(reason = "Error sending data: " + str(e))

    def disconnect(self, reason = None):
        """
        Disconnects from the server and cleans up resources.
        If reason is none, it means the disconnection was intentional,
        otherwise it was due to an error or server issue.
        Args:
            reason (str, optional): The reason for disconnection, if any.
        """

        self.server_ip = None
        self.chat_port = None
        self.file_port = None
        self.voice_port = None
        self.username = None
        self.buffer_state = self.BUFFER_WAIT_FILL
        self.jitter_buffer.clear()
        self.voice_enabled = False
        self.running = False

        if self.chat_socket:
            try: self.chat_socket.close()
            except: pass
            self.chat_socket = None
        if self.voice_socket:
            try: self.voice_socket.close()
            except: pass
            self.voice_socket = None
        if self.on_disconnect:
            self.on_disconnect(reason)
    
    def send_chat_message(self, content):
        """
        Sends a chat message to the server.
        Args:
            content (str): The text content of the chat message to send.
        """
        message = {
            "type": "chat",
            "content": content
        }
        self._send_json(message)

    def _receive_loop(self):
        """
        The main loop for receiving messages from the server.
        This runs in a separate thread and processes incoming messages.
        """
        buffer = "" # Buffer to accumulate incoming data until we have complete JSON lines
        self.chat_socket.settimeout(1) # Set a timeout for the socket to allow periodic checks of the running flag
        while self.running:
            try:
                chunk = self.chat_socket.recv(4096).decode('utf-8')
                if not chunk: # Empty data means the server has closed the connection
                    self.disconnect(reason = "Server has closed the connection.")
                    break
                buffer += chunk # Append new data to the buffer
                while '\n' in buffer: # Process all complete lines in the buffer
                    line, buffer = buffer.split('\n', 1) # Split off the first complete line
                    if line.strip(): # Ignore empty lines
                        try:
                            data = json.loads(line)
                            self._handle_message(data)
                        except json.JSONDecodeError:
                            self.disconnect(reason = "Received malformed data from server.")
                            return
                
            except socket.timeout:
                continue # Ignore timeouts and check the running flag again
            except Exception as e:
                self.disconnect(reason = "Error receiving data: " + str(e))
                break
    
    def _handle_message(self, message):
        """
        Handles an incoming message from the server based on its type.
        Args:
            message (dict): The message data parsed from JSON.
        """
        msg_type = message.get("type")
        if msg_type == "chat":
            sender = message.get("sender")
            content = message.get("content")
            if self.on_chat_message:
                self.on_chat_message(sender, content)
        elif msg_type == "system":
            content = message.get("content")
            if self.on_system_message:
                self.on_system_message(content)
        elif msg_type == "file_notice":
            sender = message.get("sender")
            filename = message.get("filename")
            if self.on_file_notice:
                self.on_file_notice(sender, filename)