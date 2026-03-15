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
from tkinter import messagebox
import pyaudio
import opuslib
from collections import deque
import numpy as np
import uuid
import whatsapp3_client

root = None
message_list = None
message_entry = None
server_list = []
server_listbox = None

# ____________________________________________________________
# Receive and send functions, called by the GUI elements and the client backend callbacks
# ____________________________________________________________

def receive_message(message):
    global message_list
    if message_list is None:
        return
    at_bottom = message_list.yview()[1] == 1.0
    message_list.insert(END, message)
    if at_bottom:
        message_list.see('end')

def send_message(message):
    global message_list
    global message_entry

    if message_list is None or message_entry is None:
        return

    message_list.insert(END, "YOU: " + message)
    message_entry.delete(0, 'end') #clear the entry box
    message_list.see('end')
    client_backend.send_chat_message(message)

#def send_file(ip, fileport, user, filepath, window):
#    if filepath == "Select a file to send" or filepath == "":
#        return
#    try:
#        file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#        file_socket.connect((ip, int(fileport)))
#        file_socket.send("WSP3".encode())
#        file_socket.recv(1024) # Sync
#        file_socket.send(user.encode())
#        file_socket.recv(1024) # Sync
#        file_socket.send("send".encode())
#        file_socket.recv(1024) # Sync
#        filename = filepath.split("/")[-1]
#        if (" " in filename): filename = filename.replace(" ", "_")
#        file_socket.send(filename.encode())
#        file_socket.recv(1024) # Sync
#        file = open(filepath, "rb")
#        filedata = file.read()
#        filesize = len(filedata)
#        file_socket.send(str(filesize).encode())
#        file_socket.recv(1024) # Sync
#        receive_message("Sending file " + filename + ". Please wait.")
#        file_socket.sendall(filedata)
#    except:
#        receive_message("Error sending file")
#    finally:
#        file_socket.close()
#        window.destroy()



# ___________________________________________________________
# Other small functions for GUI and program control
# ___________________________________________________________


#def chat_double_click(event, ip, fileport, user):
#    global message_list
#    message = message_list.get(message_list.nearest(event.y))
#    if not("sent file" in message) or ":" in message:
#        return
#    filename = message.split(" ")[-5]
#    filepath = filedialog.asksaveasfilename(parent=root, title='Save file as', initialfile=filename)
#    receive_message("Receiving file " + filename + ". Please wait.")
#    threading.Thread(target=receive_file, args=(ip, fileport, user, filename, filepath), daemon=True).start()

#def create_file_send_window(ip, fileport, user):
#    #Creates a window with a file selector and a send button
#    window = Toplevel()
#    window.geometry("200x100")
#    window.resizable(False, False)
#    window.title("Send a file")
#    file_label = ttk.Label(window, text="Select a file to send")
#    file_label.pack()
#    file_selector = ttk.Button(window, text="Select file", command = lambda: file_label.config(text=filedialog.askopenfilename(parent=window, title='Choose a file'))).pack()
#    send_button = ttk.Button(window, text="Send", command = lambda: send_file(ip, fileport, user, file_label.cget("text"), window)).pack()
#    window.mainloop()

def stop_program():
    global root
    clear_backend_callbacks()
    client_backend.disconnect()
    if root is not None and root.winfo_exists():
        root.destroy()


def clear_root():
    global message_list
    global message_entry
    global server_listbox

    if root is None or not root.winfo_exists():
        return
    for widget in root.winfo_children():
        widget.destroy()
    message_list = None
    message_entry = None
    server_listbox = None


def clear_backend_callbacks():
    client_backend.on_chat_message = None
    client_backend.on_system_message = None
    client_backend.on_file_notice = None
    client_backend.on_disconnect = None


def schedule_on_ui(callback):
    if root is not None and root.winfo_exists():
        root.after(0, callback)


def show_disconnect_warning(reason):
    if root is None or not root.winfo_exists():
        return
    messagebox.showwarning("Disconnected", "Disconnected from server. Reason: " + reason, parent=root)


def leave_chat():
    clear_backend_callbacks()
    client_backend.disconnect()
    create_menu()


#___________________________________________________________
# Main menu (server list) functions
#___________________________________________________________

def connect_button_click(user):
    global server_listbox
    global server_list
    try:
        if (user == "" or " " in user or "/" in user or ":" in user):
            #Creates an error window
            messagebox.showerror("Error", "Invalid username", parent=root)
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
# Main window creation functions
#___________________________________________________________


def create_menu(disconnect_reason=None):
    global root
    global server_list
    global server_listbox
    global client_backend

    clear_root()
    clear_backend_callbacks()
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
    if disconnect_reason: # Warning window if the chat was closed due to server disconnection or error
        root.after_idle(lambda reason=disconnect_reason: show_disconnect_warning(reason))


def create_chat(ip, port, name, user):
    global root
    global message_list
    global message_entry
    global client_backend

    clear_root()
    root.geometry("400x300")
    root.resizable(True, True)
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)
    root.title("Whatsapp 3: Chat with " + name)
    root.protocol("WM_DELETE_WINDOW", leave_chat)

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
    quit_button = ttk.Button(root, text="Quit", command=leave_chat).grid(row=2, column = 0)
    #file_button = ttk.Button(root, text="Send file", command=lambda: create_file_send_window(ip, fileport, user)).grid(row=3, column = 0)
    enter_action = root.bind('<Return>', lambda event: send_message(message_entry.get()))
    #message_list.bind('<Double-1>', lambda event: chat_double_click(event, ip, fileport, user))
    # Backend setup
    clear_backend_callbacks()
    client_backend.on_chat_message = lambda sender, content: schedule_on_ui(lambda: receive_message(sender + ": " + content))
    client_backend.on_system_message = lambda content: schedule_on_ui(lambda: receive_message("SYSTEM: " + content))
    client_backend.on_file_notice = lambda sender, filename: schedule_on_ui(lambda: receive_message(sender + " sent file " + filename))
    client_backend.on_disconnect = lambda reason: schedule_on_ui(lambda: create_menu(disconnect_reason=reason))
    client_backend.connect(ip, port, user)

client_backend = whatsapp3_client.Whatsapp3Client()
root = Tk()
create_menu()
root.mainloop()


