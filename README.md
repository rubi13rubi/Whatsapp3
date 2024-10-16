# WHATSAPP3

Whatsapp3 is a server-client based chat programmed using tcp and udp sockets. It features text chat, file sending/storing and voice chat.

## General description

The project consists on a console-based server and an interface-based client. Once the server is set up on a specific ip/port, multiple clients can connect and start chatting, sending files and using voice chat.

## Server installing

The server is designed to run on a linux or windows machine. There is not a binary for the server as it can be interpreted with python, but **there is a server folder on each release version src directory** with the server version that will work best with that client release. Using different server and client versions can cause issues.
To avoid having issues with the opus library (which requires additional files to work), **copy the entire folder and not only the python file**. The folder contains all the opus files for Windows (.dll) and must be kept always with the server file itself.
The folder also contains the requirements file, so you can install python dependencies using:
```
pip install --update pip
pip install -r requirements.txt
```
If you find an error or your distribution does not recommend using pip, you can use a **python virtual environment**. To create a virtual environment open use `python3 -m venv wpp3venv`. Then you should be able to install the requirements with the pip from the virtual environment using
```
wpp3venv/bin/pip install --update pip
wpp3venv/bin/pip install -r requirements.txt
```
To use the virtual environment when executing your files, you need to execute the python binary of the venv instead of the one in your system. Simply replace `python3` with `wpp3venv/bin/python3`


## Server setup and usage

Once the server folder is installed, you can start it opening a terminal on the folder and typing:
```
python3 whatsapp3_server.py
```
If you get the error "Could not find Opus library. Make sure it is installed" check the section below for Opus errors.
If it is your first time using the client, it will generate a **config.json** file with the default settings and stop the program. Before running the program again, open the config file to configure all the parameters:
```
nano config.json
```
1. Change **ip** to the private ip of your machine. If you do not know it you can use ifconfig or ipconfig (depending on your os).

2. Change **port, fileport, and voiceport** to 3 separate free ports on your machine. If you want to open the server to the internet through port forwarding make sure you enter the right ports here. Make sure you type all ports with "" format. If you type just the numbers the server will not work. 

3. Change **storagelimit** to the total disk space you want to use for storing sent files, in bytes. When this limit is reached, all previous sent files will be deleted.

Save the file and run the server again. It should start and print everything that happens through the server. You can stop it anytime pressing enter. The server can take some time to close if it is in the middle of an action, like sending or receiving a file.
Additionally, the server will save everything in a log file with timestamps, so you can see the chat history even after closing the server.

## Client installing

The client has been tested on Windows, and **.exe files are included on releases**. Unlike the server, client files have been compiled with all dependencies packed inside, so everything you need to do is download the .exe file. Make sure you use the same release of client and server. Some versions may be compatible, but you may find unexpected errors.

### Alternative: running from source

Alternatively, you can also download the source and run it with python. This can be used to run the client on Linux, although you will have some issues with the interface and the audio quality will be worse. If you want to do this, you will have to download the full client folder from src, as it includes all the necessary files that are normally packed in the .exe. Also, you will need to install the requirements opening a terminal on the client folder and running:
```
pip install --update pip
pip install -r requirements.txt
```
If installing dependencies fails, you can also use a python virtual environment. The process of creating a virtual environment is already described in the server installing section. Follow the same steps and you will be able to run the client file file replacing `python3` with `wpp3venv/bin/python3`

## Client setup and usage

To run the client, just double click the .exe file. If you have decided to download the source, open a terminal on the client folder and type:
```
python3 whatsapp3.py
```
An interface will appear, and you will be asked to select a server. If this is your first time using the client, you will need to add a new server to use it.
1. Click "add server".
2. Enter the details. Note that if you are using a server through internet and not a local network, the ip you need to enter here is the public ip, and you should have all 3 ports properly forwarded and open to the internet on the server router. The port that you need to enter is the chat port (called just "port" on the server settings file). Other ports are obtained automatically when you connect to the server. The name is just for listing and remembering purposes and you can put whatever you want there.
3. Click "add". You should see your added server on the interface. The client will create a file named server_list.json. This file contains the information of added servers. It needs to be in the same folder as the executable to work, otherwise the information will be lost and a new json will be created.
4. To connect to your server, click it to select it, enter a username on the text field and click "connect" (or press enter).

If everything worked, you should see another interface with box where all messages are displayed. If the server is online and the ip is correct, you should see a welcome message and the number of connected users. If you instead see "error connecting to server", check that the server is running, the ip is correct, and no firewall is blocking the traffic.

- To **send a message**, type it in the chat box and click "send" (or press enter)
- To **send a file**, click "send file", select a file and click "send". Do not disconnect from the server until you see a confirmation message saying that your file is sent. Otherwise, your transfer will be cancelled.
- To **download a file** sent by another user, double click the message of the file. You will be prompted with a window asking where would you like to save the file and the name of it. Once you select it you will start downloading the file. Do not try to open the file or disconnect from the server until you see a confirmation message saying your file has been downloaded.
- To use **voice chat**, type "/voice" on the chat and send. Other clients in the server will be notified when you join the voice chat. If your voice volume is too high or too low, type "/gain (gain value)" with the value you want. Default is 1 so typing "/gain 2" will duplicate the volume of your input. You cannot configure gain value for other users, so if you hear them very low or very high, ask them to change their own value. To mute or unmute your microphone, type "/mute". To leave the voice chat, type "/voice" again.

## Opus error

When executing either the client or the server from source, you may get the error "Could not find Opus library. Make sure it is installed". This is because Opus library is a system library and the python package only connects the system library with Python so you can use it in the code. For the library to work you need to have the library installed on your system.

### Windows

If you get the error on Windows, check if you have the .dll files on the same folder as the python file. These files are the system library and Windows needs to find them for the Python library to work.
You should never get the error on the executable as it is packed with the library inside. However, if you have compiled your own executable, you may not have packed the libraries. Check the next section to compile your .exe correctly.

### Linux

Linux does not require the .dll files, and some distributions already have the library installed on the system. However, if you get the error, you need to manually install it using a package manager, for example:
```
sudo yum install opus
```

## About virus/malware detection. Compile the source yourself

Some antivirus, including windows defender will detect the .exe file as malware and warn about it or delete the file completely. This is due to the file not being signed, the console being hidden and the code containing network interactions that are usually found in malware. The file is completely safe and you can just allow it on your antivirus, click ok on the warnings, and allow it through the firewall.
However, it is **reasonable not to trust** random executables downloaded from the internet, so if you want to make sure what you are running is not malicious, you can check the source code and **compile it yourself**. Note that you will be required to have python installed with the required libraries for the program.
The steps shown below apply for Windows, but they should work (although it has not been tested) to generate a Linux executable. Linux does not require the .dll files to be included.

1. **Find the source code** of the the release you want to build. It should be in `src/client`. To compile it you need the full folder as it includes files that will be packed with the executable.
2. **Check the code** with a code editor to find any potential malware. Also, you can download the three .dll files from the original repository, listed in credits section (you will have to rename the "libopus-o.dll" to "opus.dll").
3. **Turn off your antivirus** or add the client folder to exceptions. This will avoid the process being stopped before it even being fully compiled.
4. **Open a terminal** on the client folder you downloaded.
5. Install pyinstalles package and **run the following command**
```
pyinstaller --onefile --noconsole whatsapp3.py
```
The command will automatically include the opus .dll files on the executable so it can work as a single file. If the opus binaries are not in the same folder when compiling, you will have an error when executing the .exe. When the proccess ends,a bunch of folders and files will have been created. You can find the .exe on the dist folder.

## Project future / contribution

As this was a "for fun" project, I am not very invested in maintaining and adding features. However, I plan to add some features, including:

- Bug fixes, cleaning code and stability improvement
- Retreive chat history on clients
- Encryption (probably client-server and server-client)
- Improved user interface
- Mobile application support for Android
- Chat history recovery
- Better management of files
- Video chat / sharing screen

This list does not imply all features will be added, but I will probably be slowly adding some of it.
I do not plan to add contributors, but issues reporting and suggestions will be very useful.

## Credits

The opus library files included with the server and the client are obtained from [this repository](https://github.com/ChillerDragon/ddnet-9.0.2-dummys/tree/master/other/opus)

## Contact

If you have any idea or suggestion, please contact [ruben.lr3@gmail.com](mailto:ruben.lr3@gmail.com).
