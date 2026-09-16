# Initial Architecture
TBC - architecture diagram

## Temperature Sensor Device Specifications
* Device: Arduino Uno (ATmega328P)
* Key Specs: 16 MHz CPU, 2 KB SRAM, 32 KB Flash.
* It will give us plain sensor telemetry (e.g., Temperature, Device ID, Timestamp).
* It is a lightweight Python script simulating the payload and packet size.
* No hardware or complex emulators required.
* The device has a memory limit. And ML-KEM-512 requires the use of keys (e.g. a 1,632 bytes secret key), while the device's working memory might need 1000 to 1500bytes. So this adds up to approximately 3 KB.
* As a result, ML-KEM is unable to physically inside 2 KB of RAM without a stack overflow or crash.
* We will use simple lightweight key based encryptions (AES-128 or ChaCha20). The sensor cannot handle anything more complex.
* We will keep the payload output simple as well:
```json
{
  "device_id": "sensor-node-01",
  "timestamp": 1726478400,
  "temperature": 21.8,
  "humidity": 55.4,
  "status": "OK"
}
```
* We will look into how to simulate the payload and get simple key based encrypted data, and that key based encrypted data will be sent to 2nd node which will then decrypt and then apply ML-KEM for PQC before sending it to cloud. => Maybe this point belongs in the design decisions document?
* One major advantage for this device is that this microcontroller is being used in real world, a lot of sensor devices are using ATmega328P, cold storages, storage room temperature and humidity sensor, soil humidity sensors, and maybe even our home room temperature sensors. So this is device is pretty close to real world usage and actually is being used a lot.



# How to run the system
TBC

# What baseline tests and measurements are there
TBC

# How to run baseline tests and measurements
TBC
