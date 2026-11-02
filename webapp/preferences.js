// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Browser-only global UI choices, independent of project recovery and recents.
export const PREFERENCES_KEY = 'ratiolab.web.preferences.v1';
export const DEFAULTS = Object.freeze({theme:'dark', language:'en', text_scale:1, hover_help:true,
  zoom_speed:1, rotation_speed:1, invert_zoom:false});

export function normalizePreferences(data) {
  const result = {...DEFAULTS};
  if (!data || typeof data !== 'object' || Array.isArray(data)) return result;
  for (const [key,fallback] of Object.entries(DEFAULTS)) {
    const value = data[key];
    if (typeof fallback === 'string' ?
      typeof value === 'string' && (key === 'theme' ? ['dark','light'] : ['en','it','es','fr','de','pt','ru','zh-CN','ta']).includes(value) :
      typeof fallback === 'boolean' ? typeof value === 'boolean' :
      typeof value === 'number' && (key === 'text_scale' ? [1,1.25,1.5] : [.5,1,2]).includes(value)) result[key] = value;
  }
  return result;
}

function readData() {
  const data = JSON.parse(localStorage.getItem(PREFERENCES_KEY));
  return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
}
export function readPreferences() {
  try { return normalizePreferences(readData()); } catch { return {...DEFAULTS}; }
}
export function savePreferences(preferences) {
  try {
    let previous = {};
    try { previous = readData(); } catch {}
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({...previous,...normalizePreferences(preferences)}));
    return true;
  } catch { return false; }
}
