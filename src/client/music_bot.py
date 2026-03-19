import yt_dlp
import json
import whatsapp3_client
import subprocess
import threading
import queue
import time

def get_direct_url(video_url):
    """
    Extracts the direct URL to the audio stream of a YouTube video.
    Also returns the title of the video for display purposes.
    """

    if video_url in url_cache:
        print("URL found in cache. Verifying that it is still valid.")
        # Ping the URL to check if it is still valid
        try:
            url = url_cache[video_url][0] # Get the cached direct URL
            response = subprocess.run(['curl', '-I', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if "200 OK" in response.stdout:
                print("Cached URL is still valid. Using cached URL.")
                return url_cache[video_url]
            else:
                print("Cached URL is no longer valid. Extracting new URL.")
        except subprocess.TimeoutExpired:
            print("Timed out while checking cached URL. Extracting new URL.")


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

def play_music(video_url):
    """
    Sends the music stream to the client backend to play the music on voice chat.
    """
    global playing
    global streaming

    print("Extracting direct URL for the video...")
    direct_url, title = get_direct_url(video_url)
    print("Direct URL extracted. Starting subprocess to convert audio stream...")
    client_backend.send_chat_message(f"Playing: {title}")

    # Use ffmpeg to convert the audio stream to a format suitable for streaming
    ffmpeg_command = [
        'ffmpeg',
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
            video_url = message.split(" ")[1] # Extract the URL from the command
            print(f"Received play command for URL: {video_url}")
            playing = True
            threading.Thread(target=play_music, args=(video_url,), daemon=True).start() # Start playing music in a separate thread
    elif message == "!stop":
        print("Received stop command.")
        client_backend.send_chat_message("Stopping music.")
        playing = False # Set playing to False to signal the music thread to stop
    elif message.startswith("!volume "):
        try:
            volume = float(message.split(" ")[1])
            if 0 <= volume <= 2.0: # Allow volume values between 0 (mute) and 2 (double volume)
                client_backend.gain = volume # Set the gain in the client backend to adjust the volume
                client_backend.send_chat_message(f"Volume set to {volume}.") # Send confirmation message to chat
            else:
                client_backend.send_chat_message("Invalid volume. Please specify a value between 0 and 2.")
        except (ValueError, IndexError):
            client_backend.send_chat_message("Invalid volume command. Please specify a value between 0 and 2.")

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
print("Setting up callbacks...")
client_backend.on_chat_message = on_message
IP = input("Enter the IP address of the server: ")
PORT = int(input("Enter the port number of the server: "))
USERNAME = "MusicBot"
SEND_INTERVAL = client_backend.CHUNK / client_backend.RATE # Time interval between sending audio frames, based on the chunk size and sample rate
print("Connecting to chat...")
client_backend.connect(IP, PORT, USERNAME)
print("Music bot is ready and running. Waiting for commands...")
input("Press Enter to exit...\n") # Keep the program running until user decides to exit
print("Saving url cache...")
with open("url_cache.json", "w") as f:
    json.dump(url_cache, f)
print("Disconnecting from chat...")
client_backend.disconnect()
print("Exiting music bot. Goodbye!")