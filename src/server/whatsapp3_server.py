import os
try: os.add_dll_directory(os.getcwd()) #add working directory to find dll
except: pass #not windows
import socket
import threading
import numpy as np
import opuslib
import time
from collections import deque
import traceback
import json

def accept_file_connections():
    """
    Loop that accepts incoming file transfer connections,
    performs the initial handshake,
    and starts a new thread to handle each file transfer.
    """
    global file_socket
    global stop_program_flag
    #create data folder if it doesn't exist
    if not os.path.exists("data"):
        os.makedirs("data")
    file_socket.settimeout(1) #set timeout to check for stop_program_flag
    while not stop_program_flag:
        try:
            file_socket.listen()
            #print("Waiting for file connection")
            client, addr = file_socket.accept()
            # Check data availability
            client.settimeout(5) # 5 second timeout for handshake data
            reader = client.makefile('r', encoding='utf-8') # This simplifies reading lines of JSON data from the socket.
            handshake_line = reader.readline()
            reader.close() # Close the reader to avoid issues.
            if not handshake_line:
                client.close()
                log("Ignoring non-WSP3 connection on file server (no data received)")
                continue
            try:
                handshake = json.loads(handshake_line)
            except json.JSONDecodeError:
                client.close()
                log("Ignoring non-WSP3 connection on file server (invalid handshake format)")
                continue
            if handshake.get("type") != "connect" or "username" not in handshake or "mode" not in handshake:
                client.close()
                log("Ignoring non-WSP3 connection on file server (invalid handshake content)")
                continue
            username = handshake.get("username")
            log("Connected to " + username + " on file server")
            mode = handshake.get("mode")
            log("Mode: " + mode)
            if mode not in ["send", "receive"]:
                client.close()
                log("Invalid mode in handshake from " + username + " on file server: " + mode)
                continue
            file_client_list.append(client)
            #Send or receive file
            if mode == "receive": # If client wants to receive file, call the function to send it
                threading.Thread(target=send_file, args=(client,handshake,), daemon=True).start()
            elif mode == "send": # If client sends file, call the function to receive it
                threading.Thread(target=receive_file, args=(client, handshake,), daemon=True).start()
        except: pass #Ignore timeout errors and continue loop to check for stop_program_flag

def receive_file(client, handshake):
    global storagelimit
    global client_dict
    global chat_socket
    """
    Handles receiving a file from a client, saving it to disk, and notifying other clients about the new file.
    Args:
        client (socket.socket): The client socket to receive the file from.
        handshake (dict): The handshake data received from the client, containing at least the username and mode.
    """
    try:
        filename = handshake.get("filename", "unnamed_file") # Get filename from handshake, default to "unnamed_file" if not provided
        username = handshake.get("username", "Unknown") # Get username from handshake, default to "Unknown" if not provided
        filename = filename.replace(" ", "_") # Replace spaces with underscores to avoid issues with file paths
        filename = filename.replace("/", "_") # Replace slashes with underscores to avoid directory traversal issues
        filename = time.strftime("%Y%m%d%H%M%S_") + filename # Prepend timestamp to filename to avoid collisions
        log("Receiving file " + filename)
        filesize = int(handshake.get("filesize", 0)) # Get filesize from handshake, default to 0 if not provided

        # File size checks and storage management
        storageused = 0
        for file in os.listdir("data"):
            storageused += os.path.getsize("data/" + file)
        storageused = int(storageused / 1024 / 1024) #convert to MB
        filesizemb = int(filesize / 1024 / 1024) #convert to MB
        log("File size: " + str(filesizemb) + " MB")
        if filesizemb > storagelimit:
            log("File size exceeds storage limit. Rejecting file from " + username)
            client.send_json({
                "type": "transfer_reject",
                "limit": storagelimit
            })
            return
        if storageused + filesizemb > storagelimit:
            #delete all files in data folder
            for file in os.listdir("data"):
                os.remove("data/" + file)
            log("Storage limit exceeded. Deleted all files in data folder to free up space.")
        send_json(client, {
            "type": "transfer_accept"
        })
        
        # Receive file data and save to disk
        with open("data/" + filename, "wb") as file:
            received = 0
            prev_percentage = 0
            prev_update_time = time.time()
            while received < filesize:
                data = client.recv(8192) # Receive data in chunks of 8KB
                file.write(data)
                received += len(data)
                # To avoid slowing down the transfer, send updates every 5% or every 5 seconds
                new_percentage = int((received / filesize) * 100)
                if new_percentage - prev_percentage > 5 or time.time() - prev_update_time > 5:
                    prev_percentage = new_percentage
                    prev_update_time = time.time()
                    send_json(client,{
                        "type": "progress",
                        "received": received,
                    })
        # Success
        log("File received")
        send_json(client, {
            "type": "transfer_success"
        })
        message = {
            "type": "file_notice",
            "sender": username,
            "filename": filename,
            "filesize": filesize,
            "timestamp": time.time()
        }
        # TODO: Add to message history (something like add_to_history(message))
        for c in list(client_dict.keys()):
            send_json(c, message)
    except Exception as e:
        log("Error receiving file " + filename)
        # Try to notify the client about the error.
        try:
            send_json(client, {
                "type": "transfer_error",
            })
        except:
            pass
        # Try to clean up any partially received file.
        try:
            if os.path.exists("data/" + filename):
                os.remove("data/" + filename)
                log("Deleted partially received file " + filename)
        except:
            pass
    finally:
        client.close()
        if client in file_client_list:
            file_client_list.remove(client)

def send_file(client, handshake):
    """
    Handles sending a file to a client based on the filename specified in the handshake,
    and notifies other clients about the file transfer.
    """
    try:
        filename = handshake.get("filename", "unnamed_file") # Get filename from handshake, default to "unnamed_file" if not provided
        if (not os.path.isfile("data/" + filename)) or "/" in filename or ".." in filename or "\\" in filename:
            send_json(client, {
                "type": "invalid_file",
            })
            log("File " + filename + " not found or invalid.")
            return
        send_json(client, { # Send transfer accept message with filesize
            "type": "transfer_accept",
            "filesize": os.path.getsize("data/" + filename)
        })
        client.recv(4096) # Wait for sync message from client before sending file data
        with open("data/" + filename, "rb") as file:
            data = file.read()
            client.sendall(data)
        log("Sending file " + filename)
    except Exception as e:
        log("Error sending file " + filename)
    finally:
        client.close()
        if client in file_client_list:
            file_client_list.remove(client)

def accept_connections():
    """
    Loop that accepts incoming client connections,
    performs the initial handshake,
    and starts a new thread to handle each client.
    """
    global chat_socket
    global stop_program_flag
    global client_dict

    chat_socket.settimeout(1) #set timeout to check for stop_program_flag
    while not stop_program_flag:
        try:
            chat_socket.listen()
            client, addr = chat_socket.accept()
            # Check data availability
            client.settimeout(5) # 5 second timeout for handshake data
            reader = client.makefile('r', encoding='utf-8') # This simplifies reading lines of JSON data from the socket.
            handshake_line = reader.readline()
            reader.close() # Close the reader to avoid issues.
            if not handshake_line:
                client.close()
                log("Ignoring non-WSP3 connection (no data received)")
                continue
            try:
                handshake = json.loads(handshake_line)
            except json.JSONDecodeError:
                client.close()
                log("Ignoring non-WSP3 connection (invalid handshake format)")
                continue
            if handshake.get("type") != "connect" or "username" not in handshake or "voice_id" not in handshake:
                client.close()
                log("Ignoring non-WSP3 connection (invalid handshake content)")
                continue
            username = handshake["username"]
            voice_id = handshake["voice_id"]
            response_status = "ok"
            response_reason = ""
            if username in client_dict.values():
                response_status = "error"
                response_reason = "username_taken"
            response_dict = {
                "status": response_status,
                "reason": response_reason,
                "file_port": config.get("fileport"),
                "voice_port": config.get("voiceport"),
                "client_list": list(client_dict.values()),
                "voice_client_list": [voice_names.get(vid) for vid in expected_voice_ids if vid in voice_names]
            }
            client.send((json.dumps(response_dict) + "\n").encode('utf-8'))
            if response_status == "ok":
                message = {
                    "type": "new_client",
                    "username": username,
                    "timestamp": time.time()
                }
                # TODO: Add to message history (something like add_to_history(message))
                for c in list(client_dict.keys()):
                    send_json(c, message)
                client_dict[client] = username
                voice_names[voice_id] = username # Associate the voice id with the username
                log("Connected to " + username)
                threading.Thread(target=receive_message_loop, args=(client, username, addr,), daemon=True).start()
            else:
                client.close()
                log("Rejected connection from " + addr[0] + ":" + str(addr[1]) + ". Reason: " + response_reason)
        except: pass #Ignore timeout errors and continue loop to check for stop_program_flag


def receive_message_loop(client, username, addr):
    """
    Loop that receives messages from a specific client and handles them accordingly.
    Args:
        client (socket.socket): The client socket to receive messages from.
        username (str): The username associated with this client.
        addr (tuple): The address of the client (IP, port).
    """
    global stop_program_flag
    global client_dict

    client.settimeout(1) #set timeout to check for stop_program_flag
    buffer = "" # Buffer to accumulate incoming data until we have complete JSON lines
    while not stop_program_flag:
        try:
            chunk = client.recv(4096).decode('utf-8')
            if not chunk:
                disconnect_client(client, reason = "Client disconnected (no data received).")
                return
            buffer += chunk
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                send_message = None
                if line.strip():
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        disconnect_client(client, reason = "Client sent invalid data format.")
                        return
                    # Message type handling
                    msg_type = message.get("type")
                    if msg_type == "chat":
                        sender = client_dict.get(client, "Unknown")
                        content = message.get("content")
                        send_message = { # Construct message to send to other clients
                            "type": "chat",
                            "sender": sender,
                            "content": content,
                            "timestamp": time.time()
                        }
                        log(sender + ": " + content)
                    elif msg_type == "voice_connect":
                        voice_id = message.get("voice_id")
                        if voice_id and voice_id not in expected_voice_ids:
                            expected_voice_ids.append(voice_id)
                            send_message = {
                                "type": "new_voice_client",
                                "username": username,
                                "timestamp": time.time()
                            }
                            log("Voice client connected: " + username)
                    elif msg_type == "voice_disconnect":
                        voice_id = message.get("voice_id")
                        if voice_id and voice_id in expected_voice_ids:
                            expected_voice_ids.remove(voice_id)
                            voice_ip = voice_ids.get(voice_id) #get the IP address associated with this voice id
                            # Disconnecting process (cleanup) if the client had already sent data
                            if voice_ip and voice_ip in voice_clients:
                                voice_clients.remove(voice_ip)
                                jitter_buffers.pop(voice_ip, None)
                                buffer_states.pop(voice_ip, None)
                                decoders.pop(voice_ip, None)
                                encoders.pop(voice_ip, None)
                            send_message = {
                                "type": "disconnected_voice_client",
                                "username": username,
                                "timestamp": time.time()
                            }
                            log("Voice client disconnected: " + username)
                    else:
                        log("Ignoring unknown message type from " + username + ": " + msg_type)
                
                if send_message:
                    # TODO: Add to message history (something like add_to_history(send_message))
                    for c in list(client_dict.keys()):
                        if c != client:
                            send_json(c, send_message)
        except socket.timeout:
            continue # Ignore timeouts and continue loop to check for stop_program_flag
        except Exception as e:
            disconnect_client(client, reason = "Client disconnected")
            exit() # If there is an error receiving data, assume client disconnected
    
    disconnect_client(client, reason = "Server closed connection")
    exit()

def send_json(client, data_dict):
    """
    Send a JSON-encoded message to the specified client socket.
    Args:
        client (socket.socket): The client socket to send the message to.
        data_dict (dict): The data to send as a JSON object.
    """
    if client:
        try:
            json_str = json.dumps(data_dict) + "\n" # Add newline as a message delimiter
            client.sendall(json_str.encode('utf-8'))
        except Exception as e:
            client.close()
            log("Error sending data to client: " + str(e))

def disconnect_client(client, reason = None):
    """
    Disconnects a client and cleans up resources.
    Args:
        client (socket.socket): The client socket to disconnect.
        reason (str, optional): The reason for disconnection, if any.
    """
    global client_dict
    global expected_voice_ids
    global voice_ids
    global voice_names
    username = client_dict.get(client, "Unknown")
    if username in client_dict.values():
        client_dict.pop(client, None) # Remove client from client_dict in a thread-safe way
        message = {
            "type": "disconnected_client",
            "username": username,
            "timestamp": time.time()
        }
        # TODO: Add to message history (something like add_to_history(message))
        for c in list(client_dict.keys()):
            send_json(c, message)
        log("Disconnected from " + username + ". Reason: " + (reason if reason else "No reason provided"))
        # Clean up voice client data if this client had a voice id
        if username in voice_names.values():
            voice_id = next(key for key, value in voice_names.items() if value == username)
            voice_names.pop(voice_id, None)
            expected_voice_ids = [vid for vid in expected_voice_ids if vid != voice_id] # Remove from expected_voice_ids
            voice_ip = voice_ids.pop(voice_id, None) # Remove from voice_ids and get the associated IP
            if voice_ip and voice_ip in voice_clients: # If the client had already sent voice data, clean up their voice buffers and decoders
                voice_clients.remove(voice_ip)
                jitter_buffers.pop(voice_ip, None)
                buffer_states.pop(voice_ip, None)
                decoders.pop(voice_ip, None)
                encoders.pop(voice_ip, None)


def voice_loop():
    """
    Receive voice data, decode it and store it on the buffers.
    Also manages new clients by creating decoders and buffers when they send their first voice packet.
    """
    global voice_socket, decoders, voice_clients, jitter_buffers, jitter_lock, expected_voice_ids, voice_ids
    voice_socket.settimeout(1)
    while not stop_program_flag:
        try:
            data, addr = voice_socket.recvfrom(4096)
            if len(data) < 16: continue # ignore packets that are too small to contain the voice id
            id = data[:16].hex() #get voice id from first 16 bytes of data
            audio_payload = data[16:]
            with jitter_lock:
                #print(id, expected_voice_ids)
                if addr in voice_clients:
                    # decode data and add to buffer
                    decoded_payload = decoders[addr].decode(audio_payload, FRAME_SIZE) #decode data (320 samples)
                    jitter_buffers[addr].append(decoded_payload) #store data in buffer
                    #print(addr, " ", buffer_states[addr], " ", len(jitter_buffers[addr]))

                elif id in expected_voice_ids: # manage new client
                    jitter_buffers[addr] = deque() #create buffer for client if it doesn't exist
                    buffer_states[addr] = BUFFER_WAIT_FILL #set buffer state to wait for fill
                    decoders[addr] = opuslib.Decoder(RATE, CHANNELS) #create decoder for this client
                    encoders[addr] = opuslib.Encoder(RATE, CHANNELS, opuslib.APPLICATION_AUDIO) #create encoder for this client
                    voice_clients.append(addr)
                    voice_ids[id] = addr #associate this voice id with the client's IP address
                    
                    
        except socket.timeout: pass
        except Exception as e: pass
            #print ("Error receiving voice data:", e)
            #traceback.print_exc()


def mix_and_send_voice():
    """
    Creates a mixed audio for each client, encodes it and sends it to each respective client.
    Also manages the timing of the mixing loop.
    """
    global voice_socket
    global voice_clients
    global jitter_buffers
    global buffer_states
    global jitter_lock
    global encoders
    next_loop_timing = time.time()
    while not stop_program_flag:
        try:
            #STEP 1: get data from buffers and add it to mix dictionary
            with jitter_lock:
                streams_to_mix = {addr: [] for addr in voice_clients}
                for addr in list(voice_clients):
                    state = buffer_states.get(addr, BUFFER_WAIT_FILL) #get buffer state, default to wait fill if not found
                    q = jitter_buffers.get(addr, deque()) #get buffer, default to empty deque if not found

                    if state == BUFFER_WAIT_FILL: #if buffer is waiting to fill, don't get data from it
                        if len(q) >= JITTER_BUFFER_OPTIMAL: #if buffer is on optimal size, change state to running
                            buffer_states[addr] = BUFFER_RUNNING
                    
                    elif buffer_states[addr] == BUFFER_RUNNING: #if buffer is running, get one frame from the buffer
                        if len(q) > 0:
                            streams_to_mix[addr].append(q.popleft()) #get one frame from buffer
                        if len(q) >= JITTER_BUFFER_MAX:
                            buffer_states[addr] = BUFFER_WAIT_DRAIN #if buffer is on max size, change state to wait for drain
                        elif len(q) == 0: #if buffer is empty, change state to wait for fill
                            buffer_states[addr] = BUFFER_WAIT_FILL
                    
                    elif buffer_states[addr] == BUFFER_WAIT_DRAIN: #if buffer is waiting to drain, get two frames from the buffer
                        if len(q) > 0:
                            streams_to_mix[addr].append(q.popleft())
                        if len(q) > 0:
                            streams_to_mix[addr].append(q.popleft())
                        if len(q) <= JITTER_BUFFER_OPTIMAL:
                            buffer_states[addr] = BUFFER_RUNNING #if buffer is on optimal size, change state to running

            #STEP 2a: get a list of all frames to mix, and note the index of the frames that belong to the each client
            all_arrays = []  # list of all numpy arrays to mix
            per_client_frames = {}  # dictionary that maps client address to list of indices in all_arrays
            idx = 0 # track index of the inserted frames on all_arrays
            for addr, frames in streams_to_mix.items(): # iterate through all clients and their frame lists
                per_client_frames[addr] = [] # initialize list for this client
                for f in frames: # iterate through all frames for this client
                    arr = np.frombuffer(f, dtype=np.int16) # convert bytes to numpy array
                    all_arrays.append(arr) # add array to all_arrays list
                    per_client_frames[addr].append(idx) # add index to per_client_frames for this client to avoid sending own audio back
                    idx += 1
                
            #STEP 2b: mix all frames together
            if len(all_arrays) == 0:
                # nothing to send: skip this iteration (sleep below)
                pass
            else:
                min_len = min(a.shape[0] for a in all_arrays) # truncate to the shortest length
                arrays32 = [a[:min_len].astype(np.int64) for a in all_arrays] # convert to int32 for safe accumulation
                total_sum = np.sum(arrays32, axis=0, dtype=np.int64) # total sum (dtype to avoid overflow)
                
                #STEP 2c: substract each client's own audio from the total sum, encode and send
                total_frames = len(arrays32) # number of frames mixed
                for addr in list(voice_clients):
                    client_idxs = per_client_frames.get(addr, []) # indices of frames that belong to this client
                    n_client_frames = len(client_idxs) # number of frames from this client
                    n_other = total_frames - n_client_frames # number of frames from other clients
                    if n_other <= 0:
                        # if there are no other frames, skip sending to this client
                        continue
                    if n_client_frames > 0:
                        # if there are frames from this client, substract them from the total sum
                        client_sum = np.sum([arrays32[i] for i in client_idxs], axis=0, dtype=np.int64) # sum of client's own frames
                        others_sum = total_sum - client_sum # substract client's own frames from total sum
                    else:
                        others_sum = total_sum # if there are no frames from this client, send the total sum
                    # normalize and clip to int16 range
                    mixed = (others_sum // n_other)
                    mixed = np.clip(mixed, -32768, 32767).astype(np.int16).tobytes()
                    # encode and send
                    try:
                        encoded_data = encoders[addr].encode(mixed, FRAME_SIZE)
                        voice_socket.sendto(encoded_data, addr)
                    except Exception as e:
                        print("Error encoding/sending to", addr, " Error details:", e)
                        traceback.print_exc()
        except Exception as e:
            print("Error mixing one frame of audio. Skipping to the next iteration. Error details:", e)
            traceback.print_exc()

        #STEP 3: sleep until the next loop timing
        next_loop_timing += MIX_INTERVAL
        sleep_time = next_loop_timing - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            print("Warning: mixing and sending audio took longer than expected. Skipping to the next iteration.")
            next_loop_timing = time.time()



def stop_program():
    """
    Cleans up resources and stops the server.
    """
    global chat_socket
    global client_dict
    global file_socket
    global file_client_list
    global stop_program_flag
    print("Stopping server, closing connections...")
    stop_program_flag = True
    chat_socket.close()
    for client in list(client_dict.keys()):
        client.close()
    file_socket.close()
    for client in file_client_list:
        client.close()
    voice_socket.close()
    log("Server stopped")
    exit()

#Program start
stop_program_flag = False
print("INITIALATING STARTING PROCESS...")
#create sockets
print("Creating sockets...")
chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # create socket for main connection management and chat
chat_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #allow reuse of address
file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # create socket for file transfer
file_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #allow reuse of address
voice_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # create socket for voice
#load config file or create default config file
print("Loading config file...")
try:
    with open("config.json", 'r') as file:
        config = json.load(file)
        ip = config.get("ip")
        port = config.get("port")
        fileport = config.get("fileport")
        voiceport = config.get("voiceport")
        storagelimit = config.get("storagelimit")
    #try to bind sockets to ip and port
    print("Validating parameters and binding sockets...")
    chat_socket.bind((ip, int(port)))
    file_socket.bind((ip, int(fileport)))
    voice_socket.bind((ip, int(voiceport)))
    
except:
    print("No config file or invalid format. Creating new config file with default values.")
    config ={
        "ip": "1",
        "port": "12345",
        "fileport": "12346",
        "voiceport": "12347",
        "storagelimit": 1024
    }
    with open("config.json", 'w') as file:
        json.dump(config, file, indent=4)
    print("Config file created. Please edit the file before starting the server again.")
    exit()

print("Initialating lists and voice parameters...")
#lists of clients and voice clients connected
client_dict = {} # Map client sockets to their usernames.
file_client_list = [] # List of client sockets that are currently connected to the file server (for cleanup purposes).
voice_clients = [] # List of client addresses that have sent voice data and are considered active voice clients.
expected_voice_ids = [] # List of expected identifiers for voice clients.
voice_ids = {} # Map voice client identifiers to their corresponding IP addresses to manage disconnections.
voice_names = {} # Map voice client identifiers to their corresponding usernames.

#voice server buffers and codec parameters
jitter_buffers = {}
buffer_states = {}
jitter_lock = threading.Lock()
CHANNELS = 1 # mono
RATE = 16000  # 16 kHz (samples per second)
FRAME_SIZE = 320 # 320 samples per frame (640 bytes), 20 ms per frame
MIX_INTERVAL = FRAME_SIZE / RATE # seconds per frame
JITTER_BUFFER_OPTIMAL = 4 # Optimal buffer size in frames
JITTER_BUFFER_MAX = 8 # Maximum buffer size in frames
#buffer states
BUFFER_WAIT_FILL = 0 #Waiting for buffer to fill to optimal size
BUFFER_RUNNING = 1 #Buffer is running correctly
BUFFER_WAIT_DRAIN = 2 #Waiting for buffer to empty to optimal size
decoders = {} # Each client has its own decoder instance as opus is a stateful codec and assumes each frame is sequential
encoders = {} # Same for encoders

#start threads
print("Starting threads...")
accept_thread = threading.Thread(target=accept_connections, daemon=True)
accept_thread.start()
file_thread = threading.Thread(target=accept_file_connections, daemon=True)
file_thread.start()
voice_thread = threading.Thread(target=voice_loop, daemon=True)
voice_thread.start()
mix_thread = threading.Thread(target=mix_and_send_voice, daemon=True)
mix_thread.start()

def log(message):
    print(message)
    with open("log.txt", "a") as file:
        datetime = time.strftime("%Y-%m-%d %H:%M:%S")
        file.write(datetime + " - " + message + "\n")


log("Server started")
input("Press enter to stop server\n")
stop_program()
