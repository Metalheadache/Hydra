import React, { useState, useEffect, useCallback } from 'react';
import { tokens, TrashIcon, timeAgo, formatTokens } from './tokens.jsx';
import { fetchHistory, fetchHistoryRun, deleteHistoryRun } from './useWebSocket.js';

// ── History Card ─────────────────────────────────────────────────────────────
const HistoryCard = ({ run, onOpen, onDelete, isDark, isLoading }) => {
  const t = tokens(isDark);
  const [hovered, setHovered] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const statusColor = run.status === 'completed' ? '#4ade80'
    : run.status === 'failed' ? '#ef4444'
    : '#f59e0b';
  const statusEmoji = run.status === 'completed' ? '✅' : run.status === 'failed' ? '❌' : '🔄';

  const handleDelete = async (e) => {
    e.stopPropagation();
    if (deleting) return;
    setDeleting(true);
    await onDelete(run.task_id);
  };

  return (
    <div
      onClick={() => onOpen(run)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '14px 16px',
        borderRadius: 14,
        // Issue #13: show reduced opacity when this specific card is loading
        opacity: isLoading ? 0.6 : 1,
        background: isLoading
          ? (isDark ? 'rgba(0,37,201,0.08)' : 'rgba(0,37,201,0.04)')
          : hovered ? (isDark ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.9)') : t.cardBg,
        border: `1px solid ${isLoading ? 'rgba(0,37,201,0.3)' : hovered ? 'rgba(0,37,201,0.2)' : t.cardBorder}`,
        backdropFilter: 'blur(20px)',
        cursor: isLoading ? 'wait' : 'pointer',
        transition: 'all 0.2s cubic-bezier(0.16,1,0.3,1)',
        transform: hovered && !isLoading ? 'translateY(-1px)' : 'translateY(0)',
        boxShadow: hovered && !isLoading ? '0 4px 20px rgba(0,0,0,0.15)' : 'none',
        marginBottom: 10,
        display: 'flex', flexDirection: 'column', gap: 6,
      }}
    >
      {/* Task text */}
      <div style={{
        fontSize: 14, fontWeight: 600, color: t.textPrimary,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        {/* Issue #13: show spinner on the specific loading card */}
        {isLoading && (
          <div style={{
            width: 14, height: 14, borderRadius: '50%', flexShrink: 0,
            border: '2px solid rgba(74,109,229,0.3)',
            borderTopColor: '#4a6de5',
            animation: 'hydra-spin 0.8s linear infinite',
          }} />
        )}
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          📋 {run.task_text || 'Untitled task'}
        </span>
      </div>

      {/* Meta row */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        fontSize: 12, color: t.textSecondary, flexWrap: 'wrap',
      }}>
        <span style={{ color: statusColor }}>{statusEmoji} {run.status}</span>
        {run.agent_count > 0 && <span>🤖 {run.agent_count} agents</span>}
        {run.total_tokens > 0 && <span>🪙 {formatTokens(run.total_tokens)}</span>}
        <span style={{ marginLeft: 'auto', color: t.textSecondary }}>
          {timeAgo(run.created_at)}
        </span>

        {/* Delete button */}
        <button
          onClick={handleDelete}
          disabled={deleting}
          style={{
            background: 'none', border: 'none', cursor: deleting ? 'default' : 'pointer',
            color: deleting ? t.textSecondary : '#ef4444',
            display: 'flex', alignItems: 'center', padding: '2px 4px',
            borderRadius: 6, opacity: hovered ? 1 : 0,
            transition: 'all 0.2s ease',
          }}
        >
          <TrashIcon size={14} />
        </button>
      </div>
    </div>
  );
};

// ── Main HistoryPage ──────────────────────────────────────────────────────────
export default function HistoryPage({
  isDark,
  apiBaseUrl,
  serverToken,
  onClose,
  onOpenResult,
  isDropdown = false,
}) {
  const t = tokens(isDark);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [loadingRun, setLoadingRun] = useState(false);
  // Issue #13: track which specific card is loading by task_id
  const [loadingId, setLoadingId] = useState(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHistory(apiBaseUrl, serverToken, 20);
      setRuns(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, serverToken]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleOpen = useCallback(async (run) => {
    if (loadingRun) return;
    setLoadingRun(true);
    // Issue #13: track which specific card is loading
    setLoadingId(run.task_id);
    try {
      const full = await fetchHistoryRun(apiBaseUrl, serverToken, run.task_id);
      onOpenResult(full);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingRun(false);
      setLoadingId(null);
    }
  }, [apiBaseUrl, serverToken, onOpenResult, loadingRun]);

  const handleDelete = useCallback(async (taskId) => {
    try {
      await deleteHistoryRun(apiBaseUrl, serverToken, taskId);
      setRuns(prev => prev.filter(r => r.task_id !== taskId));
    } catch (err) {
      setError(err.message);
    }
  }, [apiBaseUrl, serverToken]);

  if (isDropdown) {
    return (
      <div
        onClick={e => e.stopPropagation()}
        style={{
          position: 'absolute',
          top: 'calc(100% + 12px)',
          left: 0,
          width: 380,
          maxHeight: '70vh',
          borderRadius: 20,
          background: t.panelBg,
          border: `1px solid ${t.panelBorder}`,
          backdropFilter: 'blur(40px)',
          WebkitBackdropFilter: 'blur(40px)',
          boxShadow: '0 0 40px rgba(0,0,0,0.8), 0 20px 60px rgba(0,0,0,0.6), inset 0 1px 1px rgba(255,255,255,0.08)',
          opacity: 1,
          transform: 'translateY(0) scale(1)',
          transformOrigin: 'top left',
          transition: 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
          zIndex: 2000,
        }}
      >
        {/* Dropdown header */}
        <div style={{
          padding: '14px 16px',
          borderBottom: `1px solid ${t.cardBorder}`,
          display: 'flex', alignItems: 'center',
          flexShrink: 0,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: t.textPrimary }}>Task History</div>
            <div style={{ fontSize: 11, color: t.textSecondary, marginTop: 1 }}>
              {runs.length} recent runs
            </div>
          </div>
        </div>

        {/* Dropdown content */}
        <div style={{
          flex: 1, overflowY: 'auto',
          padding: '10px 12px',
          scrollbarWidth: 'thin',
        }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: '20px', color: t.textSecondary, fontSize: 13 }}>
              ⏳ Loading...
            </div>
          )}
          {error && !loading && (
            <div style={{
              padding: '10px 12px', borderRadius: 10,
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)',
              color: '#ef4444', fontSize: 12, marginBottom: 8,
            }}>
              ⚠️ {error}
            </div>
          )}
          {!loading && !error && runs.length === 0 && (
            <div style={{ textAlign: 'center', padding: '30px 16px', color: t.textSecondary }}>
              <div style={{ fontSize: 28, marginBottom: 6 }}>📭</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: t.textPrimary }}>No history yet</div>
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {runs.map(run => (
              <HistoryCard
                key={run.task_id}
                run={run}
                onOpen={() => handleOpen(run)}
                onDelete={() => handleDelete(run.task_id)}
                isDark={isDark}
                isLoading={loadingId === run.task_id}
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Full overlay mode (fallback)
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 2000,
      background: 'rgba(0,0,0,0.5)',
      backdropFilter: 'blur(12px)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end',
    }} onClick={onClose}>
      <div
        style={{
          width: '100%', maxWidth: 520, height: '100%',
          background: t.panelBg,
          border: `1px solid ${t.panelBorder}`,
          backdropFilter: 'blur(40px)',
          WebkitBackdropFilter: 'blur(40px)',
          boxShadow: '-20px 0 60px rgba(0,0,0,0.5)',
          display: 'flex', flexDirection: 'column',
          animation: 'hydra-slide-in 0.35s cubic-bezier(0.16,1,0.3,1)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          padding: '20px 20px 16px',
          borderBottom: `1px solid ${t.cardBorder}`,
          display: 'flex', alignItems: 'center', gap: 12,
          flexShrink: 0,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: t.textPrimary }}>Task History</div>
            <div style={{ fontSize: 12, color: t.textSecondary, marginTop: 2 }}>
              {runs.length} recent runs
            </div>
          </div>
          <button onClick={onClose} style={{
            width: 32, height: 32, borderRadius: '50%',
            background: 'transparent', border: `1px solid ${t.cardBorder}`,
            cursor: 'pointer', color: t.textSecondary,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 0.2s ease',
          }}>
            <svg viewBox="0 0 24 24" width={16} height={16} stroke="currentColor" strokeWidth="2" fill="none">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div style={{
          flex: 1, overflowY: 'auto',
          padding: '16px 20px',
          scrollbarWidth: 'thin',
        }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: t.textSecondary }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>⏳</div>
              Loading history...
            </div>
          )}

          {error && !loading && (
            <div style={{
              padding: '14px 16px', borderRadius: 12,
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)',
              color: '#ef4444', fontSize: 13, marginBottom: 12,
            }}>
              ⚠️ {error}
              <button onClick={loadHistory} style={{
                marginLeft: 10, background: 'none', border: 'none',
                color: '#ef4444', cursor: 'pointer', fontSize: 12,
                textDecoration: 'underline',
              }}>Retry</button>
            </div>
          )}

          {!loading && !error && runs.length === 0 && (
            <div style={{
              textAlign: 'center', padding: '60px 20px',
              color: t.textSecondary,
            }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>📭</div>
              <div style={{ fontSize: 15, fontWeight: 600, color: t.textPrimary, marginBottom: 6 }}>
                No task history yet
              </div>
              <div style={{ fontSize: 13 }}>
                Your completed tasks will appear here.
              </div>
            </div>
          )}

          {loadingRun && (
            <div style={{
              padding: '8px 14px', borderRadius: 10,
              background: 'rgba(0,37,201,0.1)', border: '1px solid rgba(0,37,201,0.2)',
              color: '#4a6de5', fontSize: 13, marginBottom: 12,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <div style={{ width: 12, height: 12, borderRadius: '50%', border: '2px solid #4a6de5', borderTopColor: 'transparent', animation: 'hydra-spin 0.8s linear infinite' }} />
              Loading task details...
            </div>
          )}

          {!loading && runs.map(run => (
            <HistoryCard
              key={run.task_id}
              run={run}
              onOpen={handleOpen}
              onDelete={handleDelete}
              isDark={isDark}
              isLoading={loadingId === run.task_id}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
