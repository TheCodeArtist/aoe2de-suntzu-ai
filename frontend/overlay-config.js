/**
 * overlay-config.js — shared configuration for the Sun Tzu overlay.
 *
 * Loaded by both index.html (via script.js) and font-calibration.html so that
 * font definitions and the font-size formula live in exactly one place.
 *
 * Exposes two globals used by both consumers:
 *   QUOTE_FONTS    — array of font descriptors
 *   computeBasePx  — returns the basePx the overlay uses for a given text
 */

"use strict";

/**
 * All available quote fonts. One is chosen at random for each new quote.
 *
 * Each entry: { family, file, weight, scale }
 *   family  — CSS font-family name used at runtime
 *   file    — filename inside fonts/ (single source of truth; @font-face injected automatically)
 *   weight  — CSS font-weight to request
 *   scale   — compensates for differing cap-heights so all fonts render at the same visual size.
 *             Baseline: Goudy Mediaeval DemiBold cap-height ≈ 68% of em-square (scale = 1.00).
 *             To re-calibrate: open font-calibration.html, adjust sliders, copy the snippet.
 *
 * To add a new font: drop the .ttf into frontend/fonts/ and add one entry here.
 */
const QUOTE_FONTS = [
  { family: "Goudy Mediaeval DemiBold",     file: "Goudy Mediaeval DemiBold.ttf",   weight: "700", scale: 1.00 },
  { family: "Goudy Medieval Alternate",     file: "Goudy Medieval Alternate.ttf",   weight: "400", scale: 0.90 },
  { family: "Kingthings Foundation",        file: "Kingthings Foundation.ttf",      weight: "100", scale: 0.85 },
  { family: "Morris Roman Black",           file: "MorrisRoman-Black.ttf",          weight: "900", scale: 1.00 },
  { family: "Morris Roman Alternate Black", file: "MorrisRomanAlternate-Black.ttf", weight: "900", scale: 1.00 },
];

/**
 * Returns the base font size (px) the live overlay uses for a quote of the
 * given length. Larger quotes get a smaller base so they fit the text area.
 *
 * Keep this table in sync with the visual design — it is the single source of
 * truth consumed by both the overlay (script.js) and the calibration tool.
 *
 * @param {string} text  The full quote string.
 * @returns {number}     Base px before per-font scale is applied.
 */
function computeBasePx(text) {
  const len = text.length;
  if      (len <  50) return 28;
  else if (len <  80) return 26;
  else if (len < 120) return 24;
  else if (len < 150) return 22;
  else                return 18;
}
