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
    global instream
    global outstream
    global client_backend

    message_entry.delete(0, 'end')

    if message_list is None or message_entry is None or message.strip() == "":
        return
    
    if message == "/voice":
        if client_backend.voice_enabled:
            client_backend.voice_toggle()
            message_list.insert(END, "You have left the voice chat.")
            message_list.see('end')
        else:
            instream = audio.open(format=client_backend.FORMAT, channels=client_backend.CHANNELS, rate=client_backend.RATE, input=True, frames_per_buffer=client_backend.CHUNK)
            outstream = audio.open(format=client_backend.FORMAT, channels=client_backend.CHANNELS, rate=client_backend.RATE, output=True, frames_per_buffer=client_backend.CHUNK)
            client_backend.voice_toggle()
            threading.Thread(target=get_microphone_data, daemon=True).start()
            message_list.insert(END, "You have joined the voice chat.")
            message_list.see('end')
        return

    if message == "/mute":
        if client_backend.voice_enabled:
            if client_backend.muted:
                client_backend.muted = False
                message_list.insert(END, "You have unmuted yourself.")
                message_list.see('end')
            else:
                client_backend.muted = True
                message_list.insert(END, "You have muted yourself.")
                message_list.see('end')
        else:
            message_list.insert(END, "You are not in the voice chat.")
            message_list.see('end')
        return
    
    if message.startswith("/gain"):
        if client_backend.voice_enabled:
            try:
                gain_value = float(message.split(" ")[1])
                client_backend.gain = gain_value
                message_list.insert(END, "Your voice gain has been set to " + str(gain_value) + ".")
                message_list.see('end')
            except:
                message_list.insert(END, "Invalid gain value. Usage: /gain [value]")
                message_list.see('end')
        else:
            message_list.insert(END, "You are not in the voice chat.")
            message_list.see('end')
        return

    message_list.insert(END, "YOU: " + message)
    message_list.see('end')
    client_backend.send_chat_message(message)

def get_microphone_data():
    """
    Get frames of audio data from the microphone and send them to the client backend to be transmitted to the server.
    """
    global client_backend
    global instream
    global outstream
    global audio

    while client_backend.voice_enabled and client_backend.running:
        try:
            frame = instream.read(client_backend.CHUNK, exception_on_overflow=False)
            client_backend.audioqueue.put(frame)
        except Exception as e: pass #print("Error reading microphone data: " + str(e))
    instream.stop_stream()
    instream.close()
    outstream.stop_stream()
    outstream.close()

def play_audio_frame(frame):
    """
    Play a raw audio frame through the audio output.
    """
    global audio
    global outstream

    try:
        outstream.write(frame)
    except Exception as e: pass #print("Error playing audio frame: " + str(e))
    


# ___________________________________________________________
# Other small functions for GUI and program control
# ___________________________________________________________


def chat_double_click(event):
    global message_list
    message = message_list.get(message_list.nearest(event.y))
    if not("sent file" in message) or ":" in message:
        return
    filename = message.split(" ")[-5]
    filepath = filedialog.asksaveasfilename(parent=root, title='Save file as', initialfile=filename)
    create_file_receive_window(filename, filepath)

def create_file_receive_window(filename, save_path):
    """
    Creates a window to receive a file from the server and show the progress on a progress bar.
    """

    def receive_and_return():
        """
        Internal function meant to be run on a sepparate thread so the GUI remains responsive.
        """
        result = client_backend.receive_file(filename, save_path, update_progress_threadsafe)
        if result == "success":
            messagebox.showinfo("Success", "File received successfully.", parent=window)
        elif result == "not_connected":
            messagebox.showerror("Error", "File port not available.", parent=window)
        elif result == "file_not_found":
            messagebox.showerror("Error", "The file was not found on the server.", parent=window)
        elif result == "no_response":
            messagebox.showerror("Error", "The server did not respond.", parent=window)
        elif result == "transfer_error":
            messagebox.showerror("Error", "Unknown error occurred during file transfer.", parent=window)
        else:
            messagebox.showerror("Error", "Unknown error occurred.", parent=window)
        update_progress_threadsafe(0) # Reset progress bar after transfer completion or error

    def update_progress_threadsafe(percentage):
        """
        Internal function to update the progress bar in the file receive window.
        """
        if window.winfo_exists():
            window.after(0, lambda p=percentage: progress_bar.configure(value=p))

    window = Toplevel()
    window.geometry("200x50")
    window.resizable(False, False)
    window.title(filename)
    progress_bar = ttk.Progressbar(window, orient='horizontal', mode='determinate', length=180)
    progress_bar.pack(pady=10)
    threading.Thread(target=receive_and_return, daemon=True).start()


def create_file_send_window():
    """
    Creates a window to select and send a file to the server.
    """
    window = Toplevel()
    window.geometry("200x100")
    window.resizable(False, False)
    window.title("Send a file")
    file_label = ttk.Label(window, text="Select a file to send")
    file_label.pack()
    file_selector = ttk.Button(window, text="Select file", command = lambda: file_label.config(text=filedialog.askopenfilename(parent=window, title='Choose a file'))).pack()
    send_button = ttk.Button(window, text="Send", command = lambda: on_send_click()).pack()
    progress_bar = ttk.Progressbar(window, orient='horizontal', mode='determinate', length=180)
    progress_bar.pack(pady=5)
    def on_send_click():
        """
        Internal function called when the send button is clicked.
        It starts a thread to send the file.
        """
        filepath = file_label.cget("text")
        threading.Thread(target=send_and_return, args=(filepath, update_progress_threadsafe), daemon=True).start()

    def send_and_return(filepath, update_callback):
        """
        Internal function meant to be run on a sepparate thread so the GUI remains responsive.
        """
        result = client_backend.send_file(filepath, update_callback)
        type = result.get("type", "unknown_error")
        if type == "success":
            messagebox.showinfo("Success", "File sent successfully.", parent=window)
        elif type == "not_connected":
            messagebox.showerror("Error", "File port not available.", parent=window)
        elif type == "file_not_found":
            messagebox.showerror("Error", "File not found. Please select a valid file.", parent=window)
        elif type == "no_response":
            messagebox.showerror("Error", "The server did not respond.", parent=window)
        elif type == "transfer_error":
            messagebox.showerror("Error", "Unknown error occurred during file transfer.", parent=window)
        elif type == "transfer_reject":
            messagebox.showerror("Error", "The server rejected the file transfer. Upload a file smaller than " + str(result['max_size']) + " MB.", parent=window)
        else:
            messagebox.showerror("Error", "Unknown error occurred.", parent=window)
        update_progress_threadsafe(0) # Reset progress bar after transfer completion or error
        
    def update_progress_threadsafe(percentage):
        """
        Internal function to update the progress bar in the file sending window.
        """
        if window.winfo_exists():
            window.after(0, lambda p=percentage: progress_bar.configure(value=p))


def stop_program():
    global root
    global audio
    clear_backend_callbacks()
    client_backend.disconnect()
    audio.terminate()
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
    client_backend.on_new_client = None
    client_backend.on_disconnected_client = None
    client_backend.on_file_notice = None
    client_backend.on_disconnect = None
    client_backend.on_connect = None
    client_backend.on_new_voice_client = None
    client_backend.on_disconnected_voice_client = None
    client_backend.onaudioframe = None


def schedule_on_ui(callback):
    if root is not None and root.winfo_exists():
        root.after(0, callback)


def show_disconnect_warning(reason, exception):
    if root is None or not root.winfo_exists():
        return
    message = "Disconnected from server. Reason: "
    if reason == "no_response":
        message += "The server did not respond."
    elif reason == "username_taken":
        message += "The username is already taken."
    elif reason == "malformed_data":
        message += "Received malformed data from the server."
    elif reason == "connection_error":
        message += "Unknown connection error occurred."
    elif reason == "send_error":
        message += "Unknown error occurred while sending data to the server."
    elif reason == "receive_error":
        message += "Unknown error occurred while receiving data from the server."
    elif reason == "closed_by_server":
        message += "The server closed the connection."
    else:
        message += "Unknown reason."
    
    # Exception details are hidden by default, but can be shown by clicking a button
    def toggle_exception_details():
        """
        Internal function to toggle the visibility of the exception details in the warning window.
        """
        if details_label.winfo_viewable():
            details_label.pack_forget()
            toggle_button.config(text="Show exception details")
        else:
            details_label.pack()
            toggle_button.config(text="Hide exception details")
    
    # Create the warning window with the message and a button to toggle exception details
    warning_window = Toplevel()
    warning_window.geometry("230x200")
    warning_window.resizable(False, False)
    warning_window.title("Disconnected")
    warning_label = ttk.Label(warning_window, text=message, wraplength=210).pack(pady=10)
    if exception is not None:
        toggle_button = ttk.Button(warning_window, text="Show exception details", command=toggle_exception_details)
        toggle_button.pack()
        details_label = ttk.Label(warning_window, text=str(exception), wraplength=210)


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


def create_menu(disconnect_reason=None, disconnect_exception=None):
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
    welcometext = ttk.Label(root, text="Welcome to Whatsapp 3 (v2.0). \n Select a server and click connect or add a new server", anchor="center", justify="center").pack()
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
        root.after_idle(lambda reason=disconnect_reason, exception=disconnect_exception: show_disconnect_warning(reason, exception))


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
    file_button = ttk.Button(root, text="Send file", command=lambda: create_file_send_window()).grid(row=3, column = 0)
    enter_action = root.bind('<Return>', lambda event: send_message(message_entry.get()))
    message_list.bind('<Double-1>', lambda event: chat_double_click(event))
    # Backend setup
    clear_backend_callbacks()
    client_backend.on_chat_message = lambda sender, content: schedule_on_ui(lambda: receive_message(sender + ": " + content))
    client_backend.on_new_client = lambda new_username: schedule_on_ui(lambda: receive_message(new_username + " has joined the chat."))
    client_backend.on_disconnected_client = lambda disconnected_username: schedule_on_ui(lambda: receive_message(disconnected_username + " has left the chat."))
    client_backend.on_file_notice = lambda sender, filename: schedule_on_ui(lambda: receive_message(sender + " sent file " + filename + " (double click to save)"))
    client_backend.on_disconnect = lambda reason, exception: schedule_on_ui(lambda: create_menu(disconnect_reason=reason, disconnect_exception=exception))
    client_backend.on_connect = lambda clientlist, voice_clientlist: schedule_on_ui(lambda: receive_message("Welcome to server. Currently " + str(len(clientlist)) + " other clients connected (" + str(len(voice_clientlist)) + " in voice chat)."))
    client_backend.on_new_voice_client = lambda new_username: schedule_on_ui(lambda: receive_message(new_username + " has joined the voice chat."))
    client_backend.on_disconnected_voice_client = lambda disconnected_username: schedule_on_ui(lambda: receive_message(disconnected_username + " has left the voice chat."))
    client_backend.on_audio_frame = lambda frame: play_audio_frame(frame)
    client_backend.connect(ip, port, user)

client_backend = whatsapp3_client.Whatsapp3Client()
audio = pyaudio.PyAudio()
root = Tk()
create_menu()
root.mainloop()