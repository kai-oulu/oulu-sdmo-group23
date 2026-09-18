### 1. What We Built & How It Works

We built the first link of the project: the **Legacy Device talking to the Edge Gateway**.

* **`legacy_device.py` (The Sensor)**
* Creates a simple JSON payload (temperature, humidity, timestamp, status).
* Takes a 16-byte pre-shared secret key (`legacy_secret_16`).
* Generates a 12-byte random number called a **nonce** (number used once) so encryption is never identical twice.
* Encrypts the JSON using **AES-GCM** (a secure symmetric cipher that scrambles the data and adds an authentication tag to stop tampering).


* Glues the nonce to the front of the encrypted text and sends it over a standard TCP socket to port 5000.


* Closes the connection immediately.


* **`edge_gateway.py` (The Bridge / Middleman)**
* Runs in the background listening on port 5000.


* Accepts the connection and downloads all the incoming bytes until the device disconnects.


* Pulls off the first 12 bytes to get the nonce, and feeds the rest into AES-GCM using the same secret key.
* Prints out the original sensor JSON to confirm it decrypted properly.



---

### 2. Why We Did It This Way (Design Choices)

* **Why an ATmega328P simulation?**
* In the real world, tiny sensors (like an Arduino Uno) only have 2 KB of RAM.
* The new Post-Quantum Cryptography algorithm (ML-KEM-512) uses key sizes and math that physically crash a 2 KB chip.
* Therefore, the device *must* use old, lightweight symmetric encryption (AES) and offload the heavy post-quantum security to the Edge Gateway.




* **Why raw TCP instead of HTTP or WebSockets?**
* Tiny microcontrollers don't run web browsers or heavy HTTP web servers.
* A raw TCP socket is the closest software simulation to a raw serial cable (UART/RS-485 bus) connecting a sensor to a Raspberry Pi gateway.




* **Why does the device close the connection?**
* TCP sends a continuous stream of bytes. To know where the message ends without writing complicated byte-counting code, the device sends its reading and closes the connection. When the gateway sees the socket close, it knows it received the full packet.



---

### 3. Log for the AI Requirement (Course Submission)

The course specifically requires recording prompts and human corrections. Give your teammate this exact log:

* **Prompt Given to AI:**
> *"Write two Python scripts using the `cryptography` library. One is `legacy_device.py` which encrypts sensor JSON telemetry using AES-GCM and a pre-shared key, connects to `127.0.0.1:5000` via TCP, sends the data, and disconnects. The second is `edge_gateway.py` which listens on port 5000, receives the encrypted bytes, decrypts the payload with the same key, and prints the sensor data."*


* **Issues Found & Human Decisions (Why we changed things):**
1. **WebSockets vs TCP:** We evaluated WebSockets vs bare TCP. Decided on bare TCP sockets because WebSockets add massive protocol bloat that makes no sense for an ATmega328P profile.
2. **Message Framing:** Instead of writing extra code to track packet lengths, we decided the device should send its payload and close the socket. The gateway reads until EOF (connection close), keeping the code minimal and bug-free.
3. **Virtual Environment Fix:** Running the code initially threw `Import "cryptography" could not be resolved`. We resolved this by syncing dependencies with `uv sync` and configuring the IDE interpreter to point directly to `./.venv`.