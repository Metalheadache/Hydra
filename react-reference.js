import React, { useState, useEffect, useRef } from 'react';

const customStyles = {
  root: {
    '--bg-color': '#05070a',
    '--glass-bg-base': 'linear-gradient(180deg, rgba(200, 220, 255, 0.05) 0%, rgba(255, 255, 255, 0.02) 100%)',
    '--glass-bg-focus': 'linear-gradient(180deg, rgba(160, 210, 255, 0.08) 0%, rgba(255, 255, 255, 0.04) 100%)',
    '--glass-border': 'rgba(192, 192, 192, 0.2)',
    '--glass-border-focus': 'rgba(160, 230, 255, 0.6)',
    '--glass-highlight': 'inset 0 1px 1px rgba(255, 255, 255, 0.1)',
    '--glass-shadow-drop': '0 0 20px rgba(0, 0, 0, 0.4)',
    '--neon-glow': '0 0 20px rgba(0, 37, 201, 0.35), inset 0 0 5px rgba(255, 255, 255, 0.05)',
    '--text-primary': '#f0f2f5',
    '--text-secondary': '#94a3b8',
    '--accent-neon': '#0025C9',
    '--accent-magenta': '#cbd5e1',
  }
};

const App = () => {
  const [isDark, setIsDark] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const [tiles, setTiles] = useState([
    { id: 'wifi', label: 'Wi-Fi', status: 'On', active: true },
    { id: 'bluetooth', label: 'Bluetooth', status: 'On', active: true },
    { id: 'airdrop', label: 'AirDrop', status: 'Contacts', active: false },
    { id: 'focus', label: 'Focus', status: 'Off', active: false },
  ]);
  const [brightnessLevel] = useState(75);
  const [volumeLevel] = useState(60);
  const controlCenterRef = useRef(null);
  const settingsBtnRef = useRef(null);

  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { 
        min-height: 100vh; 
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        -webkit-font-smoothing: antialiased;
      }
      .search-input-el::placeholder { color: #4a7aff; opacity: 0.8; }
      .search-input-el:focus::placeholder { color: #0025C9; opacity: 0.8; }
      .toggle-switch-el::after {
        content: '';
        position: absolute;
        top: 3px;
        left: 3px;
        width: 16px;
        height: 16px;
        border-radius: 50%;
        background: #94a3b8;
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      }
      .toggle-switch-el.active-toggle::after {
        left: calc(100% - 19px);
        background: #4a7aff;
        box-shadow: 0 0 10px rgba(0, 37, 201, 0.6);
      }
      @media (max-width: 480px) {
        .search-container-el { width: 100% !important; max-width: 320px; }
        .search-container-el.focused { width: 100% !important; max-width: 100% !important; }
      }
    `;
    document.head.appendChild(style);
    return () => document.head.removeChild(style);
  }, []);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (
        controlCenterRef.current &&
        !controlCenterRef.current.contains(e.target) &&
        settingsBtnRef.current &&
        !settingsBtnRef.current.contains(e.target)
      ) {
        setSettingsOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  const toggleTile = (id) => {
    setTiles(prev => prev.map(tile => {
      if (tile.id === id) {
        const newActive = !tile.active;
        let newStatus = tile.status;
        if (tile.status === 'On') newStatus = 'Off';
        else if (tile.status === 'Off') newStatus = 'On';
        return { ...tile, active: newActive, status: newStatus };
      }
      return tile;
    }));
  };

  const toggleTheme = () => {
    setIsDark(prev => !prev);
  };

  const bgStyle = isDark
    ? {
        backgroundColor: '#05070a',
        backgroundImage: 'radial-gradient(circle at 20% 20%, rgba(0, 37, 201, 0.1) 0%, transparent 40%), radial-gradient(circle at 80% 80%, rgba(74, 109, 229, 0.06) 0%, transparent 40%)',
      }
    : {
        backgroundColor: '#f0f4f8',
        backgroundImage: 'radial-gradient(circle at 15% 20%, rgba(0, 37, 201, 0.15) 0%, transparent 45%), radial-gradient(circle at 85% 75%, rgba(26, 71, 255, 0.1) 0%, transparent 40%), radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.5) 0%, transparent 70%)',
      };

  const controlCenterBg = isDark
    ? { background: 'rgba(15, 20, 25, 0.85)', borderColor: 'rgba(192, 192, 192, 0.15)' }
    : { background: 'rgba(255, 255, 255, 0.7)', borderColor: 'rgba(255, 255, 255, 0.8)' };

  const settingsBtnBg = isDark
    ? { background: 'rgba(255, 255, 255, 0.03)', borderColor: 'rgba(192, 192, 192, 0.2)' }
    : { background: 'rgba(255, 255, 255, 0.5)', borderColor: 'rgba(255, 255, 255, 0.6)' };

  const textPrimary = isDark ? '#f0f2f5' : '#0f172a';
  const textSecondary = isDark ? '#94a3b8' : '#64748b';

  const glassBgBase = isDark
    ? 'linear-gradient(180deg, rgba(200, 220, 255, 0.05) 0%, rgba(255, 255, 255, 0.02) 100%)'
    : 'linear-gradient(180deg, rgba(255, 255, 255, 0.7) 0%, rgba(255, 255, 255, 0.4) 100%)';

  const glassBgFocus = isDark
    ? 'linear-gradient(180deg, rgba(160, 210, 255, 0.08) 0%, rgba(255, 255, 255, 0.04) 100%)'
    : 'linear-gradient(180deg, rgba(255, 255, 255, 0.9) 0%, rgba(255, 255, 255, 0.6) 100%)';

  const glassBorder = isDark ? 'rgba(192, 192, 192, 0.2)' : 'rgba(255, 255, 255, 0.6)';
  const glassBorderFocus = 'rgba(160, 230, 255, 0.6)';

  const searchContainerStyle = {
    display: 'flex',
    alignItems: 'center',
    height: '52px',
    padding: '0 8px',
    borderRadius: '999px',
    background: searchFocused ? glassBgFocus : glassBgBase,
    backdropFilter: 'blur(24px)',
    WebkitBackdropFilter: 'blur(24px)',
    border: `1px solid ${searchFocused ? glassBorderFocus : glassBorder}`,
    boxShadow: searchFocused
      ? '0 0 20px rgba(0, 37, 201, 0.35), inset 0 0 5px rgba(255, 255, 255, 0.05), 0 10px 40px rgba(0, 0, 0, 0.4)'
      : 'inset 0 1px 1px rgba(255, 255, 255, 0.1), 0 0 20px rgba(0, 0, 0, 0.4)',
    width: searchFocused ? '420px' : '280px',
    transition: 'width 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.4s cubic-bezier(0.16, 1, 0.3, 1), background 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
  };

  const iconBtnStyle = (hovered) => ({
    background: 'transparent',
    border: 'none',
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: textSecondary,
    cursor: 'pointer',
    transition: 'color 0.2s ease, background 0.2s ease, transform 0.2s ease',
    flexShrink: 0,
  });

  const dividerStyle = {
    width: '1px',
    height: '20px',
    background: 'linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0) 100%)',
    margin: '0 4px',
  };

  const getTileIcon = (id) => {
    switch (id) {
      case 'wifi':
        return (
          <svg viewBox="0 0 24 24" style={{ width: '24px', height: '24px', stroke: 'currentColor', strokeWidth: '1.8', strokeLinecap: 'round', strokeLinejoin: 'round', fill: 'none' }}>
            <path d="M5 12.55a11 11 0 0 1 14.08 0" /><path d="M1.42 9a16 16 0 0 1 21.16 0" /><path d="M8.53 16.11a6 6 0 0 1 6.95 0" /><line x1="12" y1="20" x2="12.01" y2="20" />
          </svg>
        );
      case 'bluetooth':
        return (
          <svg viewBox="0 0 24 24" style={{ width: '24px', height: '24px', stroke: 'currentColor', strokeWidth: '1.8', strokeLinecap: 'round', strokeLinejoin: 'round', fill: 'none' }}>
            <polyline points="6.5 6.5 17.5 17.5 12 23 12 1 17.5 6.5 6.5 17.5" />
          </svg>
        );
      case 'airdrop':
        return (
          <svg viewBox="0 0 24 24" style={{ width: '24px', height: '24px', stroke: 'currentColor', strokeWidth: '1.8', strokeLinecap: 'round', strokeLinejoin: 'round', fill: 'none' }}>
            <circle cx="12" cy="12" r="1" /><path d="M12 2a10 10 0 0 0-7.5 16.6l-2 2.1A12 12 0 0 1 12 0a12 12 0 0 1 9.5 20.7l-2-2.1A10 10 0 0 0 12 2z" />
          </svg>
        );
      case 'focus':
        return (
          <svg viewBox="0 0 24 24" style={{ width: '24px', height: '24px', stroke: 'currentColor', strokeWidth: '1.8', strokeLinecap: 'round', strokeLinejoin: 'round', fill: 'none' }}>
            <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="4" /><line x1="4.93" y1="4.93" x2="9.17" y2="9.17" /><line x1="14.83" y1="14.83" x2="19.07" y2="19.07" /><line x1="14.83" y1="9.17" x2="19.07" y2="4.93" /><line x1="4.93" y1="19.07" x2="9.17" y2="14.83" />
          </svg>
        );
      default:
        return null;
    }
  };

  const [hoveredFilterBtn, setHoveredFilterBtn] = useState(false);
  const [hoveredSearchBtn, setHoveredSearchBtn] = useState(false);
  const [hoveredSettingsBtn, setHoveredSettingsBtn] = useState(false);

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        WebkitFontSmoothing: 'antialiased',
        padding: '24px',
        position: 'relative',
        ...bgStyle,
        transition: 'background-color 0.4s ease',
      }}
    >
      {/* Settings Wrapper */}
      <div style={{ position: 'fixed', top: '24px', left: '24px', zIndex: 1000 }}>
        <button
          ref={settingsBtnRef}
          onClick={(e) => {
            e.stopPropagation();
            setSettingsOpen(prev => !prev);
          }}
          onMouseEnter={() => setHoveredSettingsBtn(true)}
          onMouseLeave={() => setHoveredSettingsBtn(false)}
          aria-label="Settings"
          style={{
            width: '44px',
            height: '44px',
            borderRadius: '50%',
            ...settingsBtnBg,
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            boxShadow: settingsOpen
              ? '0 0 25px rgba(0, 37, 201, 0.35), inset 0 0 8px rgba(0, 37, 201, 0.15)'
              : hoveredSettingsBtn
              ? '0 0 20px rgba(0, 37, 201, 0.25), inset 0 1px 1px rgba(255, 255, 255, 0.1)'
              : 'inset 0 1px 1px rgba(255, 255, 255, 0.05), 0 4px 20px rgba(0, 0, 0, 0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: settingsOpen ? '#0025C9' : hoveredSettingsBtn ? textPrimary : textSecondary,
            transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
            transform: hoveredSettingsBtn ? 'scale(1.05)' : 'scale(1)',
            background: settingsOpen
              ? 'rgba(0, 37, 201, 0.15)'
              : hoveredSettingsBtn
              ? 'rgba(255, 255, 255, 0.08)'
              : settingsBtnBg.background,
            borderColor: settingsOpen
              ? '#0025C9'
              : hoveredSettingsBtn
              ? 'rgba(0, 37, 201, 0.5)'
              : settingsBtnBg.borderColor,
            borderWidth: '1px',
            borderStyle: 'solid',
          }}
        >
          <svg viewBox="0 0 24 24" style={{ width: '20px', height: '20px', stroke: 'currentColor', strokeWidth: '1.5', fill: 'none' }}>
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>

        {/* Control Center */}
        <div
          ref={controlCenterRef}
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute',
            top: 'calc(100% + 12px)',
            left: 0,
            width: '320px',
            padding: '16px',
            borderRadius: '20px',
            ...controlCenterBg,
            backdropFilter: 'blur(40px)',
            WebkitBackdropFilter: 'blur(40px)',
            borderWidth: '1px',
            borderStyle: 'solid',
            boxShadow: '0 0 40px rgba(0, 0, 0, 0.8), 0 20px 60px rgba(0, 0, 0, 0.6), inset 0 1px 1px rgba(255, 255, 255, 0.08)',
            opacity: settingsOpen ? 1 : 0,
            visibility: settingsOpen ? 'visible' : 'hidden',
            transform: settingsOpen ? 'translateY(0) scale(1)' : 'translateY(-10px) scale(0.95)',
            transformOrigin: 'top left',
            transition: 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
          }}
        >
          {/* Control Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginBottom: '16px' }}>
            {tiles.map((tile) => (
              <TileComponent
                key={tile.id}
                tile={tile}
                textSecondary={textSecondary}
                textPrimary={textPrimary}
                onToggle={() => toggleTile(tile.id)}
                getIcon={() => getTileIcon(tile.id)}
              />
            ))}
          </div>

          {/* Brightness Slider */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 14px',
            borderRadius: '14px', background: 'rgba(255, 255, 255, 0.03)',
            backdropFilter: 'blur(20px)', border: '1px solid rgba(255, 255, 255, 0.05)', marginBottom: '10px',
          }}>
            <div>
              <svg viewBox="0 0 24 24" style={{ width: '20px', height: '20px', stroke: textSecondary, strokeWidth: '1.8', fill: 'none' }}>
                <circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            </div>
            <div style={{ flex: 1, height: '6px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '3px', position: 'relative', overflow: 'hidden' }}>
              <div style={{ height: '100%', background: 'linear-gradient(90deg, #4a6de5, #0025C9)', borderRadius: '3px', boxShadow: '0 0 10px rgba(165, 243, 252, 0.3)', width: `${brightnessLevel}%` }} />
            </div>
          </div>

          {/* Volume Slider */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 14px',
            borderRadius: '14px', background: 'rgba(255, 255, 255, 0.03)',
            backdropFilter: 'blur(20px)', border: '1px solid rgba(255, 255, 255, 0.05)', marginBottom: '10px',
          }}>
            <div>
              <svg viewBox="0 0 24 24" style={{ width: '20px', height: '20px', stroke: textSecondary, strokeWidth: '1.8', fill: 'none' }}>
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
              </svg>
            </div>
            <div style={{ flex: 1, height: '6px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '3px', position: 'relative', overflow: 'hidden' }}>
              <div style={{ height: '100%', background: 'linear-gradient(90deg, #4a6de5, #0025C9)', borderRadius: '3px', boxShadow: '0 0 10px rgba(165, 243, 252, 0.3)', width: `${volumeLevel}%` }} />
            </div>
          </div>

          {/* Dark Mode Toggle */}
          <div
            onClick={toggleTheme}
            style={{
              display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 14px',
              borderRadius: '14px', background: 'rgba(255, 255, 255, 0.03)',
              backdropFilter: 'blur(20px)', border: '1px solid rgba(255, 255, 255, 0.05)',
              cursor: 'pointer', transition: 'all 0.3s ease',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)'; e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.05)'; e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; }}
          >
            <div>
              <svg viewBox="0 0 24 24" style={{ width: '20px', height: '20px', stroke: textSecondary, strokeWidth: '1.8', fill: 'none' }}>
                <circle cx="12" cy="12" r="5" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            </div>
            <span style={{ flex: 1, fontSize: '13px', fontWeight: 500, color: textPrimary }}>Dark Mode</span>
            <div
              className={`toggle-switch-el ${isDark ? 'active-toggle' : ''}`}
              style={{
                width: '44px',
                height: '24px',
                borderRadius: '12px',
                background: isDark ? 'rgba(0, 37, 201, 0.25)' : 'rgba(255, 255, 255, 0.1)',
                border: `1px solid ${isDark ? '#0025C9' : 'rgba(255,255,255,0.1)'}`,
                position: 'relative',
                cursor: 'pointer',
                transition: 'all 0.3s ease',
              }}
            />
          </div>
        </div>
      </div>

      {/* Search Container */}
      <div
        className={`search-container-el ${searchFocused ? 'focused' : ''}`}
        style={searchContainerStyle}
      >
        <button
          aria-label="Filters"
          onMouseEnter={() => setHoveredFilterBtn(true)}
          onMouseLeave={() => setHoveredFilterBtn(false)}
          style={{
            ...iconBtnStyle(hoveredFilterBtn),
            color: hoveredFilterBtn ? '#4a6de5' : textSecondary,
            background: hoveredFilterBtn ? 'rgba(74, 109, 229, 0.12)' : 'transparent',
          }}
        >
          <svg viewBox="0 0 24 24" style={{ width: '18px', height: '18px', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', fill: 'none' }}>
            <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" /><line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" /><line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" /><line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" />
          </svg>
        </button>

        <div style={dividerStyle} />

        <input
          type="text"
          className="search-input-el"
          placeholder="Search commands, files..."
          autoComplete="off"
          spellCheck="false"
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          onFocus={() => setSearchFocused(true)}
          onBlur={() => setSearchFocused(false)}
          style={{
            flexGrow: 1,
            height: '100%',
            background: 'transparent',
            border: 'none',
            outline: 'none',
            padding: '0 12px',
            color: textPrimary,
            fontFamily: 'inherit',
            fontSize: '15px',
            fontWeight: 400,
            width: '100%',
          }}
        />

        <button
          aria-label="Search"
          onMouseEnter={() => setHoveredSearchBtn(true)}
          onMouseLeave={() => setHoveredSearchBtn(false)}
          style={{
            ...iconBtnStyle(hoveredSearchBtn),
            color: hoveredSearchBtn ? '#0025C9' : textSecondary,
            background: hoveredSearchBtn ? 'rgba(0, 37, 201, 0.15)' : 'transparent',
          }}
        >
          <svg viewBox="0 0 24 24" style={{ width: '18px', height: '18px', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', fill: 'none' }}>
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </button>
      </div>
    </div>
  );
};

const TileComponent = ({ tile, textSecondary, textPrimary, onToggle, getIcon }) => {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      onClick={onToggle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        aspectRatio: '1',
        padding: '14px',
        borderRadius: '16px',
        background: tile.active
          ? 'rgba(0, 37, 201, 0.12)'
          : hovered
          ? 'rgba(255, 255, 255, 0.06)'
          : 'rgba(255, 255, 255, 0.03)',
        backdropFilter: 'blur(20px)',
        border: `1px solid ${tile.active ? 'rgba(0, 37, 201, 0.4)' : hovered ? 'rgba(255, 255, 255, 0.15)' : 'rgba(255, 255, 255, 0.05)'}`,
        boxShadow: tile.active
          ? '0 0 20px rgba(0, 37, 201, 0.2)'
          : 'inset 0 1px 1px rgba(255, 255, 255, 0.02), 0 4px 15px rgba(0, 0, 0, 0.3)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        cursor: 'pointer',
        transition: 'all 0.3s ease',
        transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
      }}
    >
      <div style={{ width: '28px', height: '28px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: tile.active ? '#4a7aff' : textSecondary }}>
        {getIcon()}
      </div>
      <span style={{ fontSize: '11px', fontWeight: 500, color: textSecondary, textTransform: 'uppercase', letterSpacing: '0.5px' }}>{tile.label}</span>
      <span style={{ fontSize: '13px', fontWeight: 600, color: textPrimary }}>{tile.status}</span>
    </div>
  );
};

export default App;