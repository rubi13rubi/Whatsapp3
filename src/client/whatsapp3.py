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
from tkinter import *
from tkinter import ttk
from tkinter import filedialog
import pyaudio
import opuslib
from collections import deque
import numpy as np



def receive_message(message):
    global message_list
    at_bottom = message_list.yview()[1] == 1.0
    message_list.insert(END, message)
    if at_bottom:
        message_list.see('end')

def send_message(message):
    global message_list
    global message_entry
    global server_socket
    global voice_enabled
    global gain
    if message.startswith("/voice"):
        global voice_socket
        message = "/voice"
        if voice_enabled:
            voice_enabled = False
            message_list.insert(END, "Voice chat disabled")
        else:
            voice_enabled = True
            message_list.insert(END, "Voice chat enabled")
            voice_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            ip = server_socket.getsockname()[0]
            voice_socket.bind((ip, 0)) # Bind to a random port
            threading.Thread(target=voice_rcv_loop).start()
            threading.Thread(target=voice_send_loop).start()
            threading.Thread(target=voice_play_loop).start()
        addr = voice_socket.getsockname()
        message += " " + str(addr[1]) # Send the port
    elif message == "/mute":
        global muted
        if voice_enabled:
            if muted:
                muted = False
                message_list.insert(END, "Unmuted")
                message = "/unmute"
            else:
                muted = True
                message_list.insert(END, "Muted")
                message = "/mute"
        else:
            message_list.insert(END, "You need to enable voice chat first")
            message = ""
    elif message.startswith("/gain"):
        try: gain = float(message_entry.get().split(" ")[1])
        except: message_list.insert(END, "Invalid gain value")
        message_list.insert(END, "Current gain: " + str(gain))
        message = ""

    else: message_list.insert(END, "YOU: " + message)
    message_entry.delete(0, 'end') #clear the entry box
    message_list.see('end')
    try:
        server_socket.send((message).encode())
    except:
        message_list.insert(END, "Error sending message")

def send_file(ip, fileport, user, filepath, window):
    if filepath == "Select a file to send" or filepath == "":
        return
    try:
        file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        file_socket.connect((ip, int(fileport)))
        file_socket.send("WSP3".encode())
        file_socket.recv(1024) # Sync
        file_socket.send(user.encode())
        file_socket.recv(1024) # Sync
        file_socket.send("send".encode())
        file_socket.recv(1024) # Sync
        filename = filepath.split("/")[-1]
        if (" " in filename): filename = filename.replace(" ", "_")
        file_socket.send(filename.encode())
        file_socket.recv(1024) # Sync
        file = open(filepath, "rb")
        filedata = file.read()
        filesize = len(filedata)
        file_socket.send(str(filesize).encode())
        file_socket.recv(1024) # Sync
        receive_message("Sending file " + filename + ". Please wait.")
        file_socket.sendall(filedata)
    except:
        receive_message("Error sending file")
    finally:
        file_socket.close()
        window.destroy()

def chat_double_click(event, ip, fileport, user):
    global message_list
    message = message_list.get(message_list.nearest(event.y))
    if not("sent file" in message) or ":" in message:
        return
    filename = message.split(" ")[-5]
    filepath = filedialog.asksaveasfilename(parent=root, title='Save file as', initialfile=filename)
    receive_message("Receiving file " + filename + ". Please wait.")
    threading.Thread(target=receive_file, args=(ip, fileport, user, filename, filepath)).start()
        

def receive_file(ip, fileport, user, filename, filepath):
    try:
        file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        file_socket.connect((ip, int(fileport)))
        file_socket.send("WSP3".encode())
        file_socket.recv(1024) # Sync
        file_socket.send(user.encode())
        file_socket.recv(1024) # Sync
        file_socket.send("receive".encode())
        file_socket.recv(1024) # Sync
        file_socket.send(filename.encode())
        size = int(file_socket.recv(1024).decode())
        if size == 0:
            receive_message("File not found. It may have been deleted by the server.")
            return
        file_socket.send("Sync".encode())
        with open(filepath, "wb") as file:
            received = 0
            while received < size:
                data = file_socket.recv(1024)
                file.write(data)
                received += len(data)
        receive_message("File saved in " + filepath)
    except:
        receive_message("Error receiving file")
    finally:
        file_socket.close()

def stop_chat():
    global root
    global message_thread
    global stop_program_flag
    global server_socket
    global voice_enabled
    if voice_enabled:
        send_message("/voice")
    stop_program_flag = True
    try: voice_socket.close()
    except: pass
    try: message_thread.join()
    except: pass
    server_socket.close()
    create_menu()

def stop_program():
    global root
    global stop_program_flag
    stop_program_flag = True
    root.destroy()
    exit()

def receive_message_loop():
    global message_list
    global server_socket
    server_socket.settimeout(1)
    while not stop_program_flag:   
        try:
            message = server_socket.recv(1024).decode()
            receive_message(message)
        except: pass
    server_socket.close()
def voice_rcv_loop():
    global stop_program_flag
    global voice_enabled
    global voiceaddr
    global voice_socket
    global jitter_buffer
    global buffer_state
    
    while voice_enabled and not stop_program_flag:
        try:
            data, addr = voice_socket.recvfrom(4096)
            decoded_frame = decoder.decode(data, CHUNK)
            jitter_buffer.append(decoded_frame)
            # Buffer state management when filling, management when emptying is done in the play loop
            if buffer_state == BUFFER_WAIT_FILL and len(jitter_buffer) >= JITTER_BUFFER_OPTIMAL:
                buffer_state = BUFFER_RUNNING
            elif len(jitter_buffer) >= JITTER_BUFFER_MAX:
                buffer_state = BUFFER_WAIT_DRAIN
        except: pass

def voice_play_loop():
    global stop_program_flag
    global voice_enabled
    global jitter_buffer
    global buffer_state
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)
    while voice_enabled and not stop_program_flag:
        start_time = time.time()
        try:
            if len(jitter_buffer) == 0:
                buffer_state = BUFFER_WAIT_FILL
            if buffer_state == BUFFER_WAIT_FILL: # If buffer is too empty, play silence
                frame = b'\x00' * CHUNK * 2
            elif buffer_state == BUFFER_RUNNING: # If buffer is running correctly, play one frame
                frame = jitter_buffer.popleft()
            elif buffer_state == BUFFER_WAIT_DRAIN: # If buffer is too full, mix two frames
                frame1 = jitter_buffer.popleft()
                frame2 = jitter_buffer.popleft()
                frame1 = np.frombuffer(frame1, np.int16)
                frame2 = np.frombuffer(frame2, np.int16)
                frame = ((frame1 + frame2) / 2).astype(np.int16).tobytes()
                if len(jitter_buffer) <= JITTER_BUFFER_OPTIMAL:
                    buffer_state = BUFFER_RUNNING
            stream.write(frame)
            #print("Voice play loop time: " + str(time.time() - start_time))
        except Exception as e: pass #print("Error playing voice data: " + str(e))
    #print("Voice chat ended")
    stream.close()

def voice_send_loop():
    global stop_program_flag
    global voice_enabled
    global voiceaddr
    global voice_socket
    global muted
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    while voice_enabled and not stop_program_flag:
        start_time = time.time()
        try:
            frame = stream.read(CHUNK, exception_on_overflow=False)
            frame = (np.frombuffer(frame, np.int16) * gain).astype(np.int16).tobytes() # Apply gain
            if  not muted:
                encoded_frame = encoder.encode(frame, CHUNK)
                #print("Voice read loop time: " + str(time.time() - start_time))
                voice_socket.sendto(encoded_frame, voiceaddr)
        except Exception as e: pass #print("Error sending voice data: " + str(e))
    #print("Voice chat ended")
    stream.close()

def connect_button_click(user):
    global server_listbox
    global server_list
    try:
        if (user == "" or " " in user or "/" in user or ":" in user):
            #Creates an error window
            from tkinter import messagebox
            messagebox.showerror("Error", "Invalid username")
            return
        server = server_list[server_listbox.curselection()[0]]
        create_chat(server[0], server[1], server[2], user)
    except:
        pass

def add_button_click():
    add_window = Toplevel()
    add_window.geometry("200x200")
    add_window.resizable(False, False)
    add_window.title("Add a server")
    ip_label = ttk.Label(add_window, text="IP Address").pack()
    ip_entry = ttk.Entry(add_window, width=50, text="IP Address")
    ip_entry.pack()
    port_label = ttk.Label(add_window, text="Port").pack()
    port_entry = ttk.Entry(add_window, width=50, text="Port")
    port_entry.pack()
    name_label = ttk.Label(add_window, text="Name").pack()
    name_entry = ttk.Entry(add_window, width=50, text="Name")
    name_entry.pack()
    add_button = ttk.Button(add_window, text="Add", command = lambda: add_server(ip_entry.get(), port_entry.get(), name_entry.get(), add_window, error_label)).pack()
    error_label = ttk.Label(add_window, text="")
    error_label.pack()

def add_server(ip, port, name, add_window, error_label):
    global server_list
    global server_listbox
    try:
        server_list.append([ip, int(port), name])
        server_listbox.insert(END, name + " - " + ip + ":" + port)
        open("server_list.json", "w").write(json.dumps(server_list))
        add_window.destroy()
    except:
        error_label.config(text="Invalid IP or port")

def delete_server():
    global server_listbox
    global server_list
    try:
        server_list.pop(server_listbox.curselection()[0])
        server_listbox.delete(server_listbox.curselection()[0])
        open("server_list.json", "w").write(json.dumps(server_list))
    except: pass

#___________________________________________________________
#main program (what is run when the program is started)
#___________________________________________________________


def create_menu():
    global root
    global stop_program_flag
    global server_list
    global server_listbox

    try: root.destroy()
    except: pass
    stop_program_flag = False
    root = Tk()
    root.geometry("400x330")
    root.resizable(True, True)
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)
    root.title("Whatsapp 3")
    root.protocol("WM_DELETE_WINDOW", stop_program)
    welcometext = ttk.Label(root, text="Welcome to Whatsapp 3. \n Select a server and click connect or add a new server", anchor="center", justify="center").pack()
    try: server_list = json.loads(open("server_list.json").read())
    except: server_list = []
    scroll = ttk.Scrollbar(root)
    server_listbox = Listbox(root, yscrollcommand=scroll.set)
    for server in server_list:
        name = server[2]
        ip = server[0]
        port = server[1]
        server_listbox.insert(END, name + " - " + ip + ":" + str(port))
    server_listbox.pack(fill="x", expand=True)
    add_button = ttk.Button(root, text="Add", command = lambda: add_button_click()).pack()
    delete_button = ttk.Button(root, text="Delete", command = lambda: delete_server()).pack()
    user_label = ttk.Label(root, text="Username").pack()
    user_entry = ttk.Entry(root, width=10, text="Username")
    user_entry.pack()
    connect_button = ttk.Button(root, text="Connect", command = lambda: connect_button_click(user_entry.get())).pack()
    enter_action = root.bind('<Return>', lambda event: connect_button_click(user_entry.get()))
    root.mainloop()

def create_file_send_window(ip, fileport, user):
    #Creates a window with a file selector and a send button
    window = Toplevel()
    window.geometry("200x100")
    window.resizable(False, False)
    window.title("Send a file")
    file_label = ttk.Label(window, text="Select a file to send")
    file_label.pack()
    file_selector = ttk.Button(window, text="Select file", command = lambda: file_label.config(text=filedialog.askopenfilename(parent=window, title='Choose a file'))).pack()
    send_button = ttk.Button(window, text="Send", command = lambda: send_file(ip, fileport, user, file_label.cget("text"), window)).pack()
    window.mainloop()



def create_chat(ip, port, name, user):
    global root
    global message_list
    global message_entry
    global server_socket
    global message_thread
    global voice_enabled
    global voiceaddr
    global muted

    try: root.destroy()
    except: pass
    root = Tk()
    root.geometry("400x300")
    root.resizable(True, True)
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)
    root.title("Whatsapp 3: Chat with " + name)
    root.protocol("WM_DELETE_WINDOW", stop_chat)

    # Message frame and scroll setup
    message_frame = ttk.Frame(root)
    message_frame.grid(sticky='nsew')
    scroll = ttk.Scrollbar(message_frame)
    message_list = Listbox(message_frame, yscrollcommand=scroll.set)
    scroll.config(command=message_list.yview)
    scroll.pack(side="right", fill="y")
    message_list.pack(side="left", fill="both", expand=True)
    message_frame.grid_rowconfigure(0, weight=1)
    message_frame.grid_columnconfigure(0, weight=1)
    #Entry and buttons setup
    entry_frame = ttk.Frame(root)
    entry_frame.grid(sticky='nsew')
    message_entry = ttk.Entry(entry_frame, width=50)
    message_entry.grid(row=0, column=0)
    send_button = ttk.Button(entry_frame, width = 8, text="Send", command=lambda: send_message(message_entry.get())).grid(row=0, column = 1)
    down_button = ttk.Button(entry_frame, width = 2, text="↓", command=lambda: message_list.see('end')).grid(row=0, column = 2)
    quit_button = ttk.Button(root, text="Quit", command=stop_chat).grid(row=2, column = 0)
    file_button = ttk.Button(root, text="Send file", command=lambda: create_file_send_window(ip, fileport, user)).grid(row=3, column = 0)
    enter_action = root.bind('<Return>', lambda event: send_message(message_entry.get()))
    message_list.bind('<Double-1>', lambda event: chat_double_click(event, ip, fileport, user))
    #Network setup
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.settimeout(1)
    try:
        server_socket.connect((ip, port))
        server_socket.send(("WSP3").encode())
        server_socket.recv(1024) # Sync
        server_socket.send((user).encode())
        fileport = server_socket.recv(1024).decode()
        server_socket.send("Sync".encode())
        voiceport = server_socket.recv(1024).decode()
        server_socket.send("Sync".encode())
    except: receive_message("Error connecting to server")
    server_socket.settimeout(None)
    voice_enabled = False
    muted = False
    voiceaddr = (ip, int(voiceport))
    #Threads and loops
    message_thread = threading.Thread(target=receive_message_loop)
    message_thread.start()
    root.mainloop()

def test_audio():
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, output=True, frames_per_buffer=CHUNK)
    while True:
        data = stream.read(CHUNK)
        stream.write(data)


    


#Root window setup and audio init
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000 # 16000 Hz
CHUNK = 320 # 320 samples per frame (640 bytes), 20 ms per frame
#jitter buffer parameters
JITTER_BUFFER_OPTIMAL = 4
JITTER_BUFFER_MAX = 8
#buffer states
BUFFER_WAIT_FILL = 0
BUFFER_RUNNING = 1
BUFFER_WAIT_DRAIN = 2
jitter_buffer = deque()
buffer_state = BUFFER_WAIT_FILL
gain = 1.0
audio = pyaudio.PyAudio()
encoder = opuslib.Encoder(RATE, CHANNELS, opuslib.APPLICATION_AUDIO)
decoder = opuslib.Decoder(RATE, CHANNELS)
voice_enabled = False
create_menu()


