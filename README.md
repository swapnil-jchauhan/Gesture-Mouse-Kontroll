<div align="center">

# ⚡ Project Kontroll

### *Control your Windows 11 PC with hand gestures like Jarvis — using literally any webcam.*

[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011-0078D4?style=for-the-badge&logo=windows11&logoColor=white)](https://microsoft.com)
[![Status](https://img.shields.io/badge/Status-Working%20Smoothly-00f0ff?style=for-the-badge)](https://github.com)

<br/>

> **Move your cursor with your finger, tap index on middle to click, and throw up the "super" gesture (👌) to trigger an insane glowing Jarvis holographic HUD!**

</div>

---

## 📌 Quick Links

- [1. What is this?](#1-what-is-this)
- [2. How to use](#2-how-to-use)
  - [The Gestures](#-the-gestures)
  - [The Jarvis HUD](#-the-jarvis-hud)
  - [Auto-Launch on Boot](#-auto-launch-on-boot)
  - [Calibration Mode](#-calibration-mode)
- [3. Requirements & Setup](#3-requirements--setup)
- [4. Cool Tips](#4-cool-tips)

---

## 1. What is this?

Imagine being able to control ur PC without touching a anything like Tony Stark interacting with holograms in mid-air. 

Every webcam mouse project I found online had the same annoying issues:
1. **The cursor shakes like crazy** because cheap webcams have noisy sensors.
2. **You miss your clicks** because when you do a mid-air pinch, your hand shakes and the cursor slides away from the button.
3. **They lag** or need expensive depth cameras.

So I made this

It's a lightweight software for Windows 11 that:
- Uses **any regular webcam** (even cheap potato laptop cameras).
- Removes all jitter so the mouse moves **butter-smooth**.
- Freezes the cursor for a split second when you click, so you **never miss small buttons or links**.
- Runs quietly in your system tray in the background and can launch automatically when Windows boots up!

---

## 2. How to use

### ✋ The Gestures

| Gesture | What to do | What happens |
| :--- | :--- | :--- |
| **Move Cursor** | Point or move your hand comfortably (elbow on desk!) | Pointer acceleration lets a 2-inch wrist flick reach screen edges! |
| **Left Click** | Lightly tap your **Index fingertip on your Middle fingertip** | Instant left click! (Zero mouse drift, never accidentally drags) |
| **Double Click** | Tap index on middle twice quickly | Opens folders, apps, or selects words |
| **Drag & Select** | Pinch **Thumb & Index tips together** | Locks drag to move windows or highlight text (release to drop) |
| **Jarvis Toggle** | **👌 "Super" gesture**: Thumb + Index touch, **last 3 fingers straight up** | Toggles tracking **ON / OFF** & summons the glowing HUD! |

> **Tilted Dual-Monitor Setup?** Kontroll automatically calculates your hand's 3D knuckle orientation, so it works even if your webcam is on a tilted side monitor! You can also pick your setup in the Tray Menu (*Left Monitor*, *Center*, *Right*).
> **No Arm Fatigue:** You don't need to wave your whole arm around. Rest your elbow on your desk, and relaxed finger/wrist twitches move the cursor across the entire screen!

---

### 🔮 The Jarvis HUD

Whenever you flash the **Super Gesture (👌)**:
- A glowing holographic neon-cyan HUD reticle pops up at the top of your screen.
- Plays a high-tech two-tone Jarvis audio chirp.
- **100% Click-through**: It won't steal your window focus or mess up whatever game/app you're using.
- Smoothly fades away after 2 seconds.

---

### 🚀 Auto-Launch on Boot

Want it to be ready as soon as you turn on your PC?
1. Look at your Windows taskbar system tray (bottom-right corner).
2. Right-click the **Project Kontroll** icon.
3. Click **Run on Windows Startup**.
4. That's it! Next time you log in, it starts silently in the background (no black terminal windows popping up).

---

### 🎯 Calibration Mode

Want to see what your camera sees and check your hand skeleton?
Run:
```bash
python main.py --calibrate
```
This opens the Diagnostic window where you can see:
- Your live camera feed with real-time hand skeleton tracking.
- The **Active Virtual Mousepad** (yellow box) so you don't have to wave your whole arm around.
- A live **Tap Meter** bar showing how close your fingers are to clicking.

---

## 3. Requirements & Setup

### What You Need:
- **OS**: Windows 10 or Windows 11 (64-bit)
- **Python**: Version 3.10, 3.11, or 3.12
- **Camera**: Any built-in laptop webcam or standard USB camera

### How to Install:

1. **Clone or download this repo**:
   ```bash
   git clone https://github.com/your-username/project-kontroll.git
   cd project-kontroll
   ```

2. **Install the dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start it up!**:
   ```bash
   # Run in background with system tray icon
   python main.py

   # Or run with the camera calibration window open
   python main.py --calibrate
   ```

---

## 4. Cool Tips

- **Resting your hand**: If you need to type on your keyboard, just do the **👌 Super Gesture** to switch to Standby, or put your hand down — it won't move your cursor accidentally.
- **Low-light rooms**: Kontroll automatically boosts contrast on dark webcam frames, so it still tracks even in a dim bedroom at night.
- **No arm fatigue**: You only need to move your hand inside the center box of the camera to reach every corner of your screen.
