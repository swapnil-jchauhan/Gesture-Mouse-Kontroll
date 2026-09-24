<div align="center">

# Project Kontroll

### Control your Windows PC with hand gestures like Jarvis using literally any webcam, even the trashiest ones.

<br/>

> Move your cursor with your finger, tap index on thumb with a closed fist to left click, tap index on middle for right click, and hold index on thumb with last three fingers up to drag windows.

</div>

---

## Quick Links

1. [What is this?](#1-what-is-this)
2. [How to use](#2-how-to-use)
3. [Requirements and Setup](#3-requirements-and-setup)
4. [Cool Tips](#4-cool-tips)

---

## 1. What is this?

Imagine being able to control ur PC without touching anything like Tony Stark interacting with holograms in mid air. 

Every webcam mouse project I found online had the same annoying issues:
1. The cursor shakes like crazy because cheap webcams have noisy sensors.
2. You miss your clicks because your hand twitches when tapping mid air and the cursor slides away from the button.
3. They lag or need expensive depth cameras.

So I made this

It is a lightweight software for Windows 11 that:
* Uses any regular webcam, even cheap potato laptop cameras.
* Naturally tracks your hand in real time so moving right moves right with zero camera confusion.
* Has literal OS level sticky aim assist. When your cursor gets close to ANY clickable button, link, tab, Chrome UI, or taskbar icon, it clings hard directly onto it so your clicks never slip off.
* Can be turned on or off anytime with a quick Shaka sign 🤙.
* When you log in on boot, it plays an epic Jarvis boot animation with sound effects and runs silently in the background with no black cmd console window.
* Removes all jitter so the mouse moves butter smooth.

---

## 2. How to use

### The Gestures

| Gesture | What to do | What happens |
| :--- | :--- | :--- |
| Activate or Standby 🤙 | Stick your Thumb and Pinky out with your middle three fingers folded in (Shaka sign) | Toggles Kontroll active or standby with a holographic HUD alert |
| Move Cursor | Point or move your hand comfortably with your elbow resting on your desk | Natural mirrored movement with pointer acceleration so a 2 inch wrist flick reaches screen edges |
| Left Click ✊ | Make a closed fist and lightly tap your Index fingertip on your Thumb | Instant left click with zero drift and hard sticky lock on buttons |
| Double Click ✊ | Tap index on thumb twice with a closed fist | Opens folders, apps, or selects words |
| Drag and Select 👌 | Touch Index on Thumb but keep your last three fingers straight UP | Locks drag to move windows or highlight text, release to drop |
| Right Click ✌️ | Lightly tap your Index fingertip on your Middle fingertip | Opens right click context menu |

Tilted Dual Monitor Setup: Kontroll automatically calculates your hand 3D knuckle orientation, so it works even if your webcam is on a tilted side monitor. You can also pick your setup in the Tray Menu (Left Monitor, Center, Right).

No Arm Fatigue: You do not need to wave your whole arm around. Rest your elbow on your desk, and relaxed finger wrist twitches move the cursor across the entire screen.

---

### The Jarvis Boot Animation

When you enter your password on boot and log into Windows:
* A glowing holographic neon cyan HUD reticle pops up at the top of your screen.
* It plays a multi stage Jarvis diagnostic boot sequence with power up chimes.
* It is 100% click through and never steals window focus from your apps.
* Runs silently in your system tray in the background with no black terminal windows.

---

### Auto Launch on Boot

Want it to be ready as soon as you turn on your PC?
1. Look at your Windows taskbar system tray in the bottom right corner.
2. Right click the Project Kontroll icon.
3. Click Run on Windows Startup.
4. Next time you log in, it starts silently in the background.

---

### Calibration Mode

Want to see what your camera sees and check your hand skeleton?
Run:
```bash
python main.py --calibrate
```
This opens the Diagnostic window where you can see:
* Your live camera feed with real time hand skeleton tracking.
* The Active Virtual Mousepad yellow box so you do not have to wave your whole arm around.
* Live tap meters and sticky aim assist telemetry.

---

## 3. Requirements and Setup

### What You Need:
* OS: Windows 10 or Windows 11 (64 bit)
* Python: Version 3.10, 3.11, or 3.12
* Camera: Any built in laptop webcam or standard USB camera

### How to Install:

1. Clone or download this repo:
```bash
git clone https://github.com/your-username/project-kontroll.git
cd project-kontroll
```

2. Install the dependencies:
```bash
pip install -r requirements.txt
```

3. Start it up:
```bash
# Run in background with system tray icon
python main.py

# Or run with the camera calibration window open
python main.py --calibrate
```

---

## 4. Cool Tips

* Shaka to Toggle: If you want to take a break or type without the mouse tracking, just flash the Shaka sign 🤙 for a second to put Kontroll into standby. Flash it again to wake it back up.
* Resting your hand: If you need to type on your keyboard, just put your hand down on your desk. It will not move your cursor accidentally.
* Hard Sticky Aim Assist: When you hover near buttons, context menus, or Chrome tabs, the cursor clings hard to the center. When you tap your fingers together, it will not slip or twitch off the button. To move to something else, just pull away or flick your wrist normally.
* Low light rooms: Kontroll automatically boosts contrast on dark webcam frames, so it still tracks even in a dim bedroom at night.
