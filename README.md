A Universal VRChat Heart Rate OSC Tool
A simple GUI-based Bluetooth heart rate bridge for VRChat. Reads real-time heart rate data from Xiaomi smart bands and sends values to VRChat avatar parameters via OSC.
✨ Features
- Real-time heart rate reading from Xiaomi Smart Band
- Customizable VRChat OSC avatar parameters (bool + float)
- Automatic scanning, reconnecting and timeout detection
- Visual GUI: BPM display, connection status, running log
- Auto reset OSC state when disconnected
📦 Release Download
You can get the compiled Windows EXE from Releases on the right side of this repository.
💻 How to Use
1. Enable VRChat OSC
Open VRChat > Settings > OSC > Turn on OSC.
2. Set Avatar Parameters
Default parameters (you can change them in software):
- hr_connected (Bool): Device connected status
- hr_percent (Float): Normalized heart rate percentage (0.0 ~ 1.0)
3. Run the Tool
1. Wear and unlock your Xiaomi band
2. Turn on Bluetooth on your PC
3. Click Start Bluetooth Scan
4. The tool will auto connect and push heart rate data to your avatar
🛠 For Developers (Run Source)
Python 3.10+ recommended
pip install bleak pyside6 python-osc
python hr_gui.py
📷 Parameter Description
- BPM: Real-time heart rate value
- Heart Rate Percent: currentBPM / 200 (clamped 0~1)
📄 License
This project is open-sourced under the MIT License. Feel free to use and modify.
