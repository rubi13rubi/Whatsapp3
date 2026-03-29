import flet as ft
import json
import whatsapp3_client
import pyaudio
import threading
import os
import sys

class ServerCard(ft.Container):
    """
    A custom Flet container to display server information and a connect button.
    """
    def __init__(self, server_name, server_ip, server_port, server_number, on_connect_click, on_delete_click):
        """
        Args:
            server_name (str): The name of the server to display.
            server_ip (str): The IP address of the server to display.
            server_port (int): The port number of the server to display.
            server_number (int): The index of the server in the server list.
            on_connect_click (function): A callback function to call when the connect button is clicked, with server_ip and server_port as arguments.
            on_delete_click (function): A callback function to call when the delete button is clicked, with server_number as an argument.
        """
        super().__init__()
        self.padding = 10
        self.border_radius = 5
        self.bgcolor = ft.Colors.PRIMARY_CONTAINER
        self.content = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls =[
                ft.Column([
                    ft.Text(server_name, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY_CONTAINER),
                    ft.Text(f"{server_ip}:{server_port}", size=14, color=ft.Colors.ON_PRIMARY_CONTAINER)
                ], spacing=5, expand=True),
                ft.Button(
                    "Connect",
                    on_click=lambda e: on_connect_click(server_ip, server_port, server_name),
                    icon=ft.Icons.LINK,
                    bgcolor=ft.Colors.INVERSE_PRIMARY,
                    color=ft.Colors.ON_PRIMARY_CONTAINER,
                    ),
                ft.IconButton(
                    ft.Icons.DELETE,
                    bgcolor=ft.Colors.INVERSE_PRIMARY,
                    icon_color=ft.Colors.ON_PRIMARY_CONTAINER,
                    on_click=lambda e: on_delete_click(server_number)
                )
            ]
        )

class EditableNameField(ft.Container):
    """Widget to insert the user's name and edit it when needed."""
    
    def __init__(self, initial_name, on_name_changed):
        """
        Args:
            initial_name (str): The initial name to display.
            on_name_changed (function): Callback that receives the new name.
        """
        super().__init__()
        self.initial_name = initial_name
        self.on_name_changed = on_name_changed
        self.is_editing = False
        self.name_text = ft.Text(
            initial_name, 
            size=16, 
            color=ft.Colors.ON_PRIMARY,
        )
        self.name_input = ft.TextField(
            value=initial_name,
            on_submit=self.save_name,
            expand=True,
            border = ft.InputBorder.UNDERLINE,
            cursor_color=ft.Colors.ON_PRIMARY,
            border_color=ft.Colors.ON_PRIMARY,
            color=ft.Colors.ON_PRIMARY,
            selection_color=ft.Colors.ON_PRIMARY,
            text_size=16,
            dense=True,
            autofocus=True
        )
        self.content = ft.Row(
            [
                ft.Text(
                    f"Welcome back, ", 
                    size=16, 
                    color=ft.Colors.ON_PRIMARY
                ),
                self.name_text,
                ft.IconButton(
                    ft.Icons.EDIT,
                    icon_color=ft.Colors.ON_PRIMARY,
                    on_click=self.toggle_edit_mode
                )
            ],
            spacing=10
        )

    def toggle_edit_mode(self, e):
        """Toggle between display and edit mode for the name field."""
        self.is_editing = not self.is_editing
        if self.is_editing:
            # Change to edit mode
            self.content.controls[1] = self.name_input
            self.update()
        else:
            # Change back to display mode
            self.content.controls[1] = self.name_text
            self.update()
    
    def save_name(self, e):
        """Save the new name and call the callback to update config."""
        new_name = self.name_input.value.strip()
        if new_name:
            self.initial_name = new_name
            self.name_text.value = new_name
            self.on_name_changed(new_name)  # Callback
            self.toggle_edit_mode(None)  # Switch back to display mode

class MessageContainer(ft.Container):
    """Container that displays the message list."""
    def __init__(self):
        super().__init__()
        self.bgcolor = ft.Colors.PRIMARY_CONTAINER
        self.border_radius = 5
        self.padding = 10
        self.expand = True
        self.content = ft.ListView(
            controls=[],
            spacing=10,
            padding=10,
            scroll= ft.ScrollMode.AUTO,
            expand=True,
            auto_scroll=True,
        )
        self.url_launcher = ft.UrlLauncher() # UrlLauncher instance to handle link taps in messages

    async def update_interface(self):
        """Helper method to update the interface asynchronously."""
        self.update()
    
    def add_message(self, sender, content, page):
        """Adds a message to the message list."""
        async def on_link_tap(e):
            """Handles link taps in messages and opens them in the default web browser."""
            url = e.data
            await self.url_launcher.launch_url(url) # Use UrlLauncher to open the link in the default web browser
        message_control = ft.Container(
            content=ft.Column([
                ft.Text(sender, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SECONDARY_CONTAINER),
                ft.Markdown(content,
                            selectable=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            on_tap_link=on_link_tap
                            )
            ], spacing=5),
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=5,
            padding=10
        )
        self.content.controls.append(message_control)
        page.run_task(self.update_interface)
    
    def add_notification(self, content, page):
        """Adds a notification message to the message list."""
        notification_control = ft.Container(
            content=ft.Text(content, size=12, color=ft.Colors.ON_SECONDARY_CONTAINER, text_align=ft.TextAlign.CENTER),
            bgcolor=ft.Colors.INVERSE_PRIMARY,
            border_radius=5,
            padding=10
        )
        self.content.controls.append(notification_control)
        page.run_task(self.update_interface)
    
    def add_file_notice(self, sender, filename, page):
        """Adds a file notice message to the message list."""
        
        def receive_and_return(filepath):
            """
            Receives the file from the server showing the progress and shows the result.
            This should be done on a sepparate thread to avoid blocking the interface.
            """
            def update_progress(percentage):
                """Updates the progress bar with the current progress value."""
                progress.value = percentage / 100.0
                page.run_task(self.update_interface)

            progress = ft.ProgressBar(width=200, bgcolor=ft.Colors.INVERSE_PRIMARY, color=ft.Colors.ON_PRIMARY_CONTAINER)
            file_notice_control.content.controls = [
                ft.Text(sender, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SECONDARY_CONTAINER),
                ft.Text(f"Downloading file: {filename}", size=14, color=ft.Colors.ON_SECONDARY_CONTAINER),
                progress
            ]
            page.run_task(self.update_interface)
            result = client_backend.receive_file(filename, filepath, update_progress) # Receive the file using the backend client and update the progress bar

            if result == "success":
                file_notice_control.content.controls = normal_controls + [ft.Text(f"File successfully received.", size=14, color=ft.Colors.ON_SECONDARY_CONTAINER)]
            else:
                error_message = "Unknown error."
                if result == "not_connected":
                    error_message = "File port not available."
                elif result == "file_not_found":
                    error_message = "File not found."
                elif result == "no_response":
                    error_message = "The server did not respond."
                elif result == "transfer_error":
                    error_message = "Error during file transfer."
                file_notice_control.content.controls = normal_controls + [ft.Text(f"Error receiving file: {error_message}", size=14, color=ft.Colors.ERROR)]
            page.run_task(self.update_interface)
        
        def select_path_and_download(e):
            """Opens a file dialog to select the download location and starts the file receiving thread."""
            file_picker = ft.FilePicker()
            async def pick_file():
                path = await file_picker.save_file(dialog_title="Select download location", file_name=filename)
                threading.Thread(target=receive_and_return, args=(path,), daemon=True).start()
            page.run_task(pick_file)                

        normal_controls = [
            ft.Text(sender, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SECONDARY_CONTAINER),
            ft.Text(f"Sent a file: {filename}", size=14, color=ft.Colors.ON_SECONDARY_CONTAINER),
            ft.Button("Download", icon=ft.Icons.DOWNLOAD, bgcolor=ft.Colors.INVERSE_PRIMARY, color=ft.Colors.ON_PRIMARY_CONTAINER, on_click=select_path_and_download)
        ]

        file_notice_control = ft.Container(
            content=ft.Column(normal_controls, spacing=5),
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=5,
            padding=10
        )
        self.content.controls.append(file_notice_control)
        page.run_task(self.update_interface)
    
    def add_file_upload(self, page):
        """
        Adds a file upload notice to the message list.
        Manages the file upload process and updates the interface with the upload progress and result.
        """    

        file_upload_control = ft.Container(
            content=ft.Column([
                ft.Text(f"", size=14, color=ft.Colors.ON_SECONDARY_CONTAINER),
                ft.ProgressBar(width=200, bgcolor=ft.Colors.INVERSE_PRIMARY, color=ft.Colors.ON_PRIMARY_CONTAINER)
            ], spacing=5),
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=5,
            padding=10
        )
        self.content.controls.append(file_upload_control)
        page.run_task(self.update_interface)

        def upload_file(filepath):
            """
            Uploads the file to the server and updates the interface with the result.
            This should be done on a sepparate thread to avoid blocking the interface.
            """
            def update_progress(percentage):
                """Updates the progress bar with the current progress value."""
                file_upload_control.content.controls[1].value = percentage / 100.0
                page.run_task(self.update_interface)
            
            result = client_backend.send_file(filepath, update_progress) # Send the file using the backend client and update the progress bar
            type = result.get("type", "unknown_error")

            if type == "success":
                self.content.controls.remove(file_upload_control) # Remove the file upload notice from the message list after successful upload
            else:
                error_message = "Unknown error."
                if type == "not_connected":
                    error_message = "File port not available."
                elif type == "file_not_found":
                    error_message = "File not found."
                elif type == "no_response":
                    error_message = "The server did not respond."
                elif type == "transfer_error":
                    error_message = "Error during file transfer."
                elif type == "transfer_reject":
                    error_message = "File transfer rejected by server. Upload a file smaller than " + str(result['max_size']) + " MB."
                file_upload_control.content.controls = [
                    ft.Text(f"Error uploading file: {error_message}", size=14, color=ft.Colors.ERROR)
                ]
            page.run_task(self.update_interface)
        
        file_picker = ft.FilePicker()
        async def pick_file():
            path = await file_picker.pick_files(dialog_title="Select file to upload")
            if path[0].path:
                threading.Thread(target=upload_file, args=(path[0].path,), daemon=True).start() # Start a thread to upload the file to the server
                file_upload_control.content.controls[0].value = f"Uploading file: {os.path.basename(path[0].path)}"
            else:
                self.content.controls.remove(file_upload_control) # Remove the file upload notice if no file was selected
                page.run_task(self.update_interface)
        
        page.run_task(pick_file)

class UserListContainer(ft.Container):
    """Container that displays the list of connected users."""
    def __init__(self):
        super().__init__()
        self.bgcolor = ft.Colors.PRIMARY_CONTAINER
        self.border_radius = 5
        self.padding = 10
        self.expand = True
        self.content = ft.ListView(
            controls=[],
            spacing=10,
            padding=10,
            scroll= ft.ScrollMode.AUTO,
            expand=True,
        )
    
    def update_user_list(self, user_list, page):
        """Updates the user list display with the current list of connected users."""
        self.content.controls.clear()
        for user in user_list:
            user_control = ft.Container(
                content=ft.Text(user, size=14, color=ft.Colors.ON_SECONDARY_CONTAINER),
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                border_radius=5,
                padding=10
            )
            self.content.controls.append(user_control)
        async def update_interface():
            """Updates the interface to show the new user list."""
            self.update()
        page.run_task(update_interface)

def clear_backend_callbacks():
    """Clears the backend callbacks to prevent unwanted calls after disconnection."""
    global client_backend
    client_backend.on_chat_message = None
    client_backend.on_disconnect = None
    client_backend.on_new_client = None
    client_backend.on_disconnected_client = None
    client_backend.on_connect = None
    client_backend.on_new_voice_client = None
    client_backend.on_disconnected_voice_client = None
    client_backend.on_file_notice = None
    client_backend.on_audio_frame = None

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

def get_base_path():
    """
    Get the base path for the application,
    which is the directory of the executable when frozen, or the directory of the script when not frozen.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def save_data(page):
    """
    Saves the server list and config to json files in the base path of the application.
    """
    global server_list, server_list_path, config, config_path
    with open(server_list_path, "w") as f:
        json.dump(server_list, f)
    with open(config_path, "w") as f:
        json.dump(config, f)
    page.run_task(page.window.destroy) # Close the application window after saving data and disconnecting

def recode_name(name):
    """Recodes the string for display purposes."""
    try:
        return name.encode('cp1252').decode('utf-8')
    except:
        return name

def main(page: ft.Page):
    """
    Main function to set up the Flet app and display the screens.
    This function is called when the Fleet app starts.
    Args:
        page (ft.Page): The main page of the Flet app.
    """
    global server_list
    global config
    page.theme = ft.Theme(color_scheme_seed=config.get("color_seed")) # Set the theme
    page.window.prevent_close = True # Prevent the window from closing immediately to allow saving data
    page.window.on_event = lambda e: save_data(page) if e.type.name == "CLOSE" else None # Save data when the app is closed
    
    def navigate_to_server_list(e = None, reason = None, exception = None):
        """
        Navigates to the server list screen when called.
        Args:
            e: The event that triggered the navigation (optional).
            reason: The reason for the disconnection (optional).
            exception: The exception that caused the error (optional).
        """
        page.controls.clear() # Clear the current screen
        page.title = "Whatsapp 3"
        page.window.width = 400
        page.window.height = 600
        page.bgcolor = ft.Colors.PRIMARY
        page.window.icon = os.path.join(get_base_path(), "assets", "icon_transparent.ico")
        # Get the server list from the json file
        
        page.add(server_list_screen(server_list)) # Add the server list screen to the page
        if reason or exception: # Show an error message if there is a reason or exception for disconnection
            error_message = "Disconnected from server."
            if reason == "no_response":
                error_message = "The server did not respond."
            elif reason == "closed_by_server":
                error_message = "Connection closed by server."
            elif reason == "username_taken":
                error_message = "The username is already taken by another client."
            elif reason == "malformed_data":
                error_message = "Error receiving data: Received data from the server was not valid JSON."
            elif reason == "connection_error":
                error_message = "Unknown error trying to connect to the server."
            elif reason == "send_error":
                error_message = "Unknown error while sending data to the server."
            elif reason == "receive_error":
                error_message = "Unknown error while receiving data from the server."

            if exception:
                error_message += f" Exception: {str(exception)}."
            page.dialog = ft.AlertDialog(
                title=ft.Text("Connection Error"),
                content=ft.Text(error_message),
                actions=[ft.Button("OK", on_click=lambda e: setattr(page.dialog, "open", False))]
            )
            page.overlay.append(page.dialog)
            page.dialog.open = True
        async def update_interface():
            page.update() # Update the page to reflect the changes
        page.run_task(update_interface)
    
    def show_add_server_dialog(e):
        """
        Shows a dialog to add a new server when called.
        Args:
            e: The event that triggered the dialog (optional).
        """
        page.dialog = add_server_dialog() # Reset the dialog content
        page.overlay.append(page.dialog) # Add the dialog to the page overlay
        page.dialog.open = True
        page.update()
    
    def navigate_to_chat_screen(server_ip, server_port, server_name):
        """
        Navigates to the chat screen for the specified server.
        Args:
            server_ip (str): The IP address of the server to connect to.
            server_port (int): The port number of the server to connect to.
            server_name (str): The name of the server to connect to.
        """
        global client_backend
        page.controls.clear() # Clear the current screen
        page.title = "Whatsapp 3 - " + server_name
        page.window.width = 800
        page.window.height = 600
        page.bgcolor = ft.Colors.PRIMARY
        # Add chat screen controls here (placeholder for now)
        message_container = MessageContainer()
        user_list_container = UserListContainer()
        voice_user_list_container = UserListContainer()
        user_list = [config.get("name", "Guest")] # Start with the user's own name in the user list
        voice_user_list = [] # List to keep track of users in voice chat
        message_textfield = ft.TextField(
            expand=True,
            autofocus=True,
            hint_text="Type your message here...",
            on_submit=lambda e: send_message(e),
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_color=ft.Colors.PRIMARY_CONTAINER,
            color=ft.Colors.ON_SECONDARY_CONTAINER,
            cursor_color=ft.Colors.ON_SECONDARY_CONTAINER,
            )
        
        # Voice chat controls
        voice_chat_row_inactive_controls = [
            ft.Button("Connect to Voice Chat", icon=ft.Icons.ADD_LINK, on_click=lambda e: start_voice_chat(e), expand=True, bgcolor=ft.Colors.INVERSE_PRIMARY, color=ft.Colors.ON_PRIMARY_CONTAINER)
        ]
        mute_button = ft.IconButton(ft.Icons.MIC, icon_color=ft.Colors.ON_PRIMARY_CONTAINER, bgcolor = ft.Colors.INVERSE_PRIMARY, on_click=lambda e: mute_toggle(e), expand=True) # Placeholder for mute functionality
        voice_chat_row_active_controls = [
            ft.IconButton(ft.Icons.LINK_OFF, icon_color=ft.Colors.ON_PRIMARY_CONTAINER, bgcolor = ft.Colors.INVERSE_PRIMARY, on_click=lambda e: stop_voice_chat(e), expand=True),
            mute_button,
            ft.IconButton(ft.Icons.SETTINGS, icon_color=ft.Colors.ON_PRIMARY_CONTAINER, bgcolor = ft.Colors.INVERSE_PRIMARY, on_click=lambda e: show_voice_chat_settings(e), expand=True) # Placeholder for voice chat settings
        ]
        voice_chat_row = ft.Row(voice_chat_row_inactive_controls, height = 50) # Start with the inactive voice chat controls

        input_device_dropdown = ft.Dropdown(
            options=[], on_text_change=lambda e: change_input_device(e)
        )

        output_device_dropdown = ft.Dropdown(
            options=[], on_text_change=lambda e: change_output_device(e)
        )
        gain_slider = ft.Slider(min=0.0, max=2.0, value=config.get("gain", 1.0), on_change_end=lambda e: on_gain_change(e))
        noise_suppression_checkbox = ft.Checkbox(label="Enable noise suppression", value=config.get("noise_suppressor", False), on_change=lambda e: on_noise_suppressor_toggle(e))
        warning_message = ft.Text("", color=ft.Colors.ERROR, size=12)
        page.dialog = ft.AlertDialog(
                title=ft.Text("Voice Chat Settings"),
                content=ft.Column([
                    ft.Text("Input device:"),
                    input_device_dropdown,
                    ft.Text("Output device:"),
                    output_device_dropdown,
                    ft.Text("Gain:"),
                    gain_slider,
                    noise_suppression_checkbox,
                    warning_message
                ]),
                actions=[ft.Button("OK", on_click=lambda e: setattr(page.dialog, "open", False))]
            )
        page.overlay.append(page.dialog)

        def on_connect(client_list, voice_client_list):
            """Callback for when the client successfully connects to the server."""
            nonlocal user_list, voice_user_list
            user_list.extend(client_list) # Add the connected clients to the user list
            user_list_container.update_user_list(user_list, page) # Update the user list display with the connected users
            voice_user_list = voice_client_list # Set the voice user list to the connected voice clients
            voice_user_list_container.update_user_list(voice_user_list, page) # Update the voice user list display

        def on_new_client(new_username):
            """Callback for when a new client connects to the server."""
            user_list.append(new_username)
            user_list_container.update_user_list(user_list, page) # Update the user list display with the new client
            message_container.add_notification(f"{new_username} joined the chat.", page) # Notification message for new client joining

        def on_disconnected_client(disconnected_username):
            """Callback for when a client disconnects from the server."""
            if disconnected_username in user_list:
                user_list.remove(disconnected_username)
                user_list_container.update_user_list(user_list, page) # Update the user list display after client disconnection
                message_container.add_notification(f"{disconnected_username} left the chat.", page) # Notification message for client leaving
            if disconnected_username in voice_user_list:
                voice_user_list.remove(disconnected_username)
                voice_user_list_container.update_user_list(voice_user_list, page) # Update the voice user list display after voice client disconnection

        def on_new_voice_client(new_username):
            """Callback for when a new client joins the voice chat."""
            voice_user_list.append(new_username)
            voice_user_list_container.update_user_list(voice_user_list, page) # Update the voice user list display with the new voice client
            message_container.add_notification(f"{new_username} joined the voice chat.", page) # Notification message for new voice client joining
        
        def on_disconnected_voice_client(disconnected_username):
            """Callback for when a client leaves the voice chat."""
            if disconnected_username in voice_user_list:
                voice_user_list.remove(disconnected_username)
                voice_user_list_container.update_user_list(voice_user_list, page) # Update the voice user list display after voice client leaving
                message_container.add_notification(f"{disconnected_username} left the voice chat.", page) # Notification message for voice client leaving
        
        def send_message(e):
            """Sends the message in the text field to the server."""
            message = message_textfield.value.strip()
            if message:
                client_backend.send_chat_message(message) # Send the message using the backend client
                message_textfield.value = "" # Clear the text field
                message_container.add_message(config.get("name", "Guest"), message, page) # Add the sent message to the message container
            page.run_task(message_textfield.focus) # Refocus the text field after sending
            message_textfield.update() # Update the text field to reflect the cleared value    
        
        def disconnect(e):
            """Disconnects from the server and navigates back to the server list."""
            clear_backend_callbacks() # Clear the backend callbacks to prevent unwanted calls after disconnection
            client_backend.disconnect() # Disconnect from the server using the backend client
            navigate_to_server_list() # Navigate back to the server list screen
        
        def get_audio_devices():
            """Gets the list of available audio input and output devices and updates the dropdown options."""
            input_devices = []
            output_devices = []
            selected_input = config.get("input_device", None)
            selected_output = config.get("output_device", None)
            default_host_api = audio.get_default_host_api_info()["index"]
            for i in range(audio.get_device_count()):
                device_info = audio.get_device_info_by_index(i)
                if device_info["hostApi"] != default_host_api: # Filter devices to only include those from the default host API
                    continue
                if device_info["maxInputChannels"] > 0: # If the device has input channels, add it to the input devices list
                    input_devices.append((recode_name(device_info["name"]), i))
                    if selected_input == recode_name(device_info["name"]):
                        input_device_dropdown.value = str(i) # Set the dropdown value to the selected input device
                if device_info["maxOutputChannels"] > 0: # If the device has output channels, add it to the output devices list
                    output_devices.append((recode_name(device_info["name"]), i))
                    if selected_output == recode_name(device_info["name"]):
                        output_device_dropdown.value = str(i) # Set the dropdown value to the selected output device
            input_device_dropdown.options = [ft.dropdown.Option(key=str(i), text=recode_name(name)) for name, i in input_devices]
            output_device_dropdown.options = [ft.dropdown.Option(key=str(i), text=recode_name(name)) for name, i in output_devices]
            page.update()
            
        def start_voice_chat(e):
            """Starts the voice chat and updates the interface accordingly."""
            nonlocal voice_chat_row
            global instream
            global outstream

            # Audio index selection logic
            input_device_index = None
            output_device_index = None
            default_host_api = audio.get_default_host_api_info()["index"]
            for i in range(audio.get_device_count()):
                device_info = audio.get_device_info_by_index(i)
                if recode_name(device_info["name"]) == config.get("input_device") and device_info["maxInputChannels"] > 0:
                    if device_info["hostApi"] == default_host_api: # Check default host API
                        input_device_index = i
                    elif input_device_index is None: # Fallback in case there is no other match
                        input_device_index = i
                if recode_name(device_info["name"]) == config.get("output_device") and device_info["maxOutputChannels"] > 0:
                    if device_info["hostApi"] == default_host_api: # Check default host API
                        output_device_index = i
                    elif output_device_index is None: # Fallback in case there is no other match
                        output_device_index = i

            instream = audio.open(format=FORMAT, channels=client_backend.CHANNELS, rate=client_backend.RATE, input=True, frames_per_buffer=client_backend.CHUNK, input_device_index=input_device_index) # Open the audio input stream with the selected input device
            outstream = audio.open(format=FORMAT, channels=client_backend.CHANNELS, rate=client_backend.RATE, output=True, frames_per_buffer=client_backend.CHUNK, output_device_index=output_device_index)
            client_backend.gain = config.get("gain", 1.0) # Set the gain for the voice chat from the config
            client_backend.voice_toggle() # Toggle the voice chat using the backend client
            voice_chat_row.controls = voice_chat_row_active_controls # Switch to the active voice chat controls
            page.update() # Update the page to reflect the changes
            voice_user_list.append(config.get("name", "Guest")) # Add the user to the voice user list
            voice_user_list_container.update_user_list(voice_user_list, page) # Update the voice user list display
            get_audio_devices()
            warning_message.value = ""
            gain_slider.value = config.get("gain", 1.0)
            threading.Thread(target=get_microphone_data, daemon=True).start() # Start a thread to get microphone data and send it to the server

        def stop_voice_chat(e):
            """Stops the voice chat and updates the interface accordingly."""
            nonlocal voice_chat_row
            client_backend.voice_toggle() # Toggle the voice chat using the backend client
            voice_chat_row.controls = voice_chat_row_inactive_controls # Switch to the inactive voice chat controls
            page.update() # Update the page to reflect the changes
            voice_user_list.remove(config.get("name", "Guest")) # Remove the user from the voice user list
            voice_user_list_container.update_user_list(voice_user_list, page) # Update the voice user list display after leaving voice chat

        def mute_toggle(e):
            """Toggles the mute state for the user's microphone."""
            if client_backend.muted:
                client_backend.muted = False
                mute_button.icon = ft.Icons.MIC
                mute_button.icon_color = ft.Colors.ON_PRIMARY_CONTAINER
                mute_button.update()
            else:
                client_backend.muted = True
                mute_button.icon = ft.Icons.MIC_OFF
                mute_button.icon_color = ft.Colors.ERROR
                mute_button.update()
        
        def change_input_device(e):
            """Changes the audio input device based on the dropdown selection."""
            selected_device = e.data
            if config.get("input_device") == selected_device:
                return # No change in device, do nothing
            config["input_device"] = selected_device # Update the config with the new input device
            if client_backend.voice_enabled:
                warning_message.value = "Device changes will take effect after leaving and rejoining the voice chat."
            page.update()

        def change_output_device(e):
            """Changes the audio output device based on the dropdown selection."""
            selected_device = e.data
            if config.get("output_device") == selected_device:
                return # No change in device, do nothing
            config["output_device"] = selected_device # Update the config with the new output device
            if client_backend.voice_enabled:
                warning_message.value = "Device changes will take effect after leaving and rejoining the voice chat."
            page.update()

        def on_gain_change(e):
            """Changes the gain for the voice chat based on the slider value."""
            new_gain = gain_slider.value
            config["gain"] = new_gain # Update the config with the new gain value
            client_backend.gain = new_gain # Set the new gain value in the backend client
        
        def on_noise_suppressor_toggle(e):
            """Toggles the noise suppressor for the voice chat based on the checkbox value."""
            enabled = noise_suppression_checkbox.value
            config["noise_suppressor"] = enabled # Update the config with the new noise suppressor state
            client_backend.noise_suppressor = enabled # Set the new noise suppressor state in the backend client

        def show_voice_chat_settings(e):
            """Shows the voice chat settings dialog."""
            page.dialog.open = True
            page.update()

        page.add(ft.Row([
            ft.Column([
                ft.Row([ # Top row with server name and disconnect button
                    ft.Button(
                        "Disconnect",
                        on_click=disconnect,
                        icon=ft.Icons.LINK_OFF,
                        bgcolor=ft.Colors.INVERSE_PRIMARY,
                        color=ft.Colors.ON_PRIMARY_CONTAINER,
                    ),
                    ft.Text(f"Chat: {server_name}", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY, expand=True, text_align=ft.TextAlign.CENTER)
                ], height=50),
                message_container, # The container that displays the messages
                ft.Row([ # Message input row
                    message_textfield,
                    ft.IconButton(
                        ft.Icons.SEND,
                        on_click=lambda e: send_message(e),
                        bgcolor=ft.Colors.INVERSE_PRIMARY,
                        icon_color=ft.Colors.ON_SECONDARY_CONTAINER
                    ),
                    ft.IconButton(
                        ft.Icons.ATTACH_FILE,
                        on_click=lambda e: message_container.add_file_upload(page),
                        bgcolor=ft.Colors.INVERSE_PRIMARY,
                        icon_color=ft.Colors.ON_SECONDARY_CONTAINER
                    )
                ], height=50)
            ], expand=True),
            ft.Column([ # Side column
                ft.Text("Connected Users", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY, text_align=ft.TextAlign.CENTER),
                user_list_container, # The container that displays the list of connected users
                ft.Text("Voice Chat Users", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY, text_align=ft.TextAlign.CENTER),
                voice_user_list_container, # The container that displays the list of connected users in voice chat
                voice_chat_row # The row that contains the voice chat controls (connect/disconnect, mute, settings)
            ], width=250)
        ], expand = True)) # Add the chat screen controls to the page
        client_backend.on_chat_message = lambda sender, content: message_container.add_message(sender, content, page) # Set the callback for receiving chat messages
        client_backend.on_disconnect = lambda reason, exception: navigate_to_server_list(reason=reason, exception=exception) # Set the callback for disconnection
        client_backend.on_new_client = on_new_client # Set the callback for new client connections
        client_backend.on_disconnected_client = on_disconnected_client # Set the callback for client disconnections
        client_backend.on_connect = on_connect # Set the callback for successful connection
        client_backend.on_new_voice_client = on_new_voice_client # Set the callback for new voice client connections
        client_backend.on_disconnected_voice_client = on_disconnected_voice_client # Set the callback for voice client disconnections
        client_backend.on_audio_frame = play_audio_frame # Set the callback for receiving audio frames
        client_backend.on_file_notice = lambda sender, filename: message_container.add_file_notice(sender, filename, page) # Set the callback for receiving file notices
        page.update()
        client_backend.connect(server_ip, server_port, config.get("name", "Guest")) # Connect to the server using the backend client
        

    def delete_server(server_number):
        """
        Deletes a server from the server list and updates the screen.
        Args:
            server_number (int): The index of the server to delete in the server list.
        """
        global server_list
        # Remove the server from the list
        server_list.pop(server_number)
        navigate_to_server_list() # Refresh the server list screen
    
    def add_server(server_name, server_ip, server_port):
        """
        Adds a new server to the server list and updates the screen.
        Args:
            server_name (str): The name of the server to add.
            server_ip (str): The IP address of the server to add.
            server_port (int): The port number of the server to add.
        """
        global server_list
        # Add the new server to the list
        server_list.append((server_ip, server_port, server_name))
    
    def server_list_screen(server_list):
        """
        Creates the server list screen with the given server list.
        Args:
            server_list (list): A list of servers to display on the screen.
        Returns:
            ft.Column: A Flet column containing the server cards.
        """
        def on_name_changed(new_name):
            """Callback to update the name in the config when it changes."""
            config["name"] = new_name
        
        return ft.Column(expand=True, controls=[
            ft.Row([
                ft.Column(expand=True, controls=[
                    ft.Text("Whatsapp 3", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY),
                    EditableNameField(initial_name=config.get("name", "Guest"), on_name_changed=on_name_changed),
                    ft.Text("Select a server to connect to:", size=16, color=ft.Colors.ON_PRIMARY),
                ]),
                ft.Image(src="assets/logo.png", width=80, height=80)
            ], height=100, margin=10),
            ft.ListView(
                controls=[ServerCard(server[2], server[0], server[1], i, navigate_to_chat_screen, delete_server) for i, server in enumerate(server_list)],
                spacing=10,
                padding=10,
                scroll= ft.ScrollMode.AUTO,
                expand=True
            ),
            ft.Button(
                "Add Server",
                on_click=show_add_server_dialog,
                icon=ft.Icons.ADD,
                bgcolor=ft.Colors.INVERSE_PRIMARY,
                color=ft.Colors.ON_PRIMARY_CONTAINER,
                width=150,
                height=40,
                margin=10
            )
        ])

    def add_server_dialog():
        """
        Returns the dialog for adding a new server.
        Returns:
            ft.AlertDialog: A Flet AlertDialog for adding a new server.
        """
        server_name_input = ft.TextField(label="Server Name", expand=True, on_submit=lambda e: on_add_click(e))
        server_ip_input = ft.TextField(label="Server IP", expand=True, on_submit=lambda e: on_add_click(e))
        server_port_input = ft.TextField(label="Server Port", expand=True, keyboard_type=ft.KeyboardType.NUMBER, on_submit=lambda e: on_add_click(e))
        error_message = ft.Text("", color=ft.Colors.ERROR) # Placeholder for error messages
        def on_add_click(e):
            """Callback for when the Add button is clicked in the dialog."""
            server_name = server_name_input.value.strip()
            server_ip = server_ip_input.value.strip()
            server_port = server_port_input.value.strip()
            if server_name and server_ip and server_port.isdigit():
                add_server(server_name, server_ip, int(server_port))
                page.dialog.open = False
                page.update()
                navigate_to_server_list() # Refresh the server list screen
            else: # Show an error message if the input is invalid
                error_message.value = "Please fill in all fields correctly."
                page.update()
        add_button = ft.Button("Add", on_click=on_add_click)
        cancel_button = ft.Button("Cancel", on_click=lambda e: setattr(page.dialog, "open", False))
        return ft.AlertDialog(
            title = ft.Text("Add New Server"),
            content = ft.Column([
                server_name_input,
                server_ip_input,
                server_port_input,
                error_message
            ], height=200, spacing=10),
            actions = [add_button, cancel_button],
        )
    # Start the app on the server list screen
    navigate_to_server_list()

# Pyaudio setup for voice chat
FORMAT = pyaudio.paInt16
audio = pyaudio.PyAudio()
# Load server list and config from json files
server_list_path = os.path.join(get_base_path(), "server_list.json")
config_path = os.path.join(get_base_path(), "interface_config.json")
try: server_list = json.loads(open(server_list_path).read())
except: server_list = []
try: config = json.loads(open(config_path).read())
except: config = {
    "color_seed": "#004a49",
    "name": "Guest",
    "gain": 1.0,
    "input_device": None,
    "output_device": None,
    "noise_suppressor": False
}
if config.get("input_device") == None or config.get("output_device") == None:
    # If there are no saved audio devices in the config, set the default devices
    config["input_device"] = recode_name(audio.get_default_input_device_info().get("name"))
    config["output_device"] = recode_name(audio.get_default_output_device_info().get("name"))
client_backend = whatsapp3_client.Whatsapp3Client()
ft.run(main) # Run the Flet app with the main function as the entry point
