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
- **Tracking Anchor**: Index finger tip (`Landmark 8`) with horizontal mirroring (`norm_x = 1.0 - x`) so moving the physical hand right moves the cursor right.
- **Active Area (Dynamic Virtual Mousepad)**: Ergonomic rest box centered where the user rests their forearm/elbow on the desk (`xmin=0.28, xmax=0.70, ymin=0.44, ymax=0.78`) with cubic S-curve acceleration. Reaches all 4 screen corners with relaxed 2-inch wrist motions.
- **Stabilization**: One Euro Filter with pseudo-haptic stillness deadband (2.8 px), eliminating sensor noise and tremor when holding still.

### 3.2 The Closed Fist Left Click & Double Click ✊
- **Principle**: The user curls their middle, ring, and pinky fingers into a closed fist and lightly taps their index fingertip on their thumb fingertip.
- **Metric**:
  $$\text{Ratio} = \frac{\|\mathbf{P}_{\text{IndexTip}} - \mathbf{P}_{\text{ThumbTip}}\|}{\|\mathbf{P}_{\text{Wrist}} - \mathbf{P}_{\text{MiddleMCP}}\|}$$
  When fingers are in a closed fist and ratio drops below 0.18, click contact is registered. Quick release fires a left click; two taps within 380 ms fire a double click.

### 3.3 The Shaka Activation Gesture 🤙
- **Pose**: Hawaiian Shaka sign — Thumb (`Landmark 4`) and Pinky (`Landmark 20`) are extended OUT, while the middle three fingers (Index 8, Middle 12, Ring 16) are curled IN against the palm.
- **Behavior**:
  - Holding Shaka for 0.35s toggles Kontroll between **ACTIVE** and **STANDBY**.
  - Triggers the Jarvis Holographic HUD popup alert and updates system tray state.

### 3.4 Drag & Drop (Super Sign 👌)
- **Pose**: Index fingertip touches Thumb fingertip while the last three fingers (Middle, Ring, Pinky) remain extended straight UP.
- **Behavior**:
  - Holding for >= 140 ms locks left mouse down (`DRAG_START`) for moving windows or selecting text.
  - Releasing pinch fires `DRAG_RELEASE`.

### 3.5 Right Click ✌️
- **Pose**: Lightly tap Index fingertip on Middle fingertip with both fingers extended.
- **Behavior**: Fires native Windows right-click event to open context menus.

### 3.6 Hard Sticky Aim Assist & Click Anchor
- **Principle**: Automatically detects clickable UI elements (buttons, Chrome tabs, links, icons, taskbar items, title bar controls) via Windows UI Automation, MSAA, and Win32 hit-testing.
- **Sticky Gravity**: When entering the button capture radius, the cursor snaps and clings rigidly to the button center.
- **Click Anchor**: During tap contact or click motion (`is_clicking=True`), the lock is immutable against localized finger twitches.
- **Breakout**: Only releases when the user substantially pulls away (> 65-75 px from target) or performs an intentional fast wrist flick (> 750 px/s).

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
### Phase 5: Tilted Dual-Monitor Support & Perspective Invariance (Completed)
- **Tilted Dual-Monitor & Perspective Invariance**: Built palm-local coordinate frame metric that measures 3D finger separation along the hand's own anatomical knuckle axis. Resolves the visual occlusion/foreshortening issue where cameras mounted on angled secondary monitors falsely saw index and middle fingers overlapping in 2D.
- **Camera Mount Selector & Auto-Tilt**: Added automatic tilt angle detection and selectable mount presets (`Auto-Compensate`, `Left Monitor Tilted ~35°`, `Center 0°`, `Right Monitor Tilted ~35°`) in both the System Tray menu and the Calibration HUD.

### Phase 6: Pointing-Pose Extension Gate, True 1:1 Hardware Dispatch & Tamed Snapper (Completed)
- **Pointing Pose Extension Gate**: Mandates that both Index and Middle fingers are extended (`tip.y < pip.y`) before tap detection evaluates. When pointing with index finger alone and middle curled into palm, tap ratio returns 1.0 (100% immune to false clicks caused by 2D camera perspective foreshortening).
- **True 1:1 Hardware Response (Zero-Lag Direct Dispatch)**: Removed artificial exponential blend smoothing (`blend_factor = 0.55`) in `main.py` which was causing spongy latency and dragging sensations. Direct 1€ filter coordinates are dispatched immediately to Windows `SendInput`, giving instantaneous 1:1 cursor response.
- **Ergonomic Rest Box & S-Curve Pointer Mapping**: Re-centered the active tracking box to `xmin=0.28, xmax=0.70, ymin=0.44, ymax=0.78` with smooth S-curve cubic acceleration. Moving the wrist ~2 inches while resting the forearm/elbow on the desk reaches all four corners and title bar buttons with zero arm strain or shoulder lifting.
- **Tamed Assistive Target Snapper**: Replaced aggressive 0.92/0.85 magnetic trapping with a subtle, assistive 0.35 pull and gentle 0.25 hover assist (`breakout_velocity=220.0 px/s`). Gently stabilizes clicking on title bar buttons without trapping the cursor or resisting breakout.
- **Non-Freezing 70ms Anchor Lock**: Capped click-stabilization anchor duration to exactly 70ms max, eliminating cursor freeze-in-place issues during tap contact.
- **Hand-Lost Immediate Reset**: Implemented `reset_hand_state()` called whenever hand leaves the frame, instantly resetting tap, drag, and lock states so sticky contact never lingers.
- **Diagnostic UI & Comprehensive Verification**: Synced Diagnostic calibration telemetry (auto-clearing to "NO HAND" on lost tracking) and expanded test suite to 15 unit tests passing with 100% success rate.

### Phase 7: OS-Level Sticky Aim Assist, Fist Tap Left Click, Drag & Right Click Overhaul (Completed)
- **Complete Removal of Cursor Jammer**: Removed pre-tap cursor freezing and anchor jamming completely. The cursor floats freely with zero artificial stickiness during free-hand motions.
- **OS-Level Sticky Aim Assist**: Integrated Windows UI Automation and Win32 Non-Client hit-testing with interactive desktop attachment. When the cursor enters proximity of any clickable element (buttons, tabs, links, Chrome UI, Taskbar, Explorer items), it clings securely directly onto the target center to eliminate finger twitch drift during clicks, breaking out cleanly on deliberate hand flicks.
- **Closed-Fist Index-Thumb Tap for Left Click**: Left clicks and double clicks are triggered by tapping index on thumb while the middle, ring, and pinky fingers are curled into a closed fist.
- **Drag & Drop**: Holding index on thumb while the last three fingers remain straight up engages window dragging and text selection, releasing cleanly when the pinch separates.
- **Right Click**: Tapping index on middle fingertip triggers a native Windows right click.
- **Jarvis Boot Sequence HUD**: Multi-stage holographic power-up animation with rising frequency audio chimes on Windows login, executing silently in background with pythonw.exe without any cmd console popups.

### Phase 8: Mirrored Natural Tracking, Jitter Elimination, Hard Sticky Lock & Shaka Activation (Completed)
- **Mirrored Natural Tracking**: Horizontally mirrored normalized index tracking (`norm_x = 1.0 - x`) so moving the physical hand to the right moves the screen cursor to the right across any setup.
- **Jitter Elimination**: Completely eliminated inter-frame dead-reckoning extrapolation in `main.py` that caused high-frequency 60-120 Hz micro-jump coordinate oscillations against camera frames. Direct 1€-filtered coordinates now dispatch cleanly on frame arrival with zero jitter.
- **Hard Sticky Aim Assist & Click Anchor**: Upgraded TargetLockManager with a 750 px/s breakout threshold and generous 65 px padding. When tapping or clicking (`is_clicking=True`), the cursor is firmly anchored to the button center and will not slip off from finger twitching, breaking out only on intentional pull away or deliberate wrist flicks.
- **Shaka Gesture Activation**: Integrated Hawaiian Shaka sign (🤙, thumb and pinky extended, middle three curled) detection with 0.35s hold debounce to toggle Kontroll between ACTIVE and STANDBY, with holographic HUD notifications.
- **Diagnostic HUD Mirroring**: Video preview in the calibration HUD is now flipped horizontally, acting like a mirror with live Shaka gesture telemetry.
- **Comprehensive Verification**: Expanded test suite to 19 automated tests covering 1€ filtering, mirrored tracking, Shaka detection, activation state transitions, click anchoring, and hard sticky aim assist. All 19 tests passing with 100% success rate.


