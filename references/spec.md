# Sun Tzu AoE2 Commentary Overlay - Technical Specification

**Version:** 1.0  
**Date:** March 14, 2026  
**Status:** Approved

## 1. Overview
A specialized streaming tool for *Age of Empires II: Definitive Edition* (AoE2:DE) that provides an automated, witty commentary overlay in the persona of Sun Tzu. The system captures the game state via screenshots, analyzes them using a Vision-enabled LLM, and displays relevant quotes or strategic advice on an OBS overlay.

## 2. System Architecture

The application consists of two main components:
1.  **Backend (Python Desktop App):** Handles configuration, screen capture, AI processing, and hotkey management.
2.  **Frontend (OBS Browser Source):** A local web page that displays the visual overlay and animates the text.

### High-Level Data Flow
1.  **Trigger:** Timer (Random Interval) OR Global Hotkey.
2.  **Capture:** Backend captures the specific "Age of Empires II: Definitive Edition" window.
3.  **Process:** Backend sends the screenshot + System Prompt + Recent Context to the LLM Endpoint.
4.  **Response:** LLM generates a short, witty quote.
5.  **Display:** Backend pushes the quote to the Frontend via WebSocket/Server-Sent Events.
6.  **Render:** Frontend fades in the Sun Tzu portrait and types out the text (RPG style).
7.  **Cooldown:** Overlay fades out; timer resets.

## 3. Python Backend (Desktop Application)

### 3.1. GUI & Configuration
Built using a native Python GUI framework (e.g., `tkinter` or `PyQt`) to ensure a standalone application feel.

**Key Features:**
*   **Window Selector:** Dropdown list of currently open windows to select the game target (e.g., "Age of Empires II: Definitive Edition"). The app must remember this selection across sessions.
*   **LLM Configuration:**
    *   **Endpoint URL:** Support for standard OpenAI-compatible endpoints (e.g., `https://api.openai.com/v1/chat/completions` or local `http://localhost:11434/v1/chat/completions`).
    *   **API Key:** Secure input field for the user's API key.
    *   **Model Name:** Input field (e.g., `gpt-4o`, `claude-3-5-sonnet`).
*   **Timing Controls:**
    *   **Min Interval:** Minimum time (seconds/minutes) between auto-triggers.
    *   **Max Interval:** Maximum time (seconds/minutes) between auto-triggers.
    *   **Enable/Disable Auto-Trigger:** Checkbox.
*   **Hotkey Recorder:**
    *   UI component that listens for a key combination (e.g., `Ctrl+Shift+T`) and saves it as the "Manual Trigger."
*   **Personality Engine (System Prompt):**
    *   **Large Text Area:** Fully editable system prompt.
    *   **Presets:** Dropdown to load pre-written prompts:
        *   *The Serious Strategist* (Classic Sun Tzu quotes only).
        *   *The Sarcastic Observer* (Roasts the player for idle villagers/floating resources).
        *   *The Helpful Coach* (Genuine advice based on the game state).
    *   **Persistence:** Custom prompts must be saved to `config.json`.

### 3.2. Core Logic
*   **Screen Capture:** Uses libraries like `pygetwindow` and `pyautogui` (or `mss`) to capture *only* the client area of the selected window handle (HWND), ensuring support for Windowed/Borderless modes.
*   **Context Window:** Maintains a list of the last $N$ (default: 5) generated quotes to prevent repetition and allow the AI to reference recent comments.
*   **Global Hotkey Listener:** Uses `keyboard` or `pynput` to detect the configured hotkey even when the app is in the background.

## 4. Frontend (OBS Browser Source)

### 4.1. Visual Assets
The overlay is constructed from `resources/sun-tzu-background.png`, split into three layers to allow for dynamic resizing and polished animations:
1.  **Layer 1 (Bottom):** Parchment Background (Scaling 9-slice image to fit text length).
2.  **Layer 2 (Middle):** Sun Tzu Portrait (Fixed position/size).
3.  **Layer 3 (Top):** Border/Frame (Overlaying the edges).

### 4.2. Animation & Layout
*   **Style:** "RPG/Visual Novel" text box.
*   **Entrance:**
    1.  Parchment unrolls or fades in.
    2.  Sun Tzu portrait fades in.
    3.  Text begins typing.
*   **Text Effect:**
    *   **Typewriter:** Letters appear one by one.
    *   **Pacing:** Variable speed (randomized slightly) to mimic natural speech patterns/thought.
    *   **Font:** A legible, serif, "historical" font (e.g., Cinzel or similar).
*   **Exit:** After a duration (calculated based on text length, e.g., `word_count * 0.5s + 3s`), the entire overlay fades out opacity to 0.

## 5. AI Integration Strategy

### 5.1. Prompt Engineering
The prompt must instruct the AI to:
1.  **Analyze the Image:** Identify game age (Dark/Feudal/Castle/Imperial), resource counts (floating wood/gold?), idle villagers, military composition, and active battles.
2.  **Consult Domain Knowledge:** Refer to `references/AoE2-Commentary-Bot-Ideas.md` for specific aspects of interest, including:
    *   **Build Order Timings:** Comparing current time vs. expected Feudal/Castle times.
    *   **Economy Balance:** Flagging floating resources or improper villager distribution (e.g., too much wood, not enough farms).
    *   **Military Composition:** Identifying counter-units (e.g., Pikes vs. Knights) and missing upgrades (Bloodlines, Fletching).
    *   **Strategic Positioning:** Comments on hill control, forward buildings, or walling gaps.
3.  **Adopt Persona:** Speak as Sun Tzu would, but with knowledge of AoE2 mechanics.
4.  **Be Witty:** Use metaphors relating war to gaming (e.g., "A mouse with no clicks is like a soldier with no spear").
5.  **Output Format:** JSON or plain text containing *only* the quote.

### 5.2. Context Management
Payload sent to LLM:
```json
{
  "messages": [
    {"role": "system", "content": "You are Sun Tzu... [User Configured Prompt]"},
    {"role": "user", "content": [
        {"type": "text", "text": "Current Game State Screenshot. Recent quotes: [List of last 5 quotes]"},
        {"type": "image_url", "image_url": "data:image/jpeg;base64,..."}
    ]}
  ]
}
```

## 6. Project Structure

```
aoe2-suntzu-overlay/
├── assets/
│   ├── sun-tzu-portrait.png
│   ├── parchment-bg.png
│   └── frame.png
├── backend/
│   ├── main.py           # Entry point & GUI
│   ├── capture.py        # Screen capture logic
│   ├── ai_client.py      # LLM API handling
│   ├── config_manager.py # Settings persistence
│   └── server.py         # Local web server for OBS
├── frontend/
│   ├── index.html        # OBS Browser Source entry
│   ├── style.css         # Animations & Layout
│   └── script.js         # WebSocket client & Typewriter logic
├── references/
│   └── spec.md
├── requirements.txt
└── README.md
```

## 7. Future Considerations (Post-V1)
*   **TTS Integration:** Generating audio for the quotes.
*   **Twitch Integration:** Allowing chat to trigger Sun Tzu via channel points.
*   **Game Memory Reading:** Reading memory addresses instead of vision (more accurate resource counts, but higher ban risk/complexity).
