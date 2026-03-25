// Shared design tokens and SVG icons for Hydra UI
import React from 'react';

export const tokens = (isDark) => ({
  bgColor: isDark ? '#05070a' : '#f0f4f8',
  bgGradient: isDark
    ? 'radial-gradient(circle at 20% 20%, rgba(0,37,201,0.1) 0%, transparent 40%), radial-gradient(circle at 80% 80%, rgba(74,109,229,0.06) 0%, transparent 40%)'
    : 'radial-gradient(circle at 15% 20%, rgba(0,37,201,0.15) 0%, transparent 45%), radial-gradient(circle at 85% 75%, rgba(26,71,255,0.1) 0%, transparent 40%), radial-gradient(circle at 50% 50%, rgba(255,255,255,0.5) 0%, transparent 70%)',
  glassBgBase: isDark
    ? 'linear-gradient(180deg, rgba(200,220,255,0.05) 0%, rgba(255,255,255,0.02) 100%)'
    : 'linear-gradient(180deg, rgba(255,255,255,0.7) 0%, rgba(255,255,255,0.4) 100%)',
  glassBgFocus: isDark
    ? 'linear-gradient(180deg, rgba(160,210,255,0.08) 0%, rgba(255,255,255,0.04) 100%)'
    : 'linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(255,255,255,0.6) 100%)',
  glassBorder: isDark ? 'rgba(192,192,192,0.2)' : 'rgba(255,255,255,0.6)',
  glassBorderFocus: 'rgba(160,230,255,0.6)',
  glassHighlight: 'inset 0 1px 1px rgba(255,255,255,0.1)',
  glassShadow: 'inset 0 1px 1px rgba(255,255,255,0.1), 0 0 20px rgba(0,0,0,0.4)',
  neonGlow: '0 0 20px rgba(0,37,201,0.35), inset 0 0 5px rgba(255,255,255,0.05)',
  textPrimary: isDark ? '#f0f2f5' : '#0f172a',
  textSecondary: isDark ? '#94a3b8' : '#64748b',
  accentPrimary: '#0025C9',
  accentHover: '#4a6de5',
  panelBg: isDark ? 'rgba(15,20,25,0.92)' : 'rgba(255,255,255,0.85)',
  panelBorder: isDark ? 'rgba(192,192,192,0.15)' : 'rgba(255,255,255,0.8)',
  settingsBg: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.5)',
  settingsBorder: isDark ? 'rgba(192,192,192,0.2)' : 'rgba(255,255,255,0.6)',
  cardBg: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.7)',
  cardBorder: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.8)',
  inputBg: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.5)',
  sliderTrack: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
  divider: isDark
    ? 'linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0) 100%)'
    : 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.1) 50%, rgba(0,0,0,0) 100%)',
  userBubbleBg: isDark ? 'rgba(0,37,201,0.15)' : 'rgba(0,37,201,0.1)',
  userBubbleBorder: isDark ? 'rgba(0,37,201,0.3)' : 'rgba(0,37,201,0.2)',
});

// ── Icons ──────────────────────────────────────────────────────────────────────

export const GearIcon = ({ size = 20, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

export const ClockIcon = ({ size = 20, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

export const PaperclipIcon = ({ size = 18, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
  </svg>
);

export const SendIcon = ({ size = 18, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

export const StopIcon = ({ size = 18, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
  </svg>
);

export const EyeIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

export const EyeOffIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
);

export const XIcon = ({ size = 12, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

export const SunIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="5" />
    <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
    <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
  </svg>
);

export const MoonIcon = ({ size = 20, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="1.5" fill="none">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

export const TrashIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
);

export const ChevronDownIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

export const ChevronUpIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="18 15 12 9 6 15" />
  </svg>
);

export const CopyIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
);

export const DownloadIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

export const NewChatIcon = ({ size = 20, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7" />
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
  </svg>
);

// ── Role emoji mapping ──────────────────────────────────────────────────────────

export function getRoleEmoji(role) {
  if (!role) return '🤖';
  const r = role.toLowerCase();
  if (r.includes('research')) return '🔍';
  if (r.includes('analys') || r.includes('analyst')) return '📊';
  if (r.includes('writ') || r.includes('editor')) return '✍️';
  if (r.includes('synth') || r.includes('strategy') || r.includes('brain')) return '🧠';
  if (r.includes('code') || r.includes('develop') || r.includes('engineer')) return '💻';
  if (r.includes('design') || r.includes('ui') || r.includes('ux')) return '🎨';
  if (r.includes('data') || r.includes('stat')) return '📈';
  if (r.includes('search') || r.includes('web')) return '🌐';
  if (r.includes('secur') || r.includes('audit')) return '🔒';
  return '🤖';
}

// ── Format helpers ─────────────────────────────────────────────────────────────

export function formatElapsed(ms) {
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  return `${m}m ${rs}s`;
}

export function formatTokens(n) {
  if (!n) return '0';
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function formatCost(tokens) {
  if (!tokens) return '$0.00';
  // Rough estimate: ~$3 per 1M tokens (claude-sonnet average input+output)
  const cost = (tokens / 1000000) * 3;
  if (cost < 0.01) return `$${(cost * 100).toFixed(2)}¢`;
  return `$${cost.toFixed(3)}`;
}

export function timeAgo(isoOrUnix) {
  const ts = typeof isoOrUnix === 'number'
    ? isoOrUnix * 1000
    : new Date(isoOrUnix).getTime();
  const diff = Date.now() - ts;
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}
