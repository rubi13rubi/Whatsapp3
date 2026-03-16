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
        self.on_new_client = None       # func(new_username)
        self.on_disconnected_client = None  # func(disconnected_username)
        self.on_file_notice = None      # func(sender, filename)
        self.on_disconnect = None       # func(forced)
        self.on_connect = None          # func(clientnumber)

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
                self.disconnect(reason = "no_response")
                return
            response = json.loads(response_line)
            if response.get("status") == "ok":
                self.file_port = int(response.get("file_port"))
                self.voice_port = int(response.get("voice_port"))
                # Start the message listener thread after successful connection
                self.running = True
                threading.Thread(target=self._receive_loop, daemon=True).start()
                if self.on_connect:
                    self.on_connect(response.get("client_number"))
                return
            else:
                if response.get("reason") == "username_taken":
                    self.disconnect(reason = "username_taken")
                else: self.disconnect(reason = "connection_error")
                return
        except Exception as e:
            self.disconnect(reason = "connection_error", exception = e)
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
                self.disconnect(reason = "send_error", exception = e)

    def disconnect(self, reason = None, exception = None):
        """
        Disconnects from the server and cleans up resources.
        If reason is none, it means the disconnection was intentional,
        otherwise it was due to an error or server issue.
        Args:
            reason (str, optional): Code describing the reason for disconnection, which can be used by the GUI to display an appropriate message to the user. Possible codes:
                - "no_response": The server did not respond during connection or file transfer attempts.
                - "closed_by_server": The server closed the connection.
                - "username_taken": The username provided is already in use by another client.
                - "malformed_data": Received data from the server was not valid JSON.
                - "connection_error": Generic error while trying to connect to the server.
                - "send_error": Generic error while sending data to the server.
                - "receive_error": Generic error while receiving data from the server.  
            exception (Exception, optional): The exception that caused the disconnection, if applicable. This can be used for logging or debugging purposes.
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
            self.on_disconnect(reason, exception)
    
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
                    self.disconnect(reason = "closed_by_server")
                    break
                buffer += chunk # Append new data to the buffer
                while '\n' in buffer: # Process all complete lines in the buffer
                    line, buffer = buffer.split('\n', 1) # Split off the first complete line
                    if line.strip(): # Ignore empty lines
                        try:
                            data = json.loads(line)
                            self._handle_message(data)
                        except json.JSONDecodeError:
                            self.disconnect(reason = "malformed_data")
                            return
                
            except socket.timeout:
                continue # Ignore timeouts and check the running flag again
            except Exception as e:
                self.disconnect(reason = "receive_error", exception = e)
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
        elif msg_type == "new_client":
            new_username = message.get("username")
            if self.on_new_client:
                self.on_new_client(new_username)
        elif msg_type == "disconnected_client":
            disconnected_username = message.get("username")
            if self.on_disconnected_client:
                self.on_disconnected_client(disconnected_username)
        elif msg_type == "file_notice":
            sender = message.get("sender")
            filename = message.get("filename")
            if self.on_file_notice:
                self.on_file_notice(sender, filename)

    def send_file(self, filepath, update_callback = None):
        """
        Initiates a file transfer to the server for the specified file.
        Args:
            filepath (str): The path to the file to be sent.
            update_callback (function, optional): A function to be called with progress updates during the file transfer.
        Returns:
            dict: A dictionary containing the result of the file transfer attempt, with keys:
                - "type": A string indicating the result type, which can be:
                    - "not_connected": The client is not connected to a server.
                    - "file_not_found": The specified file does not exist.
                    - "no_response": The server did not respond to the file transfer request.
                    - "transfer_error": An error occurred during the file transfer process.
                    - "transfer_reject": The server rejected the file transfer.
                    - "success": The server accepted the file transfer and it was completed successfully.
                - "max_size": The maximum allowed file size in MB (only included if the transfer was rejected due to file size).
        """
        if not self.file_port:
            return {"type": "not_connected"}
        if not os.path.isfile(filepath):
            return {"type": "file_not_found"}
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        # Connect to the file transfer port and send the file
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as file_socket:
                file_socket.settimeout(5) # 5 second timeout for connection
                file_socket.connect((self.server_ip, self.file_port))
                # Send handshake with filename and filesize
                handshake = {
                    "type": "connect",
                    "mode": "send",
                    "username": self.username,
                    "filename": filename,
                    "filesize": filesize
                }
                json_str = json.dumps(handshake) + "\n"
                file_socket.sendall(json_str.encode('utf-8'))
                # Wait for server response before sending file data
                reader = file_socket.makefile('r', encoding='utf-8')
                response_line = reader.readline()
                if not response_line: # No response from server
                    return {"type": "no_response"}
                response = json.loads(response_line)
                if response.get("type") == "transfer_reject": # File transfer rejected due to size limits
                    return {"type": "transfer_reject", "max_size": response.get("limit")}
                elif response.get("type") == "transfer_accept": # File transfer accepted, proceed to send file data
                    # Send all the file data
                    with open(filepath, "rb") as f:
                        data = f.read()
                        file_socket.sendall(data)
                    # Transfer update management
                    while response.get("type") != "transfer_success": # Wait for server to confirm transfer completion
                        if response.get("type") == "transfer_error": # Server reported an error during transfer
                            return {"type": "transfer_error"}
                        elif response.get("type") == "progress" and update_callback: # Progress update from server
                            received_bytes = response.get("received", 0)
                            percentage = (received_bytes / filesize) * 100 if filesize > 0 else 0
                            update_callback(percentage)
                        response_line = reader.readline()
                        if not response_line: # No response from server
                            return {"type": "no_response"}
                        response = json.loads(response_line)
                    return {"type": "success"}
                else: # Other responses are treated as errors
                    return {"type": "transfer_error"}
        except Exception as e:
            return {"type": "transfer_error"}
        finally:
            file_socket.close()
            reader.close()

    def receive_file(self, filename, save_path, update_callback = None):
        """
        Initiates a file reception from the server and saves it to the specified path.
        Args:
            filename (str): The name of the file to receive.
            save_path (str): The directory path where the received file should be saved.
            update_callback (function, optional): A function to be called with progress updates during the file reception.
        Returns:
            str: A string indicating the result of the file reception attempt, which can be:
                - "not_connected": The client is not connected to a server.
                - "file_not_found": The specified file is not available on the server.
                - "no_response": The server did not respond to the file reception request.
                - "transfer_error": An error occurred during the file reception process.
                - "success": The server sent a file and it was received successfully.
        """
        if not self.file_port:
            return "not_connected"
        
        # Connect to the file transfer port and send the file
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as file_socket:
                file_socket.settimeout(5) # 5 second timeout for connection
                file_socket.connect((self.server_ip, self.file_port))
                # Send handshake with filename and filesize
                handshake = {
                    "type": "connect",
                    "mode": "receive",
                    "username": self.username,
                    "filename": filename,
                }
                json_str = json.dumps(handshake) + "\n"
                file_socket.sendall(json_str.encode('utf-8'))
                # Wait for server response before receiving file data
                reader = file_socket.makefile('r', encoding='utf-8')
                response_line = reader.readline()
                if not response_line: # No response from server
                    return "no_response"
                response = json.loads(response_line)
                if response.get("type") == "invalid_file": # File not found or invalid name
                    return "file_not_found"
                elif response.get("type") == "transfer_accept": # File transfer accepted, proceed to receive file data
                    json_str = json.dumps({"type": "sync"}) + "\n" # Sync message.
                    file_socket.sendall(json_str.encode('utf-8'))
                    filesize = response.get("filesize", 0)
                    # Receive file data and save to disk
                    with open(save_path, "wb") as file:
                        prev_percentage = 0
                        prev_update_time = time.time()
                        received = 0
                        while received < filesize:
                            data = file_socket.recv(8192) # Receive data in chunks of 8KB
                            file.write(data)
                            received += len(data)
                            # To avoid slowing down the transfer, process updates every 5% or 5 seconds.
                            new_percentage = int((received / filesize) * 100)
                            if (new_percentage - prev_percentage > 5 or time.time() - prev_update_time > 5) and update_callback:
                                prev_percentage = new_percentage
                                prev_update_time = time.time()
                                update_callback(new_percentage)
                    return "success"
                else: # Other responses are treated as errors
                    return "transfer_error"
        except Exception as e:
            return "transfer_error"
        finally:
            file_socket.close()
            reader.close()