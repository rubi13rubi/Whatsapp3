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
            if data != "WSP3":
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
            if data != "WSP3":
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
    index = client_list.index(client)
    while not stop_program_flag:
        try:
            message = client.recv(1024)
            if not message: break #if message is empty, client closed connection
            if message.decode().startswith("/voice"):
                ip = addr[0]
                port = int(message.decode().split(" ")[1])
                addr = (ip, port)
                if addr not in voice_clients:
                    jitter_buffers[addr] = deque() #create buffer for client if it doesn't exist
                    buffer_states[addr] = BUFFER_WAIT_FILL #set buffer state to wait for fill
                    voice_clients.append(addr)
                    sentmessage = username + " connected to voice server"
                else:
                    voice_clients.remove(addr)
                    jitter_buffers.pop(addr)
                    buffer_states.pop(addr)
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
    global voice_socket
    global voice_clients
    global jitter_buffers
    voice_socket.settimeout(1)
    while not stop_program_flag:
        try:
            data, addr = voice_socket.recvfrom(4096)
            if addr in voice_clients: #only process data from clients connected to voice server
                decoded_data = decoder.decode(data, FRAME_SIZE) #decode data (320 samples)
                jitter_buffers[addr].append(decoded_data) #store data in buffer
                #print(addr, " ", buffer_states[addr], " ", len(jitter_buffers[addr]))
        except: pass#print ("Error receiving voice data")

def mix_and_send_voice(): #mix all voice buffers, encode it and send to all clients except the sender
    global voice_socket
    global voice_clients
    global jitter_buffers
    next_loop_timing = time.time()
    while not stop_program_flag:
        try:
            #STEP 1: iterate through all clients to mix and send each one without removing the data from the buffers
            for addr in voice_clients: 
                streams_to_mix = []
                for addr2 in voice_clients: #iterate through all clients to determine which streams to mix
                    if addr != addr2: #don't mix the stream of the client itself
                        if len(jitter_buffers[addr2]) > 0:
                            if buffer_states[addr2] == BUFFER_RUNNING:
                                streams_to_mix.append(jitter_buffers[addr2][0]) #add stream to mix without removing it
                            elif buffer_states[addr2] == BUFFER_WAIT_DRAIN: #add 2 streams to mix without removing them
                                streams_to_mix.append(jitter_buffers[addr2][0])
                                streams_to_mix.append(jitter_buffers[addr2][1])
                #mix streams and send mixed data
                if len(streams_to_mix) > 0: #mix streams only if there are more than one
                    audio_data = [np.frombuffer(stream, dtype=np.int16) for stream in streams_to_mix] #convert streams to numpy arrays
                    min_length = min(len(data) for data in audio_data)
                    audio_data = [data[:min_length] for data in audio_data] #truncate data to the shortest length
                    mixed_data = sum(audio_data) #mix audio data
                    mixed_data = mixed_data // len(audio_data) #normalize mixed data
                    mixed_data = np.clip(mixed_data, -32768, 32767) #clip mixed data to avoid overflow or underflow
                    mixed_data = mixed_data.astype(np.int16).tobytes() #convert mixed data to bytes
                    encoded_data = encoder.encode(mixed_data, FRAME_SIZE)
                    voice_socket.sendto(encoded_data, addr)
            #STEP 2: buffers cleanup and state management
            for addr in voice_clients:
                #print("State before cleanup: ", addr, " ", buffer_states[addr], " ", len(jitter_buffers[addr]))
                if buffer_states[addr] == BUFFER_WAIT_FILL: #if buffer is waiting to fill, don't clean the buffer
                    if len(jitter_buffers[addr]) >= JITTER_BUFFER_OPTIMAL: #if buffer is on optimal size, change state to running
                        buffer_states[addr] = BUFFER_RUNNING
                elif buffer_states[addr] == BUFFER_RUNNING: #if buffer is running, clean one frame from the buffer
                    jitter_buffers[addr].popleft()
                    if len(jitter_buffers[addr]) >= JITTER_BUFFER_MAX: #if buffer is on max size, change state to wait for drain
                        buffer_states[addr] = BUFFER_WAIT_DRAIN
                    elif len(jitter_buffers[addr]) == 0: #if buffer is empty, change state to wait for fill
                        buffer_states[addr] = BUFFER_WAIT_FILL
                elif buffer_states[addr] == BUFFER_WAIT_DRAIN: #if buffer is waiting to drain, clean two frames from the buffer
                    jitter_buffers[addr].popleft()
                    jitter_buffers[addr].popleft()
                    if len(jitter_buffers[addr]) <= JITTER_BUFFER_OPTIMAL: #if buffer is on optimal size, change state to running
                        buffer_states[addr] = BUFFER_RUNNING
                #print("State after cleanup: ", addr, " ", buffer_states[addr], " ", len(jitter_buffers[addr]))
        except Exception as e:
            #print("Error mixing one frame of audio. Skipping to the next iteration. Error details:", e)
            #traceback.print_exc()
            pass
        #STEP 3: sleep until the next loop timing
        next_loop_timing += MIX_INTERVAL
        sleep_time = next_loop_timing - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)
        #else:
        #    print("Warning: mixing and sending audio took longer than expected. Skipping to the next iteration.")
        



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

stop_program_flag = False
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    with open("config.json", 'r') as file:
        config = json.load(file)
        ip = config.get("ip")
        port = config.get("port")
        fileport = config.get("fileport")
        voiceport = config.get("voiceport")
        storagelimit = config.get("storagelimit")
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
server_socket.bind((ip, int(port)))
file_socket.bind((ip, int(fileport)))
client_list = []
accept_thread = threading.Thread(target=accept_connections)
accept_thread.start()
file_thread = threading.Thread(target=accept_file_connections)
file_thread.start()
voice_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
voice_socket.bind((ip, int(voiceport)))
voice_thread = threading.Thread(target=voice_loop)
voice_clients = []
jitter_buffers = {}
buffer_states = {}
CHANNELS = 1 # mono
RATE = 16000  # 16 kHz
FRAME_SIZE = 320 # 20 ms, 640 bytes per frame
MIX_INTERVAL = 0.020 # 20 ms
JITTER_BUFFER_OPTIMAL = 4 # Optimal buffer size in frames
JITTER_BUFFER_MAX = 8 # Maximum buffer size in frames
#buffer states
BUFFER_WAIT_FILL = 0 #Waiting for buffer to fill to optimal size
BUFFER_RUNNING = 1 #Buffer is running correctly
BUFFER_WAIT_DRAIN = 2 #Waiting for buffer to empty to optimal size
encoder = opuslib.Encoder(RATE, CHANNELS, opuslib.APPLICATION_AUDIO)
decoder = opuslib.Decoder(RATE, CHANNELS)
voice_thread.start()
mix_thread = threading.Thread(target=mix_and_send_voice)
mix_thread.start()

def log(message):
    with open("log.txt", "a") as file:
        datetime = time.strftime("%Y-%m-%d %H:%M:%S")
        file.write(datetime + " - " + message + "\n")



print("Server started")
log("Server started")
input("Press enter to stop server\n")
print("Stopping server")
stop_program()
