# IoT Smart Home Dashboard (PyQt6 + Arduino)

A complete **IoT gas-monitoring and home automation system** built using **Python (PyQt6)** and **Arduino**.  
The project combines real-time sensor monitoring, automatic safety logic, and an interactive GUI that visualizes a 3D-isometric smart house.
---

##  Overview

This project demonstrates how an **IoT-based gas-safety system** can automatically detect hazardous gas levels, trigger ventilation, and alert users.  
The PyQt6 desktop app communicates with an Arduino controller over serial USB, showing live sensor data and allowing manual control of devices like **LEDs, fans, servo doors, and buzzers**.

---

## Features

✅ Real-time monitoring of:
- MQ-2 gas sensor  
- DHT11 temperature + humidity  
- HC-SR04 distance sensor  

✅ Automatic control logic:
- Opens servo door + starts fan when gas exceeds threshold  
- Alarm buzzer triggered on high gas detection  

✅ Interactive dashboard:
- Toggle devices (LED, fan, door) manually  
- Visual gas-level graph  
- Isometric “Kawaii Home” 3D layout  

✅ Secure login:
- Username + password loaded from `.env`  
- Password verified via SHA-256 hash  

✅ Theming:
- Pastel orange and blue UI  
- Custom background image support  


