/**
 * Sun Tzu AoE2 Commentary Overlay — script.js
 *
 * State machine:  IDLE → ENTERING → TYPING → DISPLAYING → EXITING → IDLE
 *
 * Communication:  Server-Sent Events (SSE) from http://localhost:5000/events
 * Payload format: { "text": "...", "duration_ms": 8500 }
 */

"use strict";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const SSE_URL = `${window.location.origin}/events`;

/** Min/max milliseconds between typewriter words (random range). */
const TYPEWRITER_MIN_MS = 120;
const TYPEWRITER_MAX_MS = 260;

// QUOTE_FONTS is defined in overlay-config.js, loaded before this script.

/**
 * Inject a <style> block with @font-face rules derived from QUOTE_FONTS.
 * This replaces the static declarations that were previously in style.css.
 */
(function injectFontFaces() {
  const rules = QUOTE_FONTS.map(({ family, file, weight }) =>
    `@font-face {\n` +
    `  font-family: '${family}';\n` +
    `  font-style: normal;\n` +
    `  font-weight: ${weight};\n` +
    `  font-display: block;\n` +
    `  src: url('fonts/${file}') format('truetype');\n` +
    `}`
  ).join("\n\n");
  const style = document.createElement("style");
  style.textContent = rules;
  document.head.appendChild(style);
}());
/** Milliseconds to wait before reconnecting after an SSE error. */
const RECONNECT_BASE_MS = 2000;
const RECONNECT_MAX_MS = 5000;

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

const State = Object.freeze({
  IDLE: "IDLE",
  ENTERING: "ENTERING",
  TYPING: "TYPING",
  DISPLAYING: "DISPLAYING",
  EXITING: "EXITING",
});

let currentState = State.IDLE;

function setState(next) {
  currentState = next;
  // console.log(`[SunTzu] State: ${next}`);
}

// ---------------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------------

const overlay = document.getElementById("overlay");
const quoteText = document.getElementById("quote-text");

// ---------------------------------------------------------------------------
// SSE connection with exponential backoff reconnection
// ---------------------------------------------------------------------------

let reconnectDelay = RECONNECT_BASE_MS;
let eventSource = null;

function connectSSE() {
  if (eventSource) {
    eventSource.close();
  }

  console.log("[SunTzu] Connecting to SSE:", SSE_URL);
  eventSource = new EventSource(SSE_URL);

  eventSource.onopen = () => {
    console.log("[SunTzu] SSE connected.");
    reconnectDelay = RECONNECT_BASE_MS;
  };

  eventSource.onmessage = (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch (err) {
      console.warn("[SunTzu] Failed to parse SSE payload:", event.data, err);
      return;
    }

    if (!payload.text) {
      console.warn("[SunTzu] Payload missing 'text' field:", payload);
      return;
    }

    // Only display a new quote if we're idle; drop if an animation is running.
    if (currentState !== State.IDLE) {
      console.log("[SunTzu] Busy (%s) — dropping incoming quote.", currentState);
      return;
    }

    // Fire and forget the async sequence
    playQuoteSequence(payload.text, payload.duration_ms || 8000);
  };

  eventSource.onerror = (err) => {
    console.error("[SunTzu] SSE error — reconnecting in", reconnectDelay, "ms", err);
    eventSource.close();
    eventSource = null;

    setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
      connectSSE();
    }, reconnectDelay);
  };
}

// ---------------------------------------------------------------------------
// Async Flow Control Helpers
// ---------------------------------------------------------------------------

/**
 * Returns a Promise that resolves after `ms` milliseconds.
 */
function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Returns a Promise that resolves when the event fires OR after the timeout.
 * Resolves to true if event fired, false if timed out.
 */
function waitForEvent(target, eventType, timeoutMs) {
  return new Promise((resolve) => {
    let timer;

    const listener = (e) => {
      // Ignore bubbled events from child elements (e.g. span transitionend).
      if (e.target !== target) return;
      clearTimeout(timer);
      target.removeEventListener(eventType, listener);
      resolve(true);
    };

    target.addEventListener(eventType, listener);

    timer = setTimeout(() => {
      target.removeEventListener(eventType, listener);
      console.warn(`[SunTzu] Timed out waiting for ${eventType} (${timeoutMs}ms)`);
      resolve(false);
    }, timeoutMs);
  });
}

// ---------------------------------------------------------------------------
// Quote display pipeline (Linear Async Flow)
// ---------------------------------------------------------------------------

/**
 * Main async sequence for displaying a quote.
 * IDLE → ENTERING → TYPING → DISPLAYING → EXITING → IDLE
 */
async function playQuoteSequence(text, durationMs) {
  if (currentState !== State.IDLE) return;

  try {
    // --- 1. ENTERING ---
    setState(State.ENTERING);
    quoteText.textContent = "";
    
    // Reset classes
    overlay.classList.remove("hidden", "fading-out", "visible", "entering");
    void overlay.offsetWidth; // Force reflow
    overlay.classList.add("entering");

    // Wait for animation (450ms CSS + buffer)
    await waitForEvent(overlay, "animationend", 1000);

    // Guard: If something weird happened and we aren't entering anymore, abort
    if (currentState !== State.ENTERING) return;

    // --- 2. TYPING ---
    overlay.classList.remove("entering");
    overlay.classList.add("visible");
    setState(State.TYPING);

    const font = applyRandomFont();
    updateFontSize(text, font);
    await typewriter(quoteText, text);

    // Guard
    if (currentState !== State.TYPING) return;

    // --- 3. DISPLAYING ---
    setState(State.DISPLAYING);
    await wait(durationMs);

    // Guard
    if (currentState !== State.DISPLAYING) return;

    // --- 4. EXITING ---
    setState(State.EXITING);
    overlay.classList.remove("visible");
    overlay.classList.add("fading-out");

    // Wait for transition (600ms CSS + buffer)
    await waitForEvent(overlay, "transitionend", 1200);

  } catch (err) {
    console.error("[SunTzu] Error in quote sequence:", err);
  } finally {
    // --- 5. RESET TO IDLE ---
    // If we bailed out while the overlay was still visible (not already fading),
    // trigger the fade first so it doesn't freeze semi-transparent.
    // The inner try/catch ensures any unexpected DOM error can never prevent
    // setState(IDLE) from running, which would lock the state machine permanently.
    try {
      if (overlay.classList.contains("visible") || overlay.classList.contains("entering")) {
        overlay.classList.remove("visible", "entering");
        overlay.classList.add("fading-out");
        await waitForEvent(overlay, "transitionend", 1200);
      }
    } catch (cleanupErr) {
      console.warn("[SunTzu] Cleanup fade failed (best-effort):", cleanupErr);
    }
    overlay.classList.remove("fading-out", "visible", "entering");
    overlay.classList.add("hidden");
    quoteText.textContent = "";
    setState(State.IDLE);
  }
}

/**
 * Async typewriter effect.
 * Resolves when typing is complete.
 */
function typewriter(element, text) {
  return new Promise((resolve) => {
    element.textContent = "";

    const words = text.split(" ");
    const spans = words.map((word, i) => {
      const span = document.createElement("span");
      span.textContent = i < words.length - 1 ? word + " " : word;
      element.appendChild(span);
      return span;
    });

    let index = 0;
    let timeoutId = null;

    function revealNextWord() {
      if (currentState !== State.TYPING) {
        clearTimeout(timeoutId);
        resolve();
        return;
      }

      if (index >= spans.length) {
        resolve();
        return;
      }

      spans[index].classList.add("visible");
      index += 1;

      timeoutId = setTimeout(revealNextWord, randomBetween(TYPEWRITER_MIN_MS, TYPEWRITER_MAX_MS));
    }

    revealNextWord();
  });
}

/**
 * Picks a random font from QUOTE_FONTS, applies it to the quote element,
 * and returns the font entry so the caller can use its scale factor.
 */
function applyRandomFont() {
  const font = QUOTE_FONTS[Math.floor(Math.random() * QUOTE_FONTS.length)];
  quoteText.style.fontFamily = `'${font.family}'`;
  quoteText.style.fontWeight = font.weight;
  return font;
}

/**
 * Sets the font size so the text fits the overlay at a consistent visual size
 * regardless of which font is active.
 *
 * Delegates to computeBasePx() from overlay-config.js for the length→size
 * table, then applies the per-font scale factor.
 */
function updateFontSize(text, font) {
  quoteText.style.fontSize = `${Math.round(computeBasePx(text) * font.scale)}px`;
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

function randomBetween(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

connectSSE();
