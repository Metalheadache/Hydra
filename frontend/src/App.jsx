import React, { useState, useEffect, useRef, useCallback } from 'react';

// ─── Mock streaming ──────────────────────────────────────────────────────────
const MOCK_RESPONSES = [
  "I'm Hydra, your multi-agent task orchestrator. I'll decompose your request into parallel sub-tasks and synthesize the results. What would you like me to work on?",
  "Great task! I'm spinning up multiple specialized agents to tackle this in parallel. Each agent will focus on a specific aspect, and I'll synthesize their outputs into a coherent result for you.",
  "I've analyzed your request and identified 3 parallel work streams. The Brain model is decomposing the task now. You can expect a comprehensive, multi-perspective response shortly.",
  "Interesting challenge! My agent swarm is on it. I'll coordinate their efforts and ensure quality scoring meets the threshold before delivering the final synthesis.",
];

async function* mockStream(text) {
  const words = text.split(' ');
  for (const word of words) {
    await new Promise(r => setTimeout(r, 50 + Math.random() * 80));
    yield word + ' ';
  }
}

// ─── Default settings ────────────────────────────────────────────────────────
const DEFAULT_SETTINGS = {
  apiBaseUrl: '',
  apiKey: '',
  model: 'anthropic/claude-sonnet-4-6',
  brainModel: 'anthropic/claude-sonnet-4-6',
  maxConcurrentAgents: 5,
  perAgentTimeout: 60,
  totalTaskTimeout: 300,
  temperature: 0.4,
  qualityScoreThreshold: 5.0,
  outputDirectory: './hydra_output',
};

const MODEL_OPTIONS = [
  'anthropic/claude-sonnet-4-6',
  'gpt-4o',
  'deepseek/deepseek-chat',
  'deepseek/deepseek-reasoner',
  'ollama/llama3',
];

// ─── Color tokens ─────────────────────────────────────────────────────────────
const tokens = (isDark) => ({
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
  panelBg: isDark ? 'rgba(15,20,25,0.85)' : 'rgba(255,255,255,0.7)',
  panelBorder: isDark ? 'rgba(192,192,192,0.15)' : 'rgba(255,255,255,0.8)',
  settingsBg: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.5)',
  settingsBorder: isDark ? 'rgba(192,192,192,0.2)' : 'rgba(255,255,255,0.6)',
  userBubbleBg: isDark ? 'rgba(0,37,201,0.15)' : 'rgba(0,37,201,0.1)',
  userBubbleBorder: isDark ? 'rgba(0,37,201,0.3)' : 'rgba(0,37,201,0.2)',
  assistantBubbleBg: isDark
    ? 'linear-gradient(180deg, rgba(200,220,255,0.05) 0%, rgba(255,255,255,0.02) 100%)'
    : 'linear-gradient(180deg, rgba(255,255,255,0.7) 0%, rgba(255,255,255,0.4) 100%)',
  inputBg: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.5)',
  sliderTrack: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
  divider: isDark
    ? 'linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0) 100%)'
    : 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.1) 50%, rgba(0,0,0,0) 100%)',
});

// ─── Inline SVG Icons ─────────────────────────────────────────────────────────
const GearIcon = ({ size = 20, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

const PaperclipIcon = ({ size = 18, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
  </svg>
);

const SendIcon = ({ size = 18, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

const StopIcon = ({ size = 18, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
  </svg>
);

const EyeIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const EyeOffIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
);

const XIcon = ({ size = 12, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const SunIcon = ({ size = 16, color = 'currentColor' }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="5" />
    <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
    <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
  </svg>
);

// ─── Slider component ──────────────────────────────────────────────────────────
const GlassSlider = ({ value, onChange, min, max, step, label, displayValue, t }) => {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: t.textSecondary, fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: 12, color: t.textPrimary, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{displayValue ?? value}</span>
      </div>
      <div style={{ position: 'relative', height: 6, borderRadius: 3, background: t.sliderTrack, cursor: 'pointer' }}>
        <div style={{
          position: 'absolute', left: 0, top: 0, height: '100%',
          width: `${pct}%`, borderRadius: 3,
          background: 'linear-gradient(90deg, #4a6de5, #0025C9)',
          boxShadow: '0 0 8px rgba(0,37,201,0.4)',
          transition: 'width 0.1s ease',
        }} />
        <input
          type="range" min={min} max={max} step={step ?? 1} value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="hydra-slider"
          style={{
            position: 'absolute', top: '50%', left: 0, transform: 'translateY(-50%)',
            width: '100%', height: '100%', opacity: 0, cursor: 'pointer', margin: 0, padding: 0,
          }}
        />
        {/* Thumb visual */}
        <div style={{
          position: 'absolute', top: '50%', left: `${pct}%`,
          transform: 'translate(-50%, -50%)',
          width: 14, height: 14, borderRadius: '50%',
          background: 'white',
          boxShadow: '0 0 8px rgba(0,37,201,0.5), 0 2px 4px rgba(0,0,0,0.3)',
          pointerEvents: 'none',
          transition: 'left 0.1s ease',
        }} />
      </div>
    </div>
  );
};

// ─── Settings Panel ────────────────────────────────────────────────────────────
const SettingsPanel = ({ open, settings, onSettingChange, isDark, onToggleDark, t }) => {
  const [showApiKey, setShowApiKey] = useState(false);
  const [modelInputFocused, setModelInputFocused] = useState(false);
  const [brainModelInputFocused, setBrainModelInputFocused] = useState(false);

  const inputStyle = (focused) => ({
    width: '100%', background: 'transparent', border: 'none', outline: 'none',
    color: t.textPrimary, fontSize: 13, fontFamily: 'inherit',
  });

  const fieldWrapStyle = (focused) => ({
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '8px 12px', borderRadius: 10, marginBottom: 8,
    background: focused
      ? (isDark ? 'rgba(0,37,201,0.08)' : 'rgba(0,37,201,0.05)')
      : t.inputBg,
    border: `1px solid ${focused ? 'rgba(160,230,255,0.5)' : (isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)')}`,
    backdropFilter: 'blur(10px)',
    transition: 'all 0.3s cubic-bezier(0.16,1,0.3,1)',
    boxShadow: focused ? '0 0 12px rgba(0,37,201,0.15)' : 'none',
  });

  const labelStyle = {
    fontSize: 11, color: t.textSecondary, fontWeight: 500,
    textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 4,
    display: 'block',
  };

  const sectionStyle = {
    marginBottom: 16,
    paddingBottom: 16,
    borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'}`,
  };

  const [apiUrlFocused, setApiUrlFocused] = useState(false);
  const [apiKeyFocused, setApiKeyFocused] = useState(false);
  const [outputDirFocused, setOutputDirFocused] = useState(false);

  return (
    <div style={{
      position: 'absolute', top: 'calc(100% + 12px)', left: 0,
      width: 360, maxHeight: '80vh', overflowY: 'auto',
      padding: '20px 16px',
      borderRadius: 20,
      background: t.panelBg,
      border: `1px solid ${t.panelBorder}`,
      backdropFilter: 'blur(40px)',
      WebkitBackdropFilter: 'blur(40px)',
      boxShadow: '0 0 40px rgba(0,0,0,0.8), 0 20px 60px rgba(0,0,0,0.6), inset 0 1px 1px rgba(255,255,255,0.08)',
      opacity: open ? 1 : 0,
      visibility: open ? 'visible' : 'hidden',
      transform: open ? 'translateY(0) scale(1)' : 'translateY(-10px) scale(0.95)',
      transformOrigin: 'top left',
      transition: 'all 0.4s cubic-bezier(0.16,1,0.3,1)',
      scrollbarWidth: 'none',
      zIndex: 999,
    }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: t.textPrimary, letterSpacing: '-0.3px' }}>Hydra Settings</span>
      </div>

      {/* API Config */}
      <div style={sectionStyle}>
        <span style={{ ...labelStyle, color: '#0025C9', marginBottom: 10 }}>API Configuration</span>

        <label style={labelStyle}>API Base URL</label>
        <div style={fieldWrapStyle(apiUrlFocused)}>
          <input
            type="text" value={settings.apiBaseUrl}
            placeholder="https://api.example.com/v1"
            onChange={e => onSettingChange('apiBaseUrl', e.target.value)}
            onFocus={() => setApiUrlFocused(true)}
            onBlur={() => setApiUrlFocused(false)}
            style={inputStyle(apiUrlFocused)}
          />
        </div>

        <label style={labelStyle}>API Key</label>
        <div style={fieldWrapStyle(apiKeyFocused)}>
          <input
            type={showApiKey ? 'text' : 'password'}
            value={settings.apiKey}
            placeholder="sk-ant-..."
            onChange={e => onSettingChange('apiKey', e.target.value)}
            onFocus={() => setApiKeyFocused(true)}
            onBlur={() => setApiKeyFocused(false)}
            style={{ ...inputStyle(apiKeyFocused), flex: 1 }}
          />
          <button onClick={() => setShowApiKey(p => !p)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.textSecondary, display: 'flex', alignItems: 'center', padding: 0 }}>
            {showApiKey ? <EyeOffIcon size={16} color={t.textSecondary} /> : <EyeIcon size={16} color={t.textSecondary} />}
          </button>
        </div>
      </div>

      {/* Model Config */}
      <div style={sectionStyle}>
        <span style={{ ...labelStyle, color: '#0025C9', marginBottom: 10 }}>Model</span>

        <label style={labelStyle}>Default Model</label>
        <div style={fieldWrapStyle(modelInputFocused)}>
          <input
            list="model-options" value={settings.model}
            onChange={e => onSettingChange('model', e.target.value)}
            onFocus={() => setModelInputFocused(true)}
            onBlur={() => setModelInputFocused(false)}
            style={inputStyle(modelInputFocused)}
          />
          <datalist id="model-options">
            {MODEL_OPTIONS.map(m => <option key={m} value={m} />)}
          </datalist>
        </div>

        <label style={labelStyle}>Brain Model</label>
        <div style={fieldWrapStyle(brainModelInputFocused)}>
          <input
            list="brain-model-options" value={settings.brainModel}
            onChange={e => onSettingChange('brainModel', e.target.value)}
            onFocus={() => setBrainModelInputFocused(true)}
            onBlur={() => setBrainModelInputFocused(false)}
            style={inputStyle(brainModelInputFocused)}
          />
          <datalist id="brain-model-options">
            {MODEL_OPTIONS.map(m => <option key={m} value={m} />)}
          </datalist>
        </div>

        <GlassSlider t={t} label="Temperature" value={settings.temperature}
          onChange={v => onSettingChange('temperature', v)} min={0} max={2} step={0.1}
          displayValue={settings.temperature.toFixed(1)} />
      </div>

      {/* Execution */}
      <div style={sectionStyle}>
        <span style={{ ...labelStyle, color: '#0025C9', marginBottom: 10 }}>Execution</span>
        <GlassSlider t={t} label="Max Concurrent Agents" value={settings.maxConcurrentAgents}
          onChange={v => onSettingChange('maxConcurrentAgents', v)} min={1} max={10} />
        <GlassSlider t={t} label="Per Agent Timeout (s)" value={settings.perAgentTimeout}
          onChange={v => onSettingChange('perAgentTimeout', v)} min={10} max={300} />
        <GlassSlider t={t} label="Total Task Timeout (s)" value={settings.totalTaskTimeout}
          onChange={v => onSettingChange('totalTaskTimeout', v)} min={60} max={600} />
      </div>

      {/* Quality */}
      <div style={sectionStyle}>
        <span style={{ ...labelStyle, color: '#0025C9', marginBottom: 10 }}>Quality</span>
        <GlassSlider t={t} label="Quality Score Threshold" value={settings.qualityScoreThreshold}
          onChange={v => onSettingChange('qualityScoreThreshold', v)} min={1} max={10} step={0.5}
          displayValue={settings.qualityScoreThreshold.toFixed(1)} />
      </div>

      {/* Output */}
      <div style={sectionStyle}>
        <span style={{ ...labelStyle, color: '#0025C9', marginBottom: 10 }}>Output</span>
        <label style={labelStyle}>Output Directory</label>
        <div style={fieldWrapStyle(outputDirFocused)}>
          <input type="text" value={settings.outputDirectory}
            placeholder="./hydra_output"
            onChange={e => onSettingChange('outputDirectory', e.target.value)}
            onFocus={() => setOutputDirFocused(true)}
            onBlur={() => setOutputDirFocused(false)}
            style={inputStyle(outputDirFocused)}
          />
        </div>
      </div>

      {/* Dark Mode Toggle */}
      <div onClick={onToggleDark} style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
        borderRadius: 14, cursor: 'pointer',
        background: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.04)',
        border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'}`,
        transition: 'all 0.3s ease',
      }}
        onMouseEnter={e => {
          e.currentTarget.style.background = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.07)';
          e.currentTarget.style.borderColor = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)';
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.04)';
          e.currentTarget.style.borderColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
        }}
      >
        <SunIcon size={16} color={t.textSecondary} />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: t.textPrimary }}>Dark Mode</span>
        {/* Toggle */}
        <div style={{
          width: 44, height: 24, borderRadius: 12, position: 'relative',
          background: isDark ? 'rgba(0,37,201,0.25)' : 'rgba(0,0,0,0.12)',
          border: `1px solid ${isDark ? '#0025C9' : 'rgba(0,0,0,0.12)'}`,
          transition: 'all 0.3s ease',
          flexShrink: 0,
        }}>
          <div style={{
            position: 'absolute', top: 3,
            left: isDark ? 'calc(100% - 19px)' : 3,
            width: 16, height: 16, borderRadius: '50%',
            background: isDark ? '#4a7aff' : '#94a3b8',
            boxShadow: isDark ? '0 0 10px rgba(0,37,201,0.6)' : 'none',
            transition: 'all 0.3s cubic-bezier(0.16,1,0.3,1)',
          }} />
        </div>
      </div>
    </div>
  );
};

// ─── File chip ─────────────────────────────────────────────────────────────────
const FileChip = ({ file, onRemove, t }) => (
  <div style={{
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '3px 10px 3px 8px', borderRadius: 999,
    background: t.glassBgBase,
    backdropFilter: 'blur(10px)',
    border: `1px solid ${t.glassBorder}`,
    fontSize: 12, color: t.textSecondary,
    maxWidth: 180,
    flexShrink: 0,
  }}>
    <PaperclipIcon size={11} color={t.textSecondary} />
    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 120 }}>{file.name}</span>
    <button onClick={onRemove} style={{
      background: 'none', border: 'none', cursor: 'pointer',
      color: t.textSecondary, display: 'flex', alignItems: 'center', padding: 0,
      flexShrink: 0,
    }}>
      <XIcon size={11} color={t.textSecondary} />
    </button>
  </div>
);

// ─── Message Bubble ────────────────────────────────────────────────────────────
const MessageBubble = ({ msg, isStreaming, t, idx }) => {
  const isUser = msg.role === 'user';
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), idx * 50);
    return () => clearTimeout(timer);
  }, [idx]);

  return (
    <div style={{
      display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start',
      marginBottom: 12, padding: '0 8px',
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0)' : 'translateY(16px)',
      transition: 'opacity 0.4s cubic-bezier(0.16,1,0.3,1), transform 0.4s cubic-bezier(0.16,1,0.3,1)',
    }}>
      <div style={{
        maxWidth: 'clamp(240px, 70%, 560px)',
        padding: '12px 16px',
        borderRadius: isUser ? '20px 20px 4px 20px' : '20px 20px 20px 4px',
        background: isUser ? t.userBubbleBg : t.assistantBubbleBg,
        border: `1px solid ${isUser ? t.userBubbleBorder : t.glassBorder}`,
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        boxShadow: isUser
          ? '0 0 20px rgba(0,37,201,0.15), inset 0 1px 1px rgba(255,255,255,0.08)'
          : 'inset 0 1px 1px rgba(255,255,255,0.06), 0 4px 20px rgba(0,0,0,0.15)',
        fontSize: 15, color: t.textPrimary, lineHeight: 1.6,
        wordBreak: 'break-word', whiteSpace: 'pre-wrap',
      }}>
        {msg.content}
        {isStreaming && !isUser && (
          <span style={{
            display: 'inline-block', width: 2, height: 14, background: '#4a6de5',
            marginLeft: 2, borderRadius: 1, verticalAlign: 'text-bottom',
            animation: 'hydra-cursor-blink 0.8s ease-in-out infinite',
          }} />
        )}
        {/* File attachments */}
        {msg.files && msg.files.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
            {msg.files.map((f, i) => (
              <span key={i} style={{
                fontSize: 11, padding: '2px 8px', borderRadius: 999,
                background: 'rgba(0,37,201,0.1)', border: '1px solid rgba(0,37,201,0.2)',
                color: '#4a6de5',
              }}>📎 {f.name}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Input Bar (shared between IDLE and CHAT_ACTIVE) ──────────────────────────
const InputBar = ({
  value, onChange, onSend, onStop,
  isStreaming, files, onFilesChange, onRemoveFile,
  focused, onFocus, onBlur,
  t, isDark, placeholder,
  extraStyle,
}) => {
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const [hoveredSend, setHoveredSend] = useState(false);
  const [hoveredClip, setHoveredClip] = useState(false);

  // auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [value]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !isStreaming) onSend();
    }
  };

  const canSend = value.trim().length > 0 && !isStreaming;

  const containerStyle = {
    display: 'flex', flexDirection: 'column',
    borderRadius: 999,
    background: focused ? t.glassBgFocus : t.glassBgBase,
    backdropFilter: 'blur(24px)',
    WebkitBackdropFilter: 'blur(24px)',
    border: `1px solid ${focused ? t.glassBorderFocus : t.glassBorder}`,
    boxShadow: focused
      ? `0 0 24px rgba(0,37,201,0.3), inset 0 0 5px rgba(255,255,255,0.05), 0 10px 40px rgba(0,0,0,0.3)`
      : `inset 0 1px 1px rgba(255,255,255,0.1), 0 0 20px rgba(0,0,0,0.3)`,
    transition: 'all 0.4s cubic-bezier(0.16,1,0.3,1)',
    overflow: 'hidden',
    ...extraStyle,
  };

  return (
    <div style={containerStyle}>
      <div style={{ display: 'flex', alignItems: 'center', padding: '0 8px', minHeight: 52 }}>
        {/* Paperclip */}
        <button aria-label="Attach files"
          onClick={() => fileInputRef.current?.click()}
          onMouseEnter={() => setHoveredClip(true)}
          onMouseLeave={() => setHoveredClip(false)}
          style={{
            width: 36, height: 36, borderRadius: '50%', border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: hoveredClip ? '#4a6de5' : t.textSecondary,
            background: hoveredClip ? 'rgba(74,109,229,0.12)' : 'transparent',
            transition: 'all 0.2s ease', flexShrink: 0,
          }}>
          <PaperclipIcon size={18} color="currentColor" />
        </button>
        <input ref={fileInputRef} type="file" multiple hidden onChange={e => {
          const newFiles = Array.from(e.target.files).map(f => ({ name: f.name, size: f.size, file: f }));
          onFilesChange(prev => [...prev, ...newFiles]);
          e.target.value = '';
        }} />

        {/* Divider */}
        <div style={{ width: 1, height: 20, background: t.divider, margin: '0 4px', flexShrink: 0 }} />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={onFocus}
          onBlur={onBlur}
          placeholder={placeholder}
          rows={1}
          className="hydra-textarea"
          style={{
            flex: 1, background: 'transparent', border: 'none', outline: 'none',
            resize: 'none', padding: '0 12px', color: t.textPrimary,
            fontSize: 15, fontFamily: 'inherit', lineHeight: 1.5,
            maxHeight: 120, overflowY: 'auto', alignSelf: 'center',
          }}
        />

        {/* Divider */}
        <div style={{ width: 1, height: 20, background: t.divider, margin: '0 4px', flexShrink: 0 }} />

        {/* Send / Stop button */}
        <div style={{ position: 'relative', width: 36, height: 36, flexShrink: 0 }}>
          {/* Send */}
          <button aria-label="Send"
            onClick={onSend}
            onMouseEnter={() => setHoveredSend(true)}
            onMouseLeave={() => setHoveredSend(false)}
            disabled={!canSend}
            style={{
              position: 'absolute', inset: 0,
              borderRadius: '50%', border: 'none', cursor: canSend ? 'pointer' : 'default',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: canSend
                ? (hoveredSend ? 'rgba(0,37,201,0.85)' : 'rgba(0,37,201,0.7)')
                : 'transparent',
              color: canSend ? 'white' : t.textSecondary,
              boxShadow: canSend && hoveredSend ? '0 0 20px rgba(0,37,201,0.5)' : 'none',
              opacity: isStreaming ? 0 : 1,
              transform: isStreaming ? 'scale(0.7)' : 'scale(1)',
              transition: 'all 0.2s cubic-bezier(0.16,1,0.3,1)',
            }}>
            <SendIcon size={16} color="currentColor" />
          </button>

          {/* Stop */}
          <button aria-label="Stop"
            onClick={onStop}
            style={{
              position: 'absolute', inset: 0,
              borderRadius: '50%', border: 'none', cursor: isStreaming ? 'pointer' : 'default',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(239,68,68,0.15)',
              color: '#ef4444',
              boxShadow: isStreaming ? '0 0 20px rgba(239,68,68,0.3)' : 'none',
              opacity: isStreaming ? 1 : 0,
              transform: isStreaming ? 'scale(1)' : 'scale(0.7)',
              transition: 'all 0.2s cubic-bezier(0.16,1,0.3,1)',
              pointerEvents: isStreaming ? 'auto' : 'none',
            }}>
            <StopIcon size={16} color="currentColor" />
          </button>
        </div>
      </div>

      {/* File chips */}
      {files.length > 0 && (
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: 6,
          padding: '0 12px 10px 12px',
        }}>
          {files.map((f, i) => (
            <FileChip key={i} file={f} t={t} onRemove={() => onRemoveFile(i)} />
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  // Theme
  const [isDark, setIsDark] = useState(() => {
    try { return JSON.parse(localStorage.getItem('hydra_dark') ?? 'true'); }
    catch { return true; }
  });

  // Settings
  const [settings, setSettings] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('hydra_settings') ?? '{}');
      return { ...DEFAULT_SETTINGS, ...saved };
    } catch { return { ...DEFAULT_SETTINGS }; }
  });

  // UI state
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [appState, setAppState] = useState('IDLE'); // IDLE | ANIMATING | CHAT_ACTIVE
  const [inputFocused, setInputFocused] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [files, setFiles] = useState([]);

  // Chat state
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef(null);
  const messagesEndRef = useRef(null);
  const settingsPanelRef = useRef(null);
  const settingsBtnRef = useRef(null);
  const chatInputRef = useRef(null);

  // Animation state
  const [morphRect, setMorphRect] = useState(null);
  const [morphText, setMorphText] = useState('');
  const [morphPhase, setMorphPhase] = useState(0); // 0=idle, 1=moving, 2=done
  const morphRef = useRef(null);
  const initialBarRef = useRef(null);

  const t = tokens(isDark);

  // Persist settings
  useEffect(() => {
    localStorage.setItem('hydra_settings', JSON.stringify(settings));
  }, [settings]);
  useEffect(() => {
    localStorage.setItem('hydra_dark', JSON.stringify(isDark));
  }, [isDark]);

  // Inject styles
  useEffect(() => {
    const style = document.createElement('style');
    style.id = 'hydra-styles';
    style.textContent = `
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
      html, body, #root { height: 100%; }
      body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        -webkit-font-smoothing: antialiased;
        overflow: hidden;
      }
      .hydra-textarea::placeholder { color: #4a7aff; opacity: 0.8; }
      .hydra-textarea:focus::placeholder { color: #0025C9; opacity: 0.7; }
      .hydra-textarea { scrollbar-width: none; }
      .hydra-textarea::-webkit-scrollbar { display: none; }
      .hydra-slider { -webkit-appearance: none; appearance: none; background: transparent; }
      .hydra-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 0; height: 0; }
      .hydra-slider::-moz-range-thumb { width: 0; height: 0; opacity: 0; }

      .hydra-panel::-webkit-scrollbar { width: 4px; }
      .hydra-panel::-webkit-scrollbar-track { background: transparent; }
      .hydra-panel::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

      .hydra-messages::-webkit-scrollbar { width: 4px; }
      .hydra-messages::-webkit-scrollbar-track { background: transparent; }
      .hydra-messages::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

      @keyframes hydra-cursor-blink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0; }
      }

      @keyframes hydra-morph-phase1 {
        from { opacity: 1; }
        to { opacity: 0.9; }
      }

      @media (max-width: 640px) {
        .hydra-idle-bar { width: 90vw !important; }
        .hydra-chat-input-wrap { padding: 12px !important; }
        .hydra-messages { padding: 12px !important; }
        .hydra-settings-panel { width: 100vw !important; left: -24px !important; }
      }
    `;
    document.head.appendChild(style);
    return () => document.getElementById('hydra-styles')?.remove();
  }, []);

  // Click outside to close settings
  useEffect(() => {
    const handler = (e) => {
      if (
        settingsPanelRef.current && !settingsPanelRef.current.contains(e.target) &&
        settingsBtnRef.current && !settingsBtnRef.current.contains(e.target)
      ) setSettingsOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Escape to close settings
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') setSettingsOpen(false); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  // Auto-scroll
  useEffect(() => {
    if (isStreaming || messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isStreaming]);

  const handleSettingChange = useCallback((key, val) => {
    setSettings(prev => ({ ...prev, [key]: val }));
  }, []);

  // ── SSE Streaming handler ──────────────────────────────────────────────────
  const streamResponse = useCallback(async (userMsg, history) => {
    setIsStreaming(true);
    abortRef.current = new AbortController();
    const assistantIdx = history.length + 1; // after user msg

    const appendMsg = (idx, chunk) => {
      setMessages(prev => {
        const copy = [...prev];
        if (copy[idx]) {
          copy[idx] = { ...copy[idx], content: copy[idx].content + chunk };
        }
        return copy;
      });
    };

    // Add empty assistant placeholder
    setMessages(prev => [
      ...prev,
      { role: 'assistant', content: '', id: Date.now() + 1 }
    ]);

    try {
      if (!settings.apiBaseUrl) {
        // Mock stream
        const response = MOCK_RESPONSES[Math.floor(Math.random() * MOCK_RESPONSES.length)];
        for await (const chunk of mockStream(response)) {
          if (abortRef.current?.signal.aborted) break;
          setMessages(prev => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'assistant') {
              copy[copy.length - 1] = { ...last, content: last.content + chunk };
            }
            return copy;
          });
        }
      } else {
        // Real SSE
        const allMessages = [
          ...history.map(m => ({ role: m.role, content: m.content })),
          { role: 'user', content: userMsg },
        ];
        const res = await fetch(`${settings.apiBaseUrl}/chat/completions`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${settings.apiKey}`,
          },
          signal: abortRef.current.signal,
          body: JSON.stringify({
            model: settings.model,
            messages: allMessages,
            temperature: settings.temperature,
            stream: true,
          }),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';
          for (const line of lines) {
            if (!line.startsWith('data:')) continue;
            const data = line.slice(5).trim();
            if (data === '[DONE]') break;
            try {
              const json = JSON.parse(data);
              const chunk = json.choices?.[0]?.delta?.content ?? '';
              if (chunk) {
                setMessages(prev => {
                  const copy = [...prev];
                  const last = copy[copy.length - 1];
                  if (last?.role === 'assistant') {
                    copy[copy.length - 1] = { ...last, content: last.content + chunk };
                  }
                  return copy;
                });
              }
            } catch { /* skip */ }
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        setMessages(prev => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last?.role === 'assistant') {
            copy[copy.length - 1] = { ...last, content: last.content + ' [Stopped]' };
          }
          return copy;
        });
      } else {
        setMessages(prev => [
          ...prev,
          { role: 'system', content: `Error: ${err.message}`, id: Date.now() + 2 }
        ]);
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }, [settings]);

  // ── Send message ─────────────────────────────────────────────────────────────
  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text || isStreaming) return;
    setInputValue('');

    if (appState === 'IDLE') {
      // Begin fold animation
      const barEl = initialBarRef.current;
      if (barEl) {
        const rect = barEl.getBoundingClientRect();
        setMorphRect(rect);
        setMorphText(text);
        setMorphPhase(1);
        setAppState('ANIMATING');

        const userMsg = { role: 'user', content: text, files, id: Date.now() };
        const currentHistory = [];
        setFiles([]);

        // After animation, transition to chat
        setTimeout(() => {
          setMorphPhase(2);
          setTimeout(() => {
            setAppState('CHAT_ACTIVE');
            setMessages([userMsg]);
            setMorphPhase(0);
            setMorphRect(null);
            // Start streaming after state settles
            setTimeout(() => streamResponse(text, currentHistory), 50);
          }, 350);
        }, 500);
      }
    } else {
      // In chat, just add message
      const userMsg = { role: 'user', content: text, files, id: Date.now() };
      setFiles([]);
      const newHistory = [...messages, userMsg];
      setMessages(newHistory);
      streamResponse(text, messages);
    }
  }, [inputValue, isStreaming, appState, files, messages, streamResponse]);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // ── Morph overlay (ANIMATING state) ──────────────────────────────────────────
  const MorphOverlay = () => {
    if (!morphRect || morphPhase === 0) return null;

    // Target: upper-right area, compact bubble
    const targetTop = 24;
    const targetRight = 24;
    const targetWidth = Math.min(360, window.innerWidth * 0.6);
    const targetLeft = window.innerWidth - targetRight - targetWidth;

    const style = {
      position: 'fixed',
      top: morphPhase === 1 ? morphRect.top : targetTop,
      left: morphPhase === 1 ? morphRect.left : targetLeft,
      width: morphPhase === 1 ? morphRect.width : targetWidth,
      height: morphPhase === 1 ? morphRect.height : 'auto',
      borderRadius: morphPhase === 1 ? 999 : '20px 20px 4px 20px',
      background: morphPhase === 1 ? t.glassBgBase : t.userBubbleBg,
      backdropFilter: 'blur(24px)',
      WebkitBackdropFilter: 'blur(24px)',
      border: `1px solid ${morphPhase === 1 ? t.glassBorder : t.userBubbleBorder}`,
      boxShadow: morphPhase === 1
        ? 'inset 0 1px 1px rgba(255,255,255,0.1), 0 0 20px rgba(0,0,0,0.4)'
        : '0 0 20px rgba(0,37,201,0.2)',
      zIndex: 2000,
      padding: '14px 18px',
      display: 'flex', alignItems: 'center',
      fontSize: 15, color: t.textPrimary, lineHeight: 1.5,
      overflow: 'hidden',
      transition: 'all 0.8s cubic-bezier(0.16,1,0.3,1)',
      opacity: morphPhase === 2 ? 0 : 1,
    };

    return (
      <div style={style}>
        <span style={{ opacity: morphPhase === 1 ? 0.7 : 1, transition: 'opacity 0.3s ease' }}>
          {morphText}
        </span>
      </div>
    );
  };

  // ── Render ────────────────────────────────────────────────────────────────────
  const [hoveredSettingsBtn, setHoveredSettingsBtn] = useState(false);

  return (
    <div style={{
      height: '100vh', width: '100vw',
      backgroundColor: t.bgColor,
      backgroundImage: t.bgGradient,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
      WebkitFontSmoothing: 'antialiased',
      position: 'relative',
      overflow: 'hidden',
      transition: 'background-color 0.4s ease',
    }}>

      {/* ── Settings Button (always visible) ── */}
      <div style={{ position: 'fixed', top: 24, left: 24, zIndex: 1001 }}>
        <button
          ref={settingsBtnRef}
          onClick={e => { e.stopPropagation(); setSettingsOpen(p => !p); }}
          onMouseEnter={() => setHoveredSettingsBtn(true)}
          onMouseLeave={() => setHoveredSettingsBtn(false)}
          aria-label="Settings"
          style={{
            width: 44, height: 44, borderRadius: '50%', cursor: 'pointer',
            background: settingsOpen ? 'rgba(0,37,201,0.15)' : hoveredSettingsBtn ? 'rgba(255,255,255,0.08)' : t.settingsBg,
            border: `1px solid ${settingsOpen ? '#0025C9' : hoveredSettingsBtn ? 'rgba(0,37,201,0.5)' : t.settingsBorder}`,
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            boxShadow: settingsOpen
              ? '0 0 25px rgba(0,37,201,0.35), inset 0 0 8px rgba(0,37,201,0.15)'
              : hoveredSettingsBtn ? '0 0 20px rgba(0,37,201,0.25)' : 'inset 0 1px 1px rgba(255,255,255,0.05)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: settingsOpen ? '#0025C9' : hoveredSettingsBtn ? t.textPrimary : t.textSecondary,
            transform: hoveredSettingsBtn ? 'scale(1.05)' : 'scale(1)',
            transition: 'all 0.3s cubic-bezier(0.16,1,0.3,1)',
          }}>
          <GearIcon size={20} />
        </button>

        {/* Settings Panel */}
        <div ref={settingsPanelRef} className="hydra-settings-panel">
          <SettingsPanel
            open={settingsOpen}
            settings={settings}
            onSettingChange={handleSettingChange}
            isDark={isDark}
            onToggleDark={() => setIsDark(p => !p)}
            t={t}
          />
        </div>
      </div>

      {/* ── Morph Animation Overlay ── */}
      <MorphOverlay />

      {/* ── IDLE STATE ── */}
      {(appState === 'IDLE' || appState === 'ANIMATING') && (
        <div style={{
          position: 'fixed', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          padding: '0 24px',
          opacity: appState === 'ANIMATING' ? 0 : 1,
          transition: 'opacity 0.3s ease',
          pointerEvents: appState === 'ANIMATING' ? 'none' : 'auto',
          gap: 12,
        }}>
          {/* Tagline */}
          <div style={{
            textAlign: 'center', marginBottom: 12,
            opacity: inputFocused ? 0.4 : 1,
            transition: 'opacity 0.3s ease',
          }}>
            <div style={{
              fontSize: 13, color: t.textSecondary, letterSpacing: '0.1em',
              textTransform: 'uppercase', fontWeight: 500, marginBottom: 6,
            }}>HYDRA</div>
            <div style={{ fontSize: 13, color: t.textSecondary, opacity: 0.6 }}>
              Multi-agent task orchestration
            </div>
          </div>

          {/* Input bar */}
          <div
            ref={initialBarRef}
            className="hydra-idle-bar"
            style={{
              width: inputFocused ? 560 : 480,
              maxWidth: '90vw',
              transition: 'width 0.4s cubic-bezier(0.16,1,0.3,1)',
            }}>
            <InputBar
              value={inputValue}
              onChange={setInputValue}
              onSend={handleSend}
              onStop={handleStop}
              isStreaming={isStreaming}
              files={files}
              onFilesChange={setFiles}
              onRemoveFile={i => setFiles(prev => prev.filter((_, idx) => idx !== i))}
              focused={inputFocused}
              onFocus={() => setInputFocused(true)}
              onBlur={() => setInputFocused(false)}
              t={t}
              isDark={isDark}
              placeholder="Describe your task..."
            />
          </div>
        </div>
      )}

      {/* ── CHAT_ACTIVE STATE ── */}
      {appState === 'CHAT_ACTIVE' && (
        <div style={{
          position: 'fixed', inset: 0,
          display: 'flex', flexDirection: 'column',
        }}>
          {/* Messages area */}
          <div
            className="hydra-messages"
            style={{
              flex: 1, overflowY: 'auto',
              padding: '80px 16px 16px 16px',
              display: 'flex', flexDirection: 'column',
            }}>
            {messages.map((msg, idx) => (
              msg.role === 'system'
                ? (
                  <div key={msg.id ?? idx} style={{
                    textAlign: 'center', margin: '8px 0',
                    fontSize: 13, color: '#ef4444', opacity: 0.8,
                    padding: '6px 12px', borderRadius: 8,
                    background: 'rgba(239,68,68,0.08)', display: 'inline-block', alignSelf: 'center',
                  }}>
                    {msg.content}
                  </div>
                )
                : (
                  <MessageBubble
                    key={msg.id ?? idx}
                    msg={msg}
                    isStreaming={isStreaming && idx === messages.length - 1}
                    t={t}
                    idx={idx}
                  />
                )
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Bottom Input */}
          <div className="hydra-chat-input-wrap" style={{
            padding: '12px 24px 20px 24px',
            display: 'flex', justifyContent: 'center',
          }}>
            <div style={{ width: '100%', maxWidth: 720 }}>
              <InputBar
                ref={chatInputRef}
                value={inputValue}
                onChange={setInputValue}
                onSend={handleSend}
                onStop={handleStop}
                isStreaming={isStreaming}
                files={files}
                onFilesChange={setFiles}
                onRemoveFile={i => setFiles(prev => prev.filter((_, idx) => idx !== i))}
                focused={inputFocused}
                onFocus={() => setInputFocused(true)}
                onBlur={() => setInputFocused(false)}
                t={t}
                isDark={isDark}
                placeholder="Continue the conversation..."
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
