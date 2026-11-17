// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Browser-only global UI choices, independent of project recovery and recents.
import {normalizeThemes,themeDefaults} from './themes.js';
import {normalizeShortcuts,MOUSE_PROFILES} from './controls.js';
export const PREFERENCES_KEY = 'ratiolab.web.preferences.v1';
export const DEFAULTS = Object.freeze({theme:'dark', language:'en', text_scale:1, hover_help:true,
  zoom_speed:1, rotation_speed:1, invert_zoom:false,mouse_navigation:'ratiolab',
  theme_customizations:themeDefaults(),keyboard_shortcuts:normalizeShortcuts(null),tooth_tip_steps:{},parameter_width:230,
  mcp_client_config:{command:'',workspace:''}});

export function normalizePreferences(data) {
  const result = structuredClone(DEFAULTS);
  if (!data || typeof data !== 'object' || Array.isArray(data)) return result;
  for (const [key,fallback] of Object.entries(DEFAULTS).filter(([key])=>!['mouse_navigation','theme_customizations','keyboard_shortcuts','tooth_tip_steps','parameter_width','mcp_client_config'].includes(key))) {
    const value = data[key];
    if (typeof fallback === 'string' ?
      typeof value === 'string' && (key === 'theme' ? ['dark','light'] : ['en','it','es','fr','de','pt','ru','zh-CN','ta']).includes(value) :
      typeof fallback === 'boolean' ? typeof value === 'boolean' :
      typeof value === 'number' && (key === 'text_scale' ? [1,1.25,1.5] : [.5,1,2]).includes(value)) result[key] = value;
  }
  if(typeof data.mouse_navigation==='string'&&Object.hasOwn(MOUSE_PROFILES,data.mouse_navigation))result.mouse_navigation=data.mouse_navigation;
  result.theme_customizations=normalizeThemes(data.theme_customizations);
  result.keyboard_shortcuts=normalizeShortcuts(data.keyboard_shortcuts);
  if (data.tooth_tip_steps && typeof data.tooth_tip_steps === 'object') {
    result.tooth_tip_steps=Object.fromEntries(Object.entries(data.tooth_tip_steps).filter(([key,value])=>
      /^[a-z]+:[a-z0-9_]+$/.test(key) && Number.isFinite(value) && value > 0));
  }
  if (Number.isFinite(data.parameter_width)) result.parameter_width=Math.round(Math.max(230,Math.min(580,data.parameter_width)));
  for (const key of Object.keys(result.mcp_client_config)) {
    const value = data.mcp_client_config?.[key];
    if (typeof value === 'string') result.mcp_client_config[key] = value;
  }
  return result;
}

function readData() {
  const data = JSON.parse(localStorage.getItem(PREFERENCES_KEY));
  return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
}
export function readPreferences() {
  try { return normalizePreferences(readData()); } catch { return structuredClone(DEFAULTS); }
}
export function savePreferences(preferences) {
  try {
    let previous = {};
    try { previous = readData(); } catch {}
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({...previous,...normalizePreferences(preferences)}));
    return true;
  } catch { return false; }
}
