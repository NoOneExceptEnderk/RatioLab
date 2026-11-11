// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
export function significantText(value, digits) {
  const [mantissa, power] = value.toExponential(digits - 1).split('e');
  if (power == null) return mantissa;
  const exponent = Number(power);
  if (exponent >= -4 && exponent < digits) return String(Number(mantissa + 'e' + power));
  const sign = exponent < 0 ? '-' : '+';
  return `${Number(mantissa)}e${sign}${String(Math.abs(exponent)).padStart(2, '0')}`;
}

// Mirrors ratio_display.ratio_parts. The input remains the canonical signed quotient.
export function ratioParts(ratio, digits = 4, {signed = true} = {}) {
  const magnitude = Math.abs(ratio);
  const sign = signed ? (ratio < 0 ? '-' : '+') : '';
  if (magnitude > 0 && magnitude < 1) {
    const denominator = 1 / magnitude;
    if (Number.isFinite(denominator)) {
      const text = significantText(denominator, digits);
      return [sign + '1', ':' + (text === '1' ? significantText(denominator, 17) : text)];
    }
  }
  const text = significantText(magnitude, digits);
  return [sign + (magnitude > 1 && text === '1' ? significantText(magnitude, 17) : text), ':1'];
}
