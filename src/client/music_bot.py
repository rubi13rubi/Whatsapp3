import yt_dlp
import json
import whatsapp3_client
import subprocess
import threading
import queue
import time
import os

def get_direct_url(video_url):
    """
    Extracts the direct URL to the audio stream of a YouTube video.
    Also returns the title of the video for display purposes.
    """

    if video_url in url_cache:
        print("URL found in cache. Verifying that it is still valid.")
        direct_url, title = url_cache[video_url]
        if is_valid_url(direct_url):
            print("Cached URL is still valid. Using cached URL.")
            return (direct_url, title)
        else:
            print("Cached URL is no longer valid. Removing from cache and extracting new URL.")
            del url_cache[video_url]

    client_backend.send_chat_message("Extracting direct URL for the video. This may take a moment...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'remote_components': ['ejs:github'] 
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        url_cache[video_url] = (info['url'], info['title']) # Cache the direct URL and title for future use
        return (info['url'], info['title'])

def is_valid_url(url):
    """
    Checks if a given URL is valid and accessible by sending a HEAD request.
    Returns True if the URL is valid, False otherwise.
    """
    try:
        response = subprocess.run(['curl', '-I', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        return "200 OK" in response.stdout
    except subprocess.TimeoutExpired:
        print("Timed out while checking URL.")
        return False

def search_youtube(query):
    """
    Searches YouTube for the given query and returns the URL of the top result.
    """
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'default_search': 'ytsearch1', # Search for the query and return the top result
        'remote_components': ['ejs:github'] 
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info and len(info['entries']) > 0:
            video_info = info['entries'][0] # Get the top search result
            url_cache[video_info['webpage_url']] = (video_info['url'], video_info['title']) # Cache the direct URL and title for future use
            return video_info['webpage_url'] # Return the URL of the top search result
        else:
            raise Exception("No search results found.")


def play_music(command_text):
    """
    Sends the music stream to the client backend to play the music on voice chat.
    """
    global playing
    global streaming

    if (not "youtube.com" in command_text and not "youtu.be" in command_text) or not is_valid_url(command_text.strip()):
        # Search querry management
        client_backend.send_chat_message("Searching for the video on YouTube...")
        try:
            video_url = search_youtube(command_text.strip())
            print(f"Search complete. Found video URL: {video_url}")
        except Exception as e:
            client_backend.send_chat_message(f"No results found for '{command_text.strip()}'. Please try a different search query.")
            return
    else:
        video_url = command_text.strip()

    print("Extracting direct URL for the video...")
    try:
        direct_url, title = get_direct_url(video_url)
    except Exception as e:
        client_backend.send_chat_message(f"Url is not valid.")
        return
    print("Direct URL extracted. Starting subprocess to convert audio stream...")
    client_backend.send_chat_message(f"Playing: {title}")
    playing = True

    # Use ffmpeg to convert the audio stream to a format suitable for streaming
    ffmpeg_command = [
        'ffmpeg',
        '-reconnect', '1',
        '-reconnect_streamed', '1',
        '-reconnect_delay_max', '5',
        '-i', direct_url, # Input from the direct URL
        '-f', 's16le', # Output format: raw PCM audio
        '-ar', str(client_backend.RATE), # Audio sample rate
        '-ac', str(client_backend.CHANNELS), # Number of audio channels
        '-loglevel', 'quiet', # Suppress ffmpeg output
        'pipe:1'        # Output to stdout
    ]
    # Start the ffmpeg process
    process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) # Ignore error output
    streaming = True
    bytes_per_frame = client_backend.CHUNK * client_backend.CHANNELS * 2 # 2 bytes per sample for s16le
    frame_send_thread = threading.Thread(target=send_audio_frames, daemon=True) # Thread to send audio frames to client backend
    frame_send_thread.start() # Start the thread to send audio frames
    try:
        audio_frame = process.stdout.read(bytes_per_frame)
        while (audio_frame or len(audio_frame) == bytes_per_frame) and playing: # Continue reading frames while there is audio and the playing flag is True
            if audio_frame:
                frame_queue.put(audio_frame) # Put the audio frame in the queue for sending to the client backend
            audio_frame = process.stdout.read(bytes_per_frame) # Read the next audio frame   
    finally:
        streaming = False # Set streaming to False 
        process.kill() # Ensure the ffmpeg process is terminated when done
        process.wait() # Wait for the process to terminate
        print("Audio streaming finished. Subprocess terminated.")

def send_audio_frames():
    """
    Continuously sends audio frames from the frame queue to the client backend.
    This function should be run in a separate thread to allow simultaneous reading of ffmpeg output and sending to the client backend.
    """
    global playing
    global streaming
    global frame_queue

    client_backend.voice_toggle() # Join the voice chat
    next_loop_timing = time.time() # Initialize timing for sending frames
    while playing:
        try:
            audio_frame = frame_queue.get(timeout=1) # Wait for the next audio frame, with timeout to allow checking the playing flag
            if audio_frame:
                client_backend.audioqueue.put(audio_frame) # Put the audio frame in the client backend's audio queue for sending to the server
            # Timing management to ensure frames are sent at the correct intervals based on the SEND_INTERVAL
            next_loop_timing += SEND_INTERVAL
            sleep_time = next_loop_timing - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                print("Warning: sending took longer than expected. Skipping sleep to catch up.")
                next_loop_timing = time.time()
            pause_lock.acquire() # Acquire the pause lock to check if we need to pause sending frames
            pause_lock.release() # Release the pause lock immediately since we are not actually pausing in
        # Exception management (timeout)
        except queue.Empty:
            if not streaming: # If the queue is empty and streaming has finished, break the loop
                break
            else: continue # If the queue is empty but streaming is still ongoing, continue waiting for frames
    client_backend.send_chat_message("Music playback stopped.")
    print("Stopped sending audio frames to client backend.")
    client_backend.voice_toggle() # Leave the voice chat when done
    playing = False # Ensure playing is set to False when done
    # Clear the frame queue for the next time music is played
    frame_queue = queue.Queue(maxsize=50) # Reset the frame queue to clear any remaining frames


def on_message(sender, message):
    """
    Callback function that is called whenever a new message is received.
    It checks if the message is a command to play or stop music and acts accordingly.
    """
    global playing
    if message.startswith("!play "):
        if playing:
            print("Already playing music. Ignoring new play command.")
            client_backend.send_chat_message("Already playing music. Please stop the current music with '!stop' before playing a new one.")
        else:
            command_text = message[6:].strip() # Get the text after the "!play " command
            print(f"Received play command for: {command_text}")
            threading.Thread(target=play_music, args=(command_text,), daemon=True).start() # Start playing music in a separate thread
    elif message == "!stop":
        print("Received stop command.")
        client_backend.send_chat_message("Stopping music.")
        playing = False # Set playing to False to signal the music thread to stop
        if pause_lock.locked():
            pause_lock.release() # Release the pause lock if it is locked to ensure the music thread can exit if it is currently paused
    elif message == "!pause":
        print("Received pause command.")
        if not playing:
            client_backend.send_chat_message("No music is currently playing to pause.")
            return
        if pause_lock.locked():
            client_backend.send_chat_message("Resuming music.")
            pause_lock.release() # Release the pause lock to resume sending frames
        else:
            client_backend.send_chat_message("Pausing music.")
            pause_lock.acquire() # Acquire the pause lock to pause sending frames
    elif message.startswith("!volume "):
        try:
            volume = float(message.split(" ")[1])
            if 0 <= volume <= 2.0: # Allow volume values between 0 (mute) and 2 (double volume)
                client_backend.change_gain(volume) # Change the gain in the client backend to adjust the volume
                client_backend.send_chat_message(f"Volume set to {volume}.") # Send confirmation message to chat
            else:
                client_backend.send_chat_message("Invalid volume. Please specify a value between 0 and 2.")
        except (ValueError, IndexError):
            client_backend.send_chat_message("Invalid volume command. Please specify a value between 0 and 2.")
    elif message == "!help":
        client_backend.send_chat_message("# Available commands: \n" \
            "- **!play** <YouTube URL or search query> - Play music from YouTube. You can provide a direct URL or a search query.\n" \
            "- **!stop** - Stop the current music playback.\n" \
            "- **!pause** - Pause or resume the current music playback.\n" \
            "- **!volume** <value> - Set the volume of the music playback (0.0 to 2.0).")

def on_disconnect(reason, exception):
    """
    Callback function that is called when the client disconnects from the server.
    It can be used to perform any necessary cleanup.
    """
    print("Unexpectedly disconnected from server.")
    if reason:
        print("Reason: ", reason)
        if exception: print("Exception: ", exception)
    print("Exiting music bot. Goodbye!")
    os._exit(1)

print("Loading url cache...")
try:
    with open("url_cache.json", "r") as f:
        url_cache = json.load(f)
except:
    url_cache = {}
print("Initializing client backend...")
client_backend = whatsapp3_client.Whatsapp3Client()
playing = False
streaming = False
frame_queue = queue.Queue(maxsize=50) # Queue to hold audio frames for streaming to the client backend
pause_lock = threading.Lock() # Lock to manage pausing and resuming of music playback
print("Setting up callbacks...")
client_backend.on_chat_message = on_message
client_backend.on_disconnect = on_disconnect
IP = input("Enter the IP address of the server: ")
PORT = int(input("Enter the port number of the server: "))
USERNAME = "MusicBot"
print("Connecting to chat...")
client_backend.connect(IP, PORT, USERNAME)
SEND_INTERVAL = client_backend.CHUNK / client_backend.RATE # Time interval between sending audio frames, based on the chunk size and sample rate
print("Music bot is ready and running. Waiting for commands...")
input("Press Enter to exit...\n") # Keep the program running until user decides to exit
print("Saving url cache...")
with open("url_cache.json", "w") as f:
    json.dump(url_cache, f)
print("Disconnecting from chat...")
# Clear callbacks to avoid any potential issues with callbacks being called after disconnection
client_backend.on_chat_message = None
client_backend.on_disconnect = None
client_backend.disconnect()
print("Exiting music bot. Goodbye!")