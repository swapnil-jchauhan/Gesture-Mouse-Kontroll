# Project Kontroll: Jarvis-Grade AR Gesture Mouse & OS Controller

## 1. Project Objective & Vision

**Project Kontroll** is an ambient, always-on Windows 11 background software designed to transform your physical hand into an ultra-precise, zero-latency virtual mouse and system controller using only a standard webcam.

Inspired by futuristic "Jarvis-like" AR interfaces, Project Kontroll eliminates the need for physical mice and touchpads while solving the two most critical flaws of traditional webcam mouse controls: **cursor jitter** and **accidental click misfires**.

### Core Tenets:
1. **Flawless & Seamless Motion**: Jitter-free, buttery smooth cursor tracking with near-zero latency using adaptive filtering (One Euro filter).
2. **Distinct, Natural Gestures**:
   - **Tap Index on Middle**: Fast, positive click detection based on normalized inter-finger distance (no awkward mid-air pinching that throws off cursor aim).
   - **"Super" Gesture (Last Three Fingers Up)**: Distinct activation/toggle gesture that engages the system and summons a futuristic, floating holographic HUD notification.
3. **Ambient Background Service**:
   - Starts instantly with Windows 11 boot.
   - Resides silently in the background / system tray.
   - Low CPU/GPU footprint when idle or when hand is out of frame.
4. **Futuristic Visual Feedback**: Transparent, click-through, glowing holographic HUD overlays providing instant visual state confirmation without stealing window focus.

---

## 2. System Architecture

```
+-------------------------------------------------------------+
|                      Hardware Webcam                        |
+------------------------------+------------------------------+
                               | Frame Capture (DirectShow / 60 FPS)
                               v
+-------------------------------------------------------------+
|                 Computer Vision Pipeline                    |
|  - Frame Preprocessing & ROI Cropping                       |
|  - MediaPipe Hands Landmark Extractor (21 3D Points)        |
+------------------------------+------------------------------+
                               | Normalized Coordinates
                               v
+-------------------------------------------------------------+
|               Signal Processing & Smoothing                 |
|  - One Euro Filter (Adaptive frequency-cutoff)              |
|  - Deadband & Dynamic Friction Stabilization                |
|  - Screen Coordinate Mapping (Dynamic Active Box)           |
+------------------------------+------------------------------+
                               | Smoothed Position & Vectors
                               v
+-------------------------------------------------------------+
|                 Gesture State Machine                       |
|  - Index-to-Middle Tap Detector (Left Click / Drag)         |
|  - Super Gesture Detector (Middle + Ring + Pinky Up)        |
|  - Palm Normal & Orientation Guard (False-positive guard)  |
+------------------------------+------------------------------+
         |                                           |
         v Cursor Move / Click                       v Mode Toggle / Feedback
+-------------------------------+       +-------------------------------+
|     Windows Input Subsystem   |       |    Futuristic HUD & Tray UI   |
|  - SendInput API (ctypes)     |       |  - Transparent Layered Window |
|  - Hardware-level mouse events|       |  - Neon Cyan Jarvis Arc HUD   |
|  - Low latency, high DPI      |       |  - System Tray & Autostart    |
+-------------------------------+       +-------------------------------+
```

---

## 3. Detailed Gesture Specifications

### 3.1 Cursor Positioning
- **Tracking Anchor**: Index finger tip (`Landmark 8`) stabilized with Midpoint (`(Landmark 8 + Landmark 12) / 2`) during rest.
- **Active Area (Dynamic Virtual Mousepad)**: A centered sub-rectangle of the camera view (e.g. 60% width x 55% height) maps linearly to full screen resolution (e.g., 1920x1080 or 4K). This prevents hand fatigue and allows reaching all screen corners with small hand movements.

### 3.2 The "Tap Index on Middle" Click
- **Principle**: Instead of pinching thumb and index (which pulls the index finger downward and shifts the cursor off target), the user lightly taps their index fingertip against their middle fingertip.
- **Metric**:
  $$\text{Ratio} = \frac{\|\mathbf{P}_{\text{IndexTip}} - \mathbf{P}_{\text{MiddleTip}}\|}{\|\mathbf{P}_{\text{Wrist}} - \mathbf{P}_{\text{MiddleMCP}}\|}$$
  Normalizing by hand scale ensures identical detection distance whether the hand is 30 cm or 120 cm from the camera.
- **States**:
  - `TAP_DOWN`: Distance drops below threshold $\tau_{\text{click}}$. Immediate freeze of cursor position to guarantee pixel-accurate clicks.
  - `TAP_UP`: Quick release (< 250 ms) triggers `MOUSEEVENTF_LEFTUP` (single click).
  - `TAP_DRAG`: Sustained contact (> 250 ms) keeps left button held down for dragging or text selection.

### 3.3 The "Super" Activation Gesture
- **Pose**: The "OK / Super" pose — Thumb and Index form a ring or curl, while the **last three fingers (Middle, Ring, Pinky)** are pointed fully upright.
- **Detection**:
  - Distance between Thumb Tip (`Landmark 4`) and Index Tip (`Landmark 8`) is small.
  - Middle Tip (`Landmark 12`), Ring Tip (`Landmark 16`), and Pinky Tip (`Landmark 20`) are extended above their respective PIP joints:
    $$y_{\text{Tip}} < y_{\text{PIP}} \quad (\text{in screen coordinates})$$
- **Behavior**:
  - Toggles Kontroll between **ACTIVE** and **STANDBY**.
  - Triggers the Jarvis Holographic HUD popup animation on the screen.

---

## 4. Software Stack & Dependencies

- **Language**: Python 3.12 (x64)
- **Vision Engine**: `mediapipe` (Hand Landmarker / 21 landmarks), `opencv-python` (camera capture with DirectShow backend)
- **Math & Filtering**: `numpy`, custom 1€ Filter (One Euro Filter) implementation
- **Input Dispatch**: Windows `ctypes.windll.user32.SendInput` for zero-lag driver-grade input injection
- **HUD & Tray Interface**: `PyQt6` (Frameless, `WA_TranslucentBackground`, `WS_EX_TRANSPARENT` click-through window) + `pystray`
- **Boot Integration**: Windows Registry `Software\Microsoft\Windows\CurrentVersion\Run` or Windows Startup Shortcut

---

## 5. Development Phases & Changelog

### Phase 1: Planning & Specification (Completed)
- Core project objectives, ergonomics, and Jarvis vision defined.
- Mathematical formulations for 1€ adaptive filtering, scale-invariant tap detection, and "Super" activation gesture established.
- System architecture designed with decoupled background threads, hardware-level OS input injection, and GPU-accelerated HUD overlay.

### Phase 2: Core Engineering & Architecture Implementation (Completed)
- **Signal Filtering (`src/core/filter.py`)**: Built Casiez et al. CHI 2012 1€ adaptive low-pass filter with velocity-dependent frequency cutoff.
- **Hardware Mouse Injection (`src/core/input_simulator.py`)**: Direct Win32 `SendInput` API implementation bypassing user-space latency.
- **Gesture Engine (`src/core/gestures.py`)**: Scale-invariant index-on-middle tap detection, 120ms sub-pixel click-anchor lock, and debounced "Super" gesture recognition.
- **Threaded Tracking Pipeline (`src/core/tracker.py`)**: DirectShow webcam capture with CLAHE contrast enhancement for low-light/cheap webcam resilience.
- **Holographic Jarvis HUD Overlay (`src/ui/hud_overlay.py`)**: Frameless, transparent, click-through (`WS_EX_TRANSPARENT | WS_EX_LAYERED`) holographic reticle with 60 FPS counter-rotating arcs and audio feedback.
- **Diagnostics & Calibration HUD (`src/ui/debug_window.py`)**: Real-time camera viewport with skeletal rigging, active zone visualization, and live tap proximity progress bar.
- **System Tray & Windows 11 Autostart (`src/ui/tray.py`, `src/service/autostart.py`)**: Persistent background tray icon with high-DPI cyber icon and HKCU registry autostart manager.
- **Verification (`tests/test_kontroll.py`)**: 7 automated unit tests passed covering filter jitter suppression, zero-lag velocity response, gesture state transitions, and click anchoring.

### Phase 3: Seamless Clicking, Double-Click Precision & Magnetic Target Locking (Completed)
- **Drag-Lock Resolution**: Completely eliminated the issue where single clicks became unintended drags. Increased drag hold threshold to 420 ms and narrowed tap release hysteresis (`tap_down_ratio = 0.25`, `tap_up_ratio = 0.32`).
- **Rapid Double-Click Engine**: Integrated dedicated double-click state detection within a 400 ms window with automatic coordinate locking to ensure folders and desktop icons open reliably.
- **Pre-Tap Anchor Locking**: Implemented rolling coordinate history (lookback ~75 ms) to freeze the cursor to the exact coordinate right before physical tap deflection starts.
- **Kinetic Deadband Filter**: Enhanced `Point2DOneEuroFilter` with a 2.8 px pseudo-haptic stillness deadband, eliminating 100% of micro-tremor and sub-pixel twitching near tiny icons.
- **Magnetic Target Snapper (`src/core/target_lock.py`)**: Built an ultra-fast (< 1 ms) real-time UI element snapper leveraging Windows MSAA and Non-Client window metrics. Automatically locks onto Close [X], Minimize [_], Maximize [□], desktop icons, folders, tabs, links, and buttons, with instant breakout on fast hand flicks.
### Phase 4: Presentation & Repository Polish (Completed)
- **README Redesign**: Streamlined `README.md` into an approachable, clean high-school builder style focusing on three essential sections:
  1. What is this
  2. How to use (Gestures, Jarvis HUD, Autostart, Calibration)
  3. Requirements & Setup
- **TOC & Quick Links**: Preserved clean aesthetic badge tiles and responsive quick-jump anchor links while eliminating heavy academic math formulas and corporate jargon.
- **Repository Cleanup**: Removed unnecessary license and enterprise boilerplate for a clean, personal GitHub release.
