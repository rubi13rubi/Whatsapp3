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
            print("New connection on file server")
            log("New connection on file server")
            #check data availability with timeout
            client.settimeout(1)
            data = client.recv(1024).decode()
            client.settimeout(None)
            if data != "WSP3": #code sent by client to identify itself as WSP3 client
                client.close()
                print("Ignoring non-WSP3 connection on file server")
                log("Ignoring non-WSP3 connection on file server")
            else:
                client.send("Sync".encode())
                username = client.recv(1024).decode()
                print("Connected to", username + " on file server")
                log("Connected to " + username + " on file server")
                client.send("Sync".encode())
                mode = client.recv(1024).decode()
                print("Mode:", mode)
                log("Mode: " + mode)
                client.send("Sync".encode())
                #Send or receive file
                if mode == "receive":
                    threading.Thread(target=send_file, args=(client,)).start()
                elif mode == "send":
                    threading.Thread(target=receive_file, args=(client,username,)).start()
        except: pass

def receive_file(client, username):
    global storagelimit
    global client_list
    global server_socket
    try:
        filename = client.recv(1024).decode()
        filename = filename.replace(" ", "_") #replace spaces with underscores
        print("Receiving file", filename)
        log("Receiving file " + filename)
        client.send("Sync".encode())
        filesize = int(client.recv(1024).decode())
        client.send("Sync".encode())
        #calculate storage used on folder data
        storageused = 0
        for file in os.listdir("data"):
            storageused += os.path.getsize("data/" + file)
        storageused = int(storageused / 1024 / 1024) #convert to MB
        filesizemb = int(filesize / 1024 / 1024) #convert to MB
        print("File size:", filesizemb, "MB")
        log("File size: " + str(filesizemb) + " MB")
        if storageused + filesizemb > storagelimit:
            #delete all files in data folder
            for file in os.listdir("data"):
                os.remove("data/" + file)
        #receive file
        with open("data/" + filename, "wb") as file:
            received = 0
            while received < filesize:
                data = client.recv(1024)
                file.write(data)
                received += len(data)
        print("File received")
        log("File received")
        for c in client_list:
            c.send((username + " sent file " + filename + " (double click to save)").encode())
    except:
        print("Error receiving file", filename)
        log("Error receiving file " + filename)
    finally: client.close()

def send_file(client):
    try:
        filename = client.recv(1024).decode()
        print("Sending file ", filename)
        if not os.path.exists("data/" + filename):
            client.send("0".encode())
            print("File " + filename + " not found")
            log("File " + filename + " not found")
            return
        with open("data/" + filename, "rb") as file:
            filesize = os.path.getsize("data/" + filename)
            client.send(str(filesize).encode())
            client.recv(1024) # Sync
            data = file.read()
            client.sendall(data)
        print("File " + filename + " sent")
        log("File " + filename + " sent")
    except:
        print("Error sending file", filename)
        log("Error sending file " + filename)
    finally: client.close()
 

def accept_connections():
    global server_socket
    global stop_program_flag
    global client_list
    server_socket.settimeout(1) #set timeout to check for stop_program_flag
    while not stop_program_flag:
        try:
            server_socket.listen()
            client, addr = server_socket.accept()
            #check data availability with timeout
            client.settimeout(1)
            data = client.recv(1024).decode()
            if data != "WSP3": #code sent by client to identify itself as WSP3 client
                client.close()
                print("Ignoring non-WSP3 connection")
                log("Ignoring non-WSP3 connection")
            else:
                client.send("Sync".encode())
                username = client.recv(1024).decode()
                client.send(fileport.encode())
                client.recv(1024) # Sync
                client.send(voiceport.encode())
                client.recv(1024) # Sync
                print("Connected to", username)
                log("Connected to " + username)
                client.send(("Connected to server. Active users: " + str(len(client_list))).encode())
                for c in client_list:
                    c.send(("NEW CLIENT: " + username).encode())
                client_list.append(client)
                threading.Thread(target=receive_message_loop, args=(client, username, addr,)).start()
        except: pass

def receive_message_loop(client, username, addr):
    global stop_program_flag
    global client_list
    global expected_voice_ips
    index = client_list.index(client)
    while not stop_program_flag:
        try:
            message = client.recv(1024)
            if not message: break #if message is empty, client closed connection
            if message.decode().startswith("/voice"):
                ip = addr[0]

                if ip not in expected_voice_ips:
                    expected_voice_ips.append(ip) #add ip to expected voice ips (new user connected)
                    sentmessage = username + " connected to voice server"
                else:
                    expected_voice_ips.remove(ip) #remove ip from expected voice ips (user disconnected)
                    # Disconnecting process (cleanup)
                    for addr in voice_clients:
                        if addr[0] == ip:
                            voice_clients.remove(addr)
                            jitter_buffers.pop(addr, None)
                            buffer_states.pop(addr, None)
                            decoders.pop(addr, None)
                            encoders.pop(addr, None)
                    sentmessage = username + " disconnected from voice server"

            elif message.decode() == "/mute":
                sentmessage = username + " muted"
            elif message.decode() == "/unmute":
                sentmessage = username + " unmuted"
            else:
                sentmessage = username + ": " + message.decode()
            print(sentmessage)
            log(sentmessage)
            for c in client_list:
                if c != client:
                    c.send(sentmessage.encode())
        except Exception as e:
            if str(e) == "timed out": pass #Ignore timeout errors
            else: break #if error is not timeout, close connection

    print(username + " disconnected")
    log(username + " disconnected")
    if client in client_list: client_list.remove(client)
    client.close()
    for c in client_list:
        c.send((username + " DISCONNECTED").encode())
    exit()

def voice_loop(): #receive voice data, decode it and store in buffers
    global voice_socket, decoders, voice_clients, jitter_buffers, jitter_lock
    voice_socket.settimeout(1)
    while not stop_program_flag:
        try:
            data, addr = voice_socket.recvfrom(4096)
            with jitter_lock:
                if ip in expected_voice_ips:
                    if addr not in voice_clients: # manage new client
                        jitter_buffers[addr] = deque() #create buffer for client if it doesn't exist
                        buffer_states[addr] = BUFFER_WAIT_FILL #set buffer state to wait for fill
                        decoders[addr] = opuslib.Decoder(RATE, CHANNELS) #create decoder for this client
                        encoders[addr] = opuslib.Encoder(RATE, CHANNELS, opuslib.APPLICATION_AUDIO) #create encoder for this client
                        voice_clients.append(addr)
                    
                    # decode data and add to buffer
                    decoded_data = decoders[addr].decode(data, FRAME_SIZE) #decode data (320 samples)
                    jitter_buffers[addr].append(decoded_data) #store data in buffer
                    #print(addr, " ", buffer_states[addr], " ", len(jitter_buffers[addr]))
        except socket.timeout: pass
        except Exception as e:
            print ("Error receiving voice data:", e)
            traceback.print_exc()


def mix_and_send_voice(): #mix all voice buffers, encode it and send to all clients except the sender
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



def stop_program():
    global server_socket
    global client_list
    global stop_program_flag
    stop_program_flag = True
    server_socket.close()
    for client in client_list:
        client.close()
    log("Server stopped")
    exit()

#Program start
stop_program_flag = False
print("INITIALATING STARTING PROCESS...")
#create sockets
print("Creating sockets...")
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # create socket for main connection management and chat
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #allow reuse of address
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
    server_socket.bind((ip, int(port)))
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
client_list = []
voice_clients = []
expected_voice_ips = [] # list of all ips that connected to the voice server

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
accept_thread = threading.Thread(target=accept_connections)
accept_thread.start()
file_thread = threading.Thread(target=accept_file_connections)
file_thread.start()
voice_thread = threading.Thread(target=voice_loop)
voice_thread.start()
mix_thread = threading.Thread(target=mix_and_send_voice)
mix_thread.start()

def log(message):
    with open("log.txt", "a") as file:
        datetime = time.strftime("%Y-%m-%d %H:%M:%S")
        file.write(datetime + " - " + message + "\n")



print("Server started successfully")
log("Server started")
input("Press enter to stop server\n")
print("Stopping server")
stop_program()
