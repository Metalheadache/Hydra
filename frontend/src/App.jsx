import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import OrchestrationView from './OrchestrationView.jsx';
import ResultView from './ResultView.jsx';
import HistoryPage from './HistoryPage.jsx';
import { mockOrchestration } from './mockOrchestration.js';
import { useWebSocket, uploadFiles, fetchHistory, fetchHistoryRun, normalizeError } from './useWebSocket.js';
import {
  tokens,
  GearIcon, ClockIcon, PaperclipIcon, SendIcon, StopIcon,
  EyeIcon, EyeOffIcon, XIcon, SunIcon, MoonIcon, NewChatIcon,
} from './tokens.jsx';

// ─── Default settings ────────────────────────────────────────────────────────
const DEFAULT_SETTINGS = {
  apiBaseUrl: '',
  serverToken: '',
  apiKey: '',
  model: 'anthropic/claude-sonnet-4-6',
  brainModel: 'anthropic/claude-sonnet-4-6',
  postBrainModel: 'anthropic/claude-sonnet-4-6',
  maxConcurrentAgents: 5,
  perAgentTimeout: 60,
  totalTaskTimeout: 600,
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
  'gemini/gemini-2.5-flash',
];

// ─── GlassSlider ──────────────────────────────────────────────────────────────
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

// ─── SettingsPanel ────────────────────────────────────────────────────────────
const SettingsPanel = ({ open, settings, onSettingChange, isDark, onToggleDark, t }) => {
  const [showApiKey, setShowApiKey] = useState(false);
  const [modelInputFocused, setModelInputFocused] = useState(false);
  const [brainModelInputFocused, setBrainModelInputFocused] = useState(false);
  const [hoveredDarkToggle, setHoveredDarkToggle] = useState(false);
  const [apiUrlFocused, setApiUrlFocused] = useState(false);
  const [apiKeyFocused, setApiKeyFocused] = useState(false);
  const [serverTokenFocused, setServerTokenFocused] = useState(false);
  const [outputDirFocused, setOutputDirFocused] = useState(false);
  const [showServerToken, setShowServerToken] = useState(false);

  const inputStyle = () => ({
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
    marginBottom: 16, paddingBottom: 16,
    borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'}`,
  };

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
            placeholder="http://localhost:8000"
            onChange={e => onSettingChange('apiBaseUrl', e.target.value)}
            onFocus={() => setApiUrlFocused(true)}
            onBlur={() => setApiUrlFocused(false)}
            style={inputStyle()}
          />
        </div>

        <label style={labelStyle}>Server Token (optional)</label>
        <div style={fieldWrapStyle(serverTokenFocused)}>
          <input
            type={showServerToken ? 'text' : 'password'}
            value={settings.serverToken}
            placeholder="HYDRA_SERVER_TOKEN value"
            onChange={e => onSettingChange('serverToken', e.target.value)}
            onFocus={() => setServerTokenFocused(true)}
            onBlur={() => setServerTokenFocused(false)}
            style={{ ...inputStyle(), flex: 1 }}
          />
          <button onClick={() => setShowServerToken(p => !p)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.textSecondary, display: 'flex', alignItems: 'center', padding: 0 }}>
            {showServerToken ? <EyeOffIcon size={16} color={t.textSecondary} /> : <EyeIcon size={16} color={t.textSecondary} />}
          </button>
        </div>

        <label style={labelStyle}>LLM API Key</label>
        <div style={fieldWrapStyle(apiKeyFocused)}>
          <input
            type={showApiKey ? 'text' : 'password'}
            value={settings.apiKey}
            placeholder="sk-ant-..."
            onChange={e => onSettingChange('apiKey', e.target.value)}
            onFocus={() => setApiKeyFocused(true)}
            onBlur={() => setApiKeyFocused(false)}
            style={{ ...inputStyle(), flex: 1 }}
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
            style={inputStyle()}
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
            style={inputStyle()}
          />
          <datalist id="brain-model-options">
            {MODEL_OPTIONS.map(m => <option key={m} value={m} />)}
          </datalist>
        </div>

        <label style={labelStyle}>Synthesis Model</label>
        <div style={fieldWrapStyle(false)}>
          <input
            list="post-brain-model-options" value={settings.postBrainModel}
            onChange={e => onSettingChange('postBrainModel', e.target.value)}
            style={inputStyle()}
          />
          <datalist id="post-brain-model-options">
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
          onChange={v => onSettingChange('totalTaskTimeout', v)} min={60} max={1200} />
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
            style={inputStyle()}
          />
        </div>
      </div>

      {/* Dark mode */}
      <button
        role="switch" aria-checked={isDark}
        onClick={onToggleDark}
        onMouseEnter={() => setHoveredDarkToggle(true)}
        onMouseLeave={() => setHoveredDarkToggle(false)}
        style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
          borderRadius: 14, cursor: 'pointer', width: '100%',
          background: hoveredDarkToggle
            ? (isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.07)')
            : (isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.04)'),
          border: `1px solid ${hoveredDarkToggle
            ? (isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)')
            : (isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)')}`,
          transition: 'all 0.3s ease',
        }}
      >
        {isDark ? <MoonIcon size={16} color={t.textSecondary} /> : <SunIcon size={16} color={t.textSecondary} />}
        <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: t.textPrimary, textAlign: 'left' }}>Dark Mode</span>
        <div style={{
          width: 44, height: 24, borderRadius: 12, position: 'relative',
          background: isDark ? 'rgba(0,37,201,0.25)' : 'rgba(0,0,0,0.12)',
          border: `1px solid ${isDark ? '#0025C9' : 'rgba(0,0,0,0.12)'}`,
          transition: 'all 0.3s ease', flexShrink: 0,
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
      </button>
    </div>
  );
};

// ─── FileChip ─────────────────────────────────────────────────────────────────
const FileChip = ({ file, onRemove, t }) => {
  const isError = !!file.error;
  const isDone = !isError && file.progress >= 100;

  if (isError) {
    return (
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '4px 10px 4px 8px', borderRadius: 8,
        background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)',
        fontSize: 12, color: '#ef4444', maxWidth: 280, flexShrink: 0,
      }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.error}</span>
        <button onClick={onRemove} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', display: 'flex', alignItems: 'center', padding: 0, flexShrink: 0 }}>
          <XIcon size={11} color="#ef4444" />
        </button>
      </div>
    );
  }

  return (
    <div style={{
      display: 'inline-flex', flexDirection: 'column', gap: 3,
      padding: '4px 10px 4px 8px', borderRadius: 10,
      background: t.glassBgBase, backdropFilter: 'blur(10px)',
      border: `1px solid ${isDone ? 'rgba(74,222,128,0.3)' : t.glassBorder}`,
      fontSize: 12, color: t.textSecondary, maxWidth: 180, flexShrink: 0,
      transition: 'border-color 0.3s ease',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <PaperclipIcon size={11} color={isDone ? '#4ade80' : t.textSecondary} />
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 110 }}>{file.name}</span>
        <button onClick={onRemove} style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.textSecondary, display: 'flex', alignItems: 'center', padding: 0, flexShrink: 0, marginLeft: 'auto' }}>
          <XIcon size={11} color={t.textSecondary} />
        </button>
      </div>
      <div style={{ height: 2, borderRadius: 1, background: 'rgba(255,255,255,0.08)', overflow: 'hidden', opacity: isDone ? 0 : 1, transition: 'opacity 0.5s ease 0.3s' }}>
        <div style={{ height: '100%', width: `${file.progress ?? 0}%`, background: 'linear-gradient(90deg, #4a6de5, #0025C9)', borderRadius: 1, transition: 'width 0.1s ease', boxShadow: '0 0 6px rgba(0,37,201,0.5)' }} />
      </div>
    </div>
  );
};

// ─── MorphOverlay ─────────────────────────────────────────────────────────────
const MorphOverlay = ({ morphRect, morphPhase, morphText, t }) => {
  if (!morphRect || morphPhase === 0) return null;
  const targetTop = 24;
  const targetRight = 24;
  const targetWidth = Math.min(360, window.innerWidth * 0.6);
  const targetLeft = window.innerWidth - targetRight - targetWidth;

  return (
    <div style={{
      position: 'fixed',
      top: morphPhase === 1 ? morphRect.top : targetTop,
      left: morphPhase === 1 ? morphRect.left : targetLeft,
      width: morphPhase === 1 ? morphRect.width : targetWidth,
      height: morphPhase === 1 ? morphRect.height : 'auto',
      borderRadius: morphPhase === 1 ? 999 : '20px 20px 4px 20px',
      background: morphPhase === 1 ? t.glassBgBase : t.userBubbleBg,
      backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)',
      border: `1px solid ${morphPhase === 1 ? t.glassBorder : t.userBubbleBorder}`,
      boxShadow: morphPhase === 1
        ? 'inset 0 1px 1px rgba(255,255,255,0.1), 0 0 20px rgba(0,0,0,0.4)'
        : '0 0 20px rgba(0,37,201,0.2)',
      zIndex: 2000, padding: '14px 18px',
      display: 'flex', alignItems: 'center',
      fontSize: 15, color: t.textPrimary, lineHeight: 1.5,
      overflow: 'hidden',
      transition: 'all 0.8s cubic-bezier(0.16,1,0.3,1)',
      opacity: morphPhase === 2 ? 0 : 1,
    }}>
      <span style={{ opacity: morphPhase === 1 ? 0.7 : 1, transition: 'opacity 0.3s ease' }}>
        {morphText}
      </span>
    </div>
  );
};

// ─── InputBar ─────────────────────────────────────────────────────────────────
const InputBar = ({
  value, onChange, onSend,
  files, onFilesChange, onRemoveFile,
  focused, onFocus, onBlur,
  t, isDark, placeholder, extraStyle, autoFocusOnMount,
}) => {
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const [hoveredSend, setHoveredSend] = useState(false);
  const [hoveredClip, setHoveredClip] = useState(false);
  const uploadIntervalsRef = useRef([]);

  useEffect(() => () => uploadIntervalsRef.current.forEach(clearInterval), []);
  useEffect(() => {
    if (files.length === 0 && uploadIntervalsRef.current.length > 0) {
      uploadIntervalsRef.current.forEach(clearInterval);
      uploadIntervalsRef.current = [];
    }
  }, [files.length]);
  useEffect(() => {
    if (autoFocusOnMount) textareaRef.current?.focus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [value]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (value.trim()) onSend(); }
  };

  const canSend = value.trim().length > 0;

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      borderRadius: 999,
      background: focused ? t.glassBgFocus : t.glassBgBase,
      backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)',
      border: `1px solid ${focused ? t.glassBorderFocus : t.glassBorder}`,
      boxShadow: focused
        ? `0 0 24px rgba(0,37,201,0.3), inset 0 0 5px rgba(255,255,255,0.05), 0 10px 40px rgba(0,0,0,0.3)`
        : `${t.glassHighlight}, 0 0 20px rgba(0,0,0,0.3)`,
      transition: 'all 0.4s cubic-bezier(0.16,1,0.3,1)',
      overflow: 'hidden',
      ...extraStyle,
    }}>
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
          const MAX_FILES = 20, MAX_SIZE_MB = 50, MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;
          const incoming = Array.from(e.target.files);
          const errors = [], valid = [];
          const currentCount = files ? files.length : 0;
          const remaining = MAX_FILES - currentCount;
          let acceptedIncoming = incoming;
          if (incoming.length > remaining) {
            const skipped = incoming.length - remaining;
            errors.push(`Only ${remaining} more file${remaining !== 1 ? 's' : ''} allowed — ${skipped} skipped`);
            acceptedIncoming = incoming.slice(0, remaining);
          }
          for (const f of acceptedIncoming) {
            if (f.size > MAX_SIZE_BYTES) errors.push(`"${f.name}" exceeds ${MAX_SIZE_MB}MB`);
            else valid.push({ name: f.name, size: f.size, file: f, progress: 0 });
          }
          const withErrors = errors.map(err => ({ name: '', size: 0, error: err }));
          onFilesChange(prev => [...prev, ...withErrors, ...valid]);
          valid.forEach(f => {
            let prog = 0;
            const interval = setInterval(() => {
              prog += 10 + Math.random() * 20;
              // Issue #2: cap local validation progress at 90% — only set 100% after real upload succeeds
              if (prog >= 90) { prog = 90; clearInterval(interval); uploadIntervalsRef.current = uploadIntervalsRef.current.filter(id => id !== interval); }
              onFilesChange(prev => prev.map(ex => ex.name === f.name && ex.file === f.file ? { ...ex, progress: Math.round(prog) } : ex));
            }, 80);
            uploadIntervalsRef.current.push(interval);
          });
          e.target.value = '';
        }} />

        <div style={{ width: 1, height: 20, background: t.divider, margin: '0 4px', flexShrink: 0 }} />

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

        <div style={{ width: 1, height: 20, background: t.divider, margin: '0 4px', flexShrink: 0 }} />

        <button aria-label="Send"
          onClick={onSend}
          onMouseEnter={() => setHoveredSend(true)}
          onMouseLeave={() => setHoveredSend(false)}
          disabled={!canSend}
          style={{
            width: 36, height: 36, borderRadius: '50%', border: 'none', cursor: canSend ? 'pointer' : 'default',
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            background: canSend
              ? (hoveredSend ? 'rgba(0,37,201,0.85)' : 'rgba(0,37,201,0.7)')
              : 'transparent',
            color: canSend ? 'white' : t.textSecondary,
            boxShadow: canSend && hoveredSend ? t.neonGlow : 'none',
            transition: 'all 0.2s cubic-bezier(0.16,1,0.3,1)',
          }}>
          <SendIcon size={16} color="currentColor" />
        </button>
      </div>

      {files.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '0 12px 10px 12px' }}>
          {files.map((f, i) => (
            <FileChip key={i} file={f} t={t} onRemove={() => onRemoveFile(i)} />
          ))}
        </div>
      )}
    </div>
  );
};

// ─── ConnectionBanner ────────────────────────────────────────────────────────
const ConnectionBanner = ({ connectionState, onRetry, t, isDark }) => {
  const configs = {
    connecting: { bg: 'rgba(74,109,229,0.12)', border: 'rgba(74,109,229,0.3)', color: '#4a6de5', text: 'Connecting to server...' },
    failed: { bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)', color: '#ef4444', text: 'Connection lost. Task may still be running — check History for results.' },
  };
  const cfg = configs[connectionState];
  if (!cfg) return null;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 3500,
      padding: '10px 20px',
      background: cfg.bg,
      borderBottom: `1px solid ${cfg.border}`,
      backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
      color: cfg.color, fontSize: 13, fontWeight: 500,
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12,
      animation: 'hydra-slide-down 0.3s ease-out',
    }}>
      {connectionState === 'connecting' && (
        <div style={{ width: 14, height: 14, border: `2px solid ${cfg.color}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'hydra-spin 0.8s linear infinite' }} />
      )}
      <span>{cfg.text}</span>
      {connectionState === 'failed' && onRetry && (
        <button onClick={onRetry} style={{
          padding: '4px 12px', borderRadius: 6,
          background: 'rgba(239,68,68,0.2)', border: '1px solid rgba(239,68,68,0.4)',
          color: '#ef4444', cursor: 'pointer', fontSize: 12, fontWeight: 600,
        }}>
          Retry
        </button>
      )}
    </div>
  );
};

// ─── Toast system ────────────────────────────────────────────────────────────
const TOAST_TYPES = {
  success: { bg: 'rgba(74,222,128,0.15)', border: 'rgba(74,222,128,0.3)', color: '#4ade80', icon: '✓' },
  warning: { bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.3)', color: '#f59e0b', icon: '⚠' },
  error:   { bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.3)', color: '#ef4444', icon: '✕' },
  info:    { bg: 'rgba(74,109,229,0.15)', border: 'rgba(74,109,229,0.3)', color: '#4a6de5', icon: 'ℹ' },
};

let toastIdCounter = Date.now(); // Unique seed survives HMR

function useToasts() {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = 'info') => {
    const id = ++toastIdCounter;
    setToasts(prev => {
      const next = [...prev, { id, message, type }];
      // Max 3 visible — remove oldest
      return next.length > 3 ? next.slice(next.length - 3) : next;
    });
    // Auto-dismiss after 5s (errors stay)
    if (type !== 'error') {
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, 5000);
    }
    return id;
  }, []);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return { toasts, addToast, removeToast };
}

const ToastContainer = ({ toasts, onDismiss, isDark }) => {
  const t = tokens(isDark);
  if (toasts.length === 0) return null;
  return (
    <div style={{
      position: 'fixed', bottom: 20, right: 20, zIndex: 4000,
      display: 'flex', flexDirection: 'column', gap: 8,
      pointerEvents: 'none',
    }}>
      {toasts.map(toast => {
        const cfg = TOAST_TYPES[toast.type] || TOAST_TYPES.info;
        return (
          <div key={toast.id} style={{
            padding: '10px 14px',
            borderRadius: 12,
            background: isDark ? cfg.bg : cfg.bg.replace('0.15', '0.25'),
            border: `1px solid ${cfg.border}`,
            backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
            boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
            color: cfg.color, fontSize: 13, fontWeight: 500,
            display: 'flex', alignItems: 'center', gap: 8,
            pointerEvents: 'auto',
            animation: 'hydra-slide-in 0.3s ease-out',
            maxWidth: 340,
          }}>
            <span style={{ fontSize: 14, flexShrink: 0 }}>{cfg.icon}</span>
            <span style={{ flex: 1 }}>{toast.message}</span>
            <button onClick={() => onDismiss(toast.id)} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: cfg.color, fontSize: 14, lineHeight: 1, padding: 0, flexShrink: 0, opacity: 0.7,
            }}>×</button>
          </div>
        );
      })}
    </div>
  );
};

// ─── RecentTaskCard (home page) ───────────────────────────────────────────────
const RecentTaskCard = ({ run, onClick, isDark }) => {
  const t = tokens(isDark);
  const [hovered, setHovered] = useState(false);
  const statusColor = run.status === 'completed' ? '#4ade80' : run.status === 'failed' ? '#ef4444' : '#f59e0b';
  const statusEmoji = run.status === 'completed' ? '✅' : run.status === 'failed' ? '❌' : '🔄';

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '12px 16px',
        borderRadius: 14,
        background: hovered ? (isDark ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.9)') : t.cardBg,
        border: `1px solid ${hovered ? 'rgba(0,37,201,0.2)' : t.cardBorder}`,
        backdropFilter: 'blur(20px)',
        cursor: 'pointer',
        transition: 'all 0.2s cubic-bezier(0.16,1,0.3,1)',
        transform: hovered ? 'translateY(-2px)' : 'none',
        boxShadow: hovered ? '0 4px 20px rgba(0,0,0,0.1)' : 'none',
      }}
    >
      <div style={{
        fontSize: 13, fontWeight: 500, color: t.textPrimary, marginBottom: 6,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        📋 "{run.task_text}"
      </div>
      <div style={{ display: 'flex', gap: 8, fontSize: 11, color: t.textSecondary, flexWrap: 'wrap' }}>
        <span style={{ color: statusColor }}>{statusEmoji} {run.status}</span>
        {run.agent_count > 0 && <span>• {run.agent_count} agents</span>}
        {run.total_tokens > 0 && <span>• {Math.round(run.total_tokens / 1000)}k tokens</span>}
        <span style={{ marginLeft: 'auto' }}>
          {(() => {
            const diff = Date.now() - new Date(run.created_at).getTime();
            if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
            if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
            return `${Math.floor(diff / 86400000)}d ago`;
          })()}
        </span>
      </div>
    </div>
  );
};

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [isDark, setIsDark] = useState(() => {
    try { return JSON.parse(localStorage.getItem('hydra_dark') ?? 'true'); } catch { return true; }
  });
  const [settings, setSettings] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('hydra_settings') ?? '{}');
      return { ...DEFAULT_SETTINGS, ...saved };
    } catch { return { ...DEFAULT_SETTINGS }; }
  });

  // UI state
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [appState, setAppState] = useState('IDLE'); // IDLE | ANIMATING | ORCHESTRATING | RESULT
  const [inputFocused, setInputFocused] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [files, setFiles] = useState([]);
  const [authError, setAuthError] = useState(null); // Issue #1: auth failure banner

  // Orchestration state
  const [currentTask, setCurrentTask] = useState('');
  const [orchestrationEvents, setOrchestrationEvents] = useState([]);
  const [isCancelling, setIsCancelling] = useState(false);
  const [result, setResult] = useState(null);

  // Recent tasks on home page
  const [recentRuns, setRecentRuns] = useState([]);

  // Animation state
  const [morphRect, setMorphRect] = useState(null);
  const [morphText, setMorphText] = useState('');
  const [morphPhase, setMorphPhase] = useState(0);
  const initialBarRef = useRef(null);

  // Refs
  const settingsPanelRef = useRef(null);
  const settingsBtnRef = useRef(null);
  const historyPanelRef = useRef(null);
  const historyBtnRef = useRef(null);
  const mockAbortRef = useRef(false);

  // WebSocket
  const { connect, cancel, respondConfirmation, disconnect, retry,
    connectionState } = useWebSocket();

  // Toasts
  const { toasts, addToast, removeToast } = useToasts();

  const t = useMemo(() => tokens(isDark), [isDark]);

  // Persist settings
  useEffect(() => { localStorage.setItem('hydra_settings', JSON.stringify(settings)); }, [settings]);
  useEffect(() => { localStorage.setItem('hydra_dark', JSON.stringify(isDark)); }, [isDark]);

  // Inject styles
  useEffect(() => {
    const style = document.createElement('style');
    style.id = 'hydra-styles';
    style.textContent = `
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
      html, body, #root { height: 100%; }
      body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
      @keyframes hydra-cursor-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
      @keyframes hydra-pulse { 0%, 100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.15); opacity: 0.7; } }
      @keyframes hydra-dot-bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-4px); } }
      @keyframes hydra-shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(300%); } }
      @keyframes hydra-spin { to { transform: rotate(360deg); } }
      @keyframes hydra-slide-in { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
      @keyframes hydra-slide-down { from { transform: translateY(-100%); } to { transform: translateY(0); } }
      @media (max-width: 640px) {
        .hydra-idle-bar { width: 90vw !important; }
      }
    `;
    document.head.appendChild(style);
    return () => document.getElementById('hydra-styles')?.remove();
  }, []);

  // Click outside to close settings or history
  useEffect(() => {
    const handler = (e) => {
      if (
        settingsPanelRef.current && !settingsPanelRef.current.contains(e.target) &&
        settingsBtnRef.current && !settingsBtnRef.current.contains(e.target)
      ) setSettingsOpen(false);
      if (
        historyPanelRef.current && !historyPanelRef.current.contains(e.target) &&
        historyBtnRef.current && !historyBtnRef.current.contains(e.target)
      ) setHistoryOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') { setSettingsOpen(false); setHistoryOpen(false); } };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  // Load recent tasks on home page
  useEffect(() => {
    if (appState === 'IDLE' && settings.apiBaseUrl) {
      fetchHistory(settings.serverToken, 5)
        .then(setRecentRuns)
        .catch(() => {}); // silent fail
    }
  }, [appState, settings.apiBaseUrl, settings.serverToken]);

  const handleSettingChange = useCallback((key, val) => {
    setSettings(prev => ({ ...prev, [key]: val }));
  }, []);

  // ── Start task ─────────────────────────────────────────────────────────────
  const startOrchestration = useCallback(async (taskText, uploadedFiles = []) => {
    setCurrentTask(taskText);
    setOrchestrationEvents([]);
    setIsCancelling(false);
    setResult(null);
    setAuthError(null);

    const addEvent = (event) => {
      setOrchestrationEvents(prev => [...prev, event]);
    };

    if (!settings.apiBaseUrl) {
      // Mock mode
      mockAbortRef.current = false;
      const gen = mockOrchestration(taskText);
      for await (const event of gen) {
        if (mockAbortRef.current) break;
        addEvent(event);
        if (event.type === 'pipeline_complete') {
          setResult(event.data);
          setTimeout(() => setAppState('RESULT'), 400);
          break;
        }
        if (event.type === 'pipeline_error') {
          setTimeout(() => setAppState('RESULT'), 400);
          break;
        }
      }
    } else {
      // Real WebSocket mode
      const filePaths = uploadedFiles.map(f => f.filepath || f);
      // H1: Map frontend camelCase names to backend snake_case field names.
      // temperature is per-agent (set by Brain), not a top-level config — excluded (M6).
      const configOverrides = {
        api_key: settings.apiKey || undefined,
        default_model: settings.model || undefined,
        brain_model: settings.brainModel || undefined,
        post_brain_model: settings.postBrainModel || undefined,
        max_concurrent_agents: settings.maxConcurrentAgents,
        per_agent_timeout_seconds: settings.perAgentTimeout,
        total_task_timeout_seconds: settings.totalTaskTimeout,
        min_quality_score: settings.qualityScoreThreshold,
        output_directory: settings.outputDirectory,
      };
      // Remove undefined values
      Object.keys(configOverrides).forEach(k => configOverrides[k] === undefined && delete configOverrides[k]);

      connect({
        apiBaseUrl: settings.apiBaseUrl,
        serverToken: settings.serverToken,
        task: taskText,
        files: filePaths,
        configOverrides,
        onEvent: (event) => {
          addEvent(event);
          if (event.type === 'pipeline_complete') {
            setResult(event.data);
            setTimeout(() => setAppState('RESULT'), 400);
          }
          if (event.type === 'pipeline_error') {
            setTimeout(() => setAppState('RESULT'), 400);
          }
        },
        onError: (err) => {
          // Issue #8: set result with error so ResultView shows error state
          setResult({ error: err, output: '', execution_summary: {} });
          addEvent({ type: 'pipeline_error', data: { error: err }, timestamp: Date.now() / 1000 });
          setTimeout(() => setAppState('RESULT'), 400);
        },
        onClose: (code) => {
          // Issue #1: handle WS close code 4001 = bad token
          if (code === 4001) {
            setAuthError('Authentication failed: invalid server token (code 4001). Please check your Server Token in Settings.');
          }
        },
        onConnectionStateChange: (state) => {
          if (state === 'failed') {
            addToast('Connection lost. Check server status or try again.', 'error');
          }
        },
      });
    }
  }, [settings, connect, addToast]);

  // ── Handle send ───────────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text) return;
    setInputValue('');

    const barEl = initialBarRef.current;
    if (barEl && appState === 'IDLE') {
      const rect = barEl.getBoundingClientRect();
      setMorphRect(rect);
      setMorphText(text);
      setMorphPhase(1);
      setAppState('ANIMATING');

      const filesToUpload = files.filter(f => !f.error && f.file);
      setFiles([]);

      setTimeout(async () => {
        setMorphPhase(2);
        setTimeout(async () => {
          setAppState('ORCHESTRATING');
          setMorphPhase(0);
          setMorphRect(null);

          // Upload files if any (real backend only)
          let uploadedFiles = [];
          if (filesToUpload.length > 0 && settings.apiBaseUrl) {
            try {
              uploadedFiles = await uploadFiles(filesToUpload, settings.serverToken);
              // Issue #2: set 100% only after real upload succeeds
              setFiles(prev => prev.map(f => ({ ...f, progress: 100 })));
            } catch (err) {
              console.warn('File upload failed:', err);
            }
          } else if (filesToUpload.length > 0) {
            // Issue #2: mock mode — go straight to 100%
            setFiles(prev => prev.map(f => ({ ...f, progress: 100 })));
          }

          await startOrchestration(text, uploadedFiles);
        }, 350);
      }, 500);
    }
  }, [inputValue, appState, files, settings, startOrchestration]);

  // ── Cancel ────────────────────────────────────────────────────────────────
  const handleCancel = useCallback(() => {
    setIsCancelling(true);
    if (settings.apiBaseUrl) {
      cancel();
    } else {
      mockAbortRef.current = true;
      setTimeout(() => {
        setAppState('IDLE');
        setIsCancelling(false);
        // Issue #7: clear orchestration state on cancel in mock mode
        setOrchestrationEvents([]);
        setCurrentTask('');
        setFiles([]);
      }, 500);
    }
  }, [settings.apiBaseUrl, cancel]);

  // ── Reset to home ─────────────────────────────────────────────────────────
  const handleNewTask = useCallback(() => {
    disconnect();
    mockAbortRef.current = true;
    setAppState('IDLE');
    setOrchestrationEvents([]);
    setResult(null);
    setCurrentTask('');
    setIsCancelling(false);
  }, [disconnect]);

  // ── Open result from history ──────────────────────────────────────────────
  const handleOpenHistoryResult = useCallback((runData) => {
    setResult(runData.result || runData);
    setCurrentTask(runData.task_text || '');
    setHistoryOpen(false);
    setAppState('RESULT');
  }, []);

  // ── Open recent task (from home) ──────────────────────────────────────────
  const handleOpenRecentTask = useCallback(async (run) => {
    if (!settings.apiBaseUrl) return;
    try {
      const full = await fetchHistoryRun(settings.serverToken, run.task_id);
      setResult(full.result || full);
      setCurrentTask(full.task_text || run.task_text || '');
      setAppState('RESULT');
    } catch {
      // If we can't fetch, just run again
      setInputValue(run.task_text || '');
    }
  }, [settings]);

  // ── Hover states ──────────────────────────────────────────────────────────
  const [hoveredSettingsBtn, setHoveredSettingsBtn] = useState(false);
  const [hoveredHistoryBtn, setHoveredHistoryBtn] = useState(false);
  const [hoveredNewChat, setHoveredNewChat] = useState(false);

  // ── Nav button style ──────────────────────────────────────────────────────
  const navBtnStyle = (active, hovered) => ({
    width: 44, height: 44, borderRadius: '50%', cursor: 'pointer',
    background: active ? 'rgba(0,37,201,0.15)' : hovered ? 'rgba(255,255,255,0.08)' : t.settingsBg,
    border: `1px solid ${active ? '#0025C9' : hovered ? 'rgba(0,37,201,0.5)' : t.settingsBorder}`,
    backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
    boxShadow: active
      ? '0 0 25px rgba(0,37,201,0.35), inset 0 0 8px rgba(0,37,201,0.15)'
      : hovered ? '0 0 20px rgba(0,37,201,0.25)' : 'inset 0 1px 1px rgba(255,255,255,0.05)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: active ? '#0025C9' : hovered ? t.textPrimary : t.textSecondary,
    transform: hovered ? 'scale(1.05)' : 'scale(1)',
    transition: 'all 0.3s cubic-bezier(0.16,1,0.3,1)',
  });

  return (
    <div style={{
      height: '100vh', width: '100vw',
      backgroundColor: t.bgColor,
      backgroundImage: t.bgGradient,
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      WebkitFontSmoothing: 'antialiased',
      position: 'relative', overflow: 'hidden',
      transition: 'background-color 0.4s ease',
    }}>

      {/* ── Connection banner ── */}
      <ConnectionBanner
        connectionState={connectionState}
        onRetry={retry}
        t={t}
        isDark={isDark}
      />

      {/* ── Toast notifications ── */}
      <ToastContainer toasts={toasts} onDismiss={removeToast} isDark={isDark} />

      {/* ── Left nav: Settings + History ── */}
      <div style={{ position: 'fixed', top: 24, left: 24, zIndex: 1001, display: 'flex', gap: 8 }}>
        {/* Settings */}
        <div>
          <button
            ref={settingsBtnRef}
            onClick={e => { e.stopPropagation(); setSettingsOpen(p => !p); }}
            onMouseEnter={() => setHoveredSettingsBtn(true)}
            onMouseLeave={() => setHoveredSettingsBtn(false)}
            aria-label="Settings"
            style={navBtnStyle(settingsOpen, hoveredSettingsBtn)}
          >
            <GearIcon size={20} />
          </button>
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

        {/* History */}
        <div>
          <button
            ref={historyBtnRef}
            onClick={e => { e.stopPropagation(); setHistoryOpen(p => !p); }}
            onMouseEnter={() => setHoveredHistoryBtn(true)}
            onMouseLeave={() => setHoveredHistoryBtn(false)}
            aria-label="Task History"
            style={navBtnStyle(historyOpen, hoveredHistoryBtn)}
          >
            <ClockIcon size={18} />
          </button>
          <div ref={historyPanelRef} style={{ position: 'relative' }}>
            {historyOpen && (
              <HistoryPage
                isDark={isDark}
                apiBaseUrl={settings.apiBaseUrl}
                serverToken={settings.serverToken}
                onClose={() => setHistoryOpen(false)}
                onOpenResult={handleOpenHistoryResult}
                isDropdown={true}
              />
            )}
          </div>
        </div>
      </div>

      {/* ── Right nav: New Task (IDLE only — ResultView has its own buttons) ── */}

      {/* ── Morph overlay ── */}
      <MorphOverlay morphRect={morphRect} morphPhase={morphPhase} morphText={morphText} t={t} />

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
          gap: 16,
        }}>
          {/* Title */}
          <div style={{
            textAlign: 'center', marginBottom: 20,
            opacity: inputFocused ? 0.4 : 1,
            transition: 'opacity 0.3s ease',
          }}>
            <div style={{
              fontSize: 'clamp(36px, 10vw, 72px)',
              color: t.textPrimary,
              fontFamily: '"ByteBounce", "Inter", sans-serif',
              letterSpacing: '0.04em', lineHeight: 1,
              textShadow: '0 0 40px rgba(0,37,201,0.4)',
            }}>HYDRA</div>
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

          {/* Recent tasks */}
          {recentRuns.length > 0 && (
            <div style={{
              width: 480, maxWidth: '90vw',
              opacity: inputFocused ? 0.3 : 1,
              transition: 'opacity 0.3s ease',
            }}>
              <div style={{ fontSize: 11, color: t.textSecondary, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>
                Recent
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {recentRuns.slice(0, 3).map(run => (
                  <RecentTaskCard
                    key={run.task_id}
                    run={run}
                    onClick={() => handleOpenRecentTask(run)}
                    isDark={isDark}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── ORCHESTRATING STATE ── */}
      {appState === 'ORCHESTRATING' && (
        <>
          {/* Issue #1: auth error banner */}
          {authError && (
            <div style={{
              position: 'fixed', top: 80, left: '50%', transform: 'translateX(-50%)',
              zIndex: 2500, maxWidth: 480, width: '90vw',
              padding: '12px 16px', borderRadius: 12,
              background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)',
              color: '#ef4444', fontSize: 13, fontWeight: 500,
              backdropFilter: 'blur(20px)',
              display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <span>🔐</span>
              <span style={{ flex: 1 }}>{authError}</span>
              <button onClick={() => setAuthError(null)} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: '#ef4444', fontSize: 16, lineHeight: 1, padding: 0,
              }}>×</button>
            </div>
          )}
          <OrchestrationView
            taskText={currentTask}
            events={orchestrationEvents}
            isDark={isDark}
            onCancel={handleCancel}
            isCancelling={isCancelling}
            onConfirmationApprove={(confId) => respondConfirmation(confId, true)}
            onConfirmationReject={(confId) => respondConfirmation(confId, false)}
            connectionState={connectionState}
            onRetryPipeline={() => {
              setInputValue(currentTask);
              handleNewTask();
            }}
          />
        </>
      )}

      {/* ── RESULT STATE ── */}
      {appState === 'RESULT' && (
        <ResultView
          result={result}
          taskText={currentTask}
          isDark={isDark}
          apiBaseUrl={settings.apiBaseUrl}
          serverToken={settings.serverToken}
          onNewTask={handleNewTask}
          onRunAgain={() => {
            setInputValue(currentTask);
            handleNewTask();
          }}
          addToast={addToast}
        />
      )}

      {/* History is now a dropdown panel next to the History button */}
    </div>
  );
}
