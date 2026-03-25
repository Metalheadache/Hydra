import React, { useState, useCallback } from 'react';
import { tokens, getRoleEmoji, formatTokens, formatCost, formatElapsed,
  CopyIcon, DownloadIcon, ChevronDownIcon, ChevronUpIcon, NewChatIcon } from './tokens.jsx';
import { buildDownloadUrl } from './useWebSocket.js';

// Issue #10: escape HTML before applying markdown transforms
function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function inlineMarkdown(text) {
  // Issue #10: escape HTML first, then apply markdown transforms
  let safe = escapeHtml(text);
  return safe
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code style="background:rgba(0,0,0,0.2);padding:1px 5px;border-radius:4px;font-size:12px">$1</code>');
}

// ── Simple markdown renderer ──────────────────────────────────────────────────
function renderMarkdown(text, t, isDark) {
  if (!text) return null;
  const lines = text.split('\n');
  const elements = [];
  let i = 0;

  // Issue #12: track ordered vs unordered list items separately
  let unorderedItems = [];
  let orderedItems = [];

  const flushUnordered = () => {
    if (unorderedItems.length > 0) {
      const items = unorderedItems;
      unorderedItems = [];
      elements.push(
        <ul key={`ul-${i}`} style={{ paddingLeft: 20, margin: '8px 0', color: t.textPrimary }}>
          {items.map((item, j) => (
            <li key={j} style={{ fontSize: 14, lineHeight: 1.6, marginBottom: 4 }}
              dangerouslySetInnerHTML={{ __html: inlineMarkdown(item) }} />
          ))}
        </ul>
      );
    }
  };

  const flushOrdered = () => {
    if (orderedItems.length > 0) {
      const items = orderedItems;
      orderedItems = [];
      elements.push(
        <ol key={`ol-${i}`} style={{ paddingLeft: 20, margin: '8px 0', color: t.textPrimary }}>
          {items.map((item, j) => (
            <li key={j} style={{ fontSize: 14, lineHeight: 1.6, marginBottom: 4 }}
              dangerouslySetInnerHTML={{ __html: inlineMarkdown(item) }} />
          ))}
        </ol>
      );
    }
  };

  // Flush both list types
  const flushLists = () => {
    flushUnordered();
    flushOrdered();
  };

  while (i < lines.length) {
    const line = lines[i];

    // Heading
    const h3 = line.match(/^### (.+)/);
    const h2 = line.match(/^## (.+)/);
    const h1 = line.match(/^# (.+)/);
    if (h1) {
      flushLists();
      // Issue #11: apply inlineMarkdown to heading text
      elements.push(<h1 key={i} style={{ fontSize: 22, fontWeight: 700, color: t.textPrimary, margin: '16px 0 8px' }}
        dangerouslySetInnerHTML={{ __html: inlineMarkdown(h1[1]) }} />);
      i++; continue;
    }
    if (h2) {
      flushLists();
      elements.push(<h2 key={i} style={{ fontSize: 18, fontWeight: 700, color: t.textPrimary, margin: '14px 0 6px' }}
        dangerouslySetInnerHTML={{ __html: inlineMarkdown(h2[1]) }} />);
      i++; continue;
    }
    if (h3) {
      flushLists();
      elements.push(<h3 key={i} style={{ fontSize: 15, fontWeight: 600, color: t.textPrimary, margin: '12px 0 4px' }}
        dangerouslySetInnerHTML={{ __html: inlineMarkdown(h3[1]) }} />);
      i++; continue;
    }

    // Code block
    if (line.startsWith('```')) {
      flushLists();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      elements.push(
        <pre key={i} style={{
          // Issue #15: conditional background for light/dark mode
          background: isDark ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.06)',
          border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.1)'}`,
          borderRadius: 10, padding: '12px 16px', overflowX: 'auto',
          fontSize: 13, color: isDark ? '#e2e8f0' : '#1e293b', lineHeight: 1.6, margin: '8px 0',
          fontFamily: '"JetBrains Mono", "Fira Code", "Courier New", monospace',
        }}>
          <code>{codeLines.join('\n')}</code>
        </pre>
      );
      i++; continue;
    }

    // Issue #12: unordered list item
    if (line.match(/^[-*] (.+)/)) {
      // Flush ordered list if switching types
      flushOrdered();
      const content = line.match(/^[-*] (.+)/)[1];
      unorderedItems.push(content);
      i++; continue;
    }

    // Issue #12: ordered list item
    const numbered = line.match(/^\d+\. (.+)/);
    if (numbered) {
      // Flush unordered list if switching types
      flushUnordered();
      orderedItems.push(numbered[1]);
      i++; continue;
    }

    // Horizontal rule
    if (line.match(/^---+$/)) {
      flushLists();
      elements.push(<hr key={i} style={{ border: 'none', borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'}`, margin: '16px 0' }} />);
      i++; continue;
    }

    // Empty line
    if (line.trim() === '') {
      flushLists();
      elements.push(<div key={i} style={{ height: 8 }} />);
      i++; continue;
    }

    // Normal paragraph
    flushLists();
    elements.push(
      <p key={i} style={{ fontSize: 14, color: t.textPrimary, lineHeight: 1.7, margin: '4px 0' }}
        dangerouslySetInnerHTML={{ __html: inlineMarkdown(line) }} />
    );
    i++;
  }

  flushLists();
  return elements;
}

// ── AgentAccordion ────────────────────────────────────────────────────────────
const AgentAccordion = ({ agentId, agentData, isDark }) => {
  const t = tokens(isDark);
  const [expanded, setExpanded] = useState(false);
  const [hovered, setHovered] = useState(false);

  const score = agentData?.score;
  const scoreColor = score != null
    ? (score >= 7 ? '#4ade80' : score >= 5 ? '#f59e0b' : '#ef4444')
    : t.textSecondary;

  return (
    <div style={{
      borderRadius: 12,
      background: t.cardBg,
      border: `1px solid ${hovered ? 'rgba(0,37,201,0.2)' : t.cardBorder}`,
      backdropFilter: 'blur(10px)',
      marginBottom: 8,
      overflow: 'hidden',
      transition: 'all 0.2s ease',
    }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', padding: '12px 14px',
          display: 'flex', alignItems: 'center', gap: 10,
          background: 'transparent', border: 'none', cursor: 'pointer',
          color: t.textPrimary, textAlign: 'left',
        }}
      >
        <span style={{ fontSize: 16 }}>{getRoleEmoji(agentData?.role)}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: t.textPrimary }}>
            {agentData?.role || agentId}
          </div>
          <div style={{ fontSize: 11, color: t.textSecondary, display: 'flex', gap: 8, marginTop: 2 }}>
            {agentData?.tokens_used && <span>🪙 {formatTokens(agentData.tokens_used)}</span>}
            {agentData?.execution_time_ms && <span>⏱ {formatElapsed(agentData.execution_time_ms)}</span>}
          </div>
        </div>
        {score != null && (
          <span style={{
            fontSize: 12, fontWeight: 700, color: scoreColor,
            padding: '2px 8px', borderRadius: 999,
            background: `${scoreColor}22`,
            border: `1px solid ${scoreColor}44`,
          }}>
            {score.toFixed(1)}/10
          </span>
        )}
        <span style={{ color: t.textSecondary }}>
          {expanded ? <ChevronUpIcon size={14} /> : <ChevronDownIcon size={14} />}
        </span>
      </button>

      {expanded && (
        <div style={{
          padding: '0 14px 12px 14px',
          borderTop: `1px solid ${t.cardBorder}`,
        }}>
          {agentData?.feedback && (
            <div style={{
              fontSize: 12, color: t.textSecondary, fontStyle: 'italic',
              padding: '8px 0', marginBottom: 8,
            }}>
              Quality feedback: {agentData.feedback}
            </div>
          )}
          {agentData?.output && (
            <div style={{
              fontSize: 12, color: t.textSecondary, lineHeight: 1.6,
              background: 'rgba(0,0,0,0.2)',
              padding: '10px 12px', borderRadius: 8,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              maxHeight: 300, overflowY: 'auto',
            }}>
              {typeof agentData.output === 'string'
                ? agentData.output
                : JSON.stringify(agentData.output, null, 2)}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ── Main ResultView ───────────────────────────────────────────────────────────
export default function ResultView({
  result,
  taskText,
  isDark,
  apiBaseUrl,
  onNewTask,
  onRunAgain,
}) {
  const t = tokens(isDark);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState('output'); // output | agents | files

  // Issue #8: check for error result
  const hasError = !!result?.error;

  const synthesis = result?.synthesis || result?.output || '';
  const perAgentQuality = result?.per_agent_quality || {};
  const filesGenerated = result?.files_generated || [];
  const summary = result?.execution_summary || {};

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(synthesis).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [synthesis]);

  const tabs = [
    { id: 'output', label: '📄 Output' },
    { id: 'agents', label: `🤖 Agents (${Object.keys(perAgentQuality).length})` },
    { id: 'files', label: `📁 Files (${filesGenerated.length})` },
  ];

  return (
    <div style={{
      position: 'fixed', inset: 0,
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px 14px 140px',
        display: 'flex', alignItems: 'center', gap: 12,
        background: isDark ? 'rgba(5,7,10,0.85)' : 'rgba(240,244,248,0.85)',
        backdropFilter: 'blur(20px)',
        borderBottom: `1px solid ${t.cardBorder}`,
        flexShrink: 0,
        flexWrap: 'wrap',
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Issue #14: show error or success based on result state */}
          <div style={{
            fontSize: 11,
            color: hasError ? '#ef4444' : '#4ade80',
            fontWeight: 600, marginBottom: 2,
            textTransform: 'uppercase', letterSpacing: '0.5px',
          }}>
            {hasError ? '❌ Task Failed' : '✅ Task Complete'}
          </div>
          <div style={{
            fontSize: 14, fontWeight: 600, color: t.textPrimary,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {taskText}
          </div>
        </div>

        {/* Summary stats */}
        <div style={{ display: 'flex', gap: 12, fontSize: 12, color: t.textSecondary, flexShrink: 0 }}>
          {summary.agent_count > 0 && <span>🤖 {summary.agent_count} agents</span>}
          {summary.total_tokens > 0 && <span>🪙 {formatTokens(summary.total_tokens)}</span>}
          {summary.total_time_ms > 0 && <span>⏱ {formatElapsed(summary.total_time_ms)}</span>}
          {summary.total_cost > 0 && <span>💰 {formatCost(summary.total_tokens)}</span>}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          {!hasError && (
            <button onClick={handleCopy} style={{
              padding: '7px 12px', borderRadius: 8,
              background: copied ? 'rgba(74,222,128,0.15)' : t.cardBg,
              border: `1px solid ${copied ? 'rgba(74,222,128,0.3)' : t.cardBorder}`,
              color: copied ? '#4ade80' : t.textSecondary,
              cursor: 'pointer', fontSize: 12, fontWeight: 500,
              display: 'flex', alignItems: 'center', gap: 5,
              backdropFilter: 'blur(10px)',
              transition: 'all 0.2s ease',
            }}>
              <CopyIcon size={13} />
              {copied ? 'Copied!' : 'Copy'}
            </button>
          )}
          {onRunAgain && (
            <button onClick={onRunAgain} style={{
              padding: '7px 12px', borderRadius: 8,
              background: 'rgba(0,37,201,0.1)',
              border: '1px solid rgba(0,37,201,0.2)',
              color: '#4a6de5', cursor: 'pointer', fontSize: 12, fontWeight: 500,
              display: 'flex', alignItems: 'center', gap: 5,
              backdropFilter: 'blur(10px)',
              transition: 'all 0.2s ease',
            }}>
              ↩ {hasError ? 'Retry' : 'Run Again'}
            </button>
          )}
          {onNewTask && (
            <button onClick={onNewTask} style={{
              padding: '7px 12px', borderRadius: 8,
              background: t.cardBg,
              border: `1px solid ${t.cardBorder}`,
              color: t.textPrimary, cursor: 'pointer', fontSize: 12, fontWeight: 500,
              display: 'flex', alignItems: 'center', gap: 5,
              backdropFilter: 'blur(10px)',
              transition: 'all 0.2s ease',
            }}>
              <NewChatIcon size={13} />
              New Task
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex', gap: 4, padding: '10px 20px 0',
        background: isDark ? 'rgba(5,7,10,0.6)' : 'rgba(240,244,248,0.6)',
        borderBottom: `1px solid ${t.cardBorder}`,
        flexShrink: 0,
      }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '7px 14px', borderRadius: '8px 8px 0 0',
              background: activeTab === tab.id
                ? (isDark ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.8)')
                : 'transparent',
              border: `1px solid ${activeTab === tab.id ? t.cardBorder : 'transparent'}`,
              borderBottom: activeTab === tab.id ? `2px solid #4a6de5` : '2px solid transparent',
              color: activeTab === tab.id ? t.textPrimary : t.textSecondary,
              cursor: 'pointer', fontSize: 13, fontWeight: activeTab === tab.id ? 600 : 400,
              transition: 'all 0.2s ease',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{
        flex: 1, overflowY: 'auto',
        padding: '20px',
        scrollbarWidth: 'thin',
      }}>
        {/* Output tab */}
        {activeTab === 'output' && (
          <div style={{
            maxWidth: 800, margin: '0 auto',
            padding: '20px 24px',
            borderRadius: 16,
            background: t.cardBg,
            border: `1px solid ${hasError ? 'rgba(239,68,68,0.3)' : t.cardBorder}`,
            backdropFilter: 'blur(20px)',
          }}>
            {/* Issue #8: dedicated error state */}
            {hasError ? (
              <div style={{ textAlign: 'center', padding: '20px 0' }}>
                <div style={{ fontSize: 40, marginBottom: 12 }}>❌</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#ef4444', marginBottom: 8 }}>
                  Task Failed
                </div>
                <div style={{ fontSize: 14, color: t.textSecondary, marginBottom: 20, lineHeight: 1.5 }}>
                  {result.error}
                </div>
                {onRunAgain && (
                  <button onClick={onRunAgain} style={{
                    padding: '10px 20px', borderRadius: 10,
                    background: 'rgba(239,68,68,0.12)',
                    border: '1px solid rgba(239,68,68,0.3)',
                    color: '#ef4444', cursor: 'pointer', fontSize: 14, fontWeight: 600,
                  }}>
                    ↩ Retry Task
                  </button>
                )}
              </div>
            ) : synthesis ? (
              renderMarkdown(synthesis, t, isDark)
            ) : (
              <p style={{ color: t.textSecondary, fontStyle: 'italic' }}>No output generated.</p>
            )}
          </div>
        )}

        {/* Agents tab */}
        {activeTab === 'agents' && (
          <div style={{ maxWidth: 720, margin: '0 auto' }}>
            {Object.entries(perAgentQuality).length > 0 ? (
              Object.entries(perAgentQuality).map(([agentId, data]) => (
                <AgentAccordion
                  key={agentId}
                  agentId={agentId}
                  agentData={data}
                  isDark={isDark}
                />
              ))
            ) : (
              <div style={{
                textAlign: 'center', padding: '40px 20px',
                color: t.textSecondary, fontSize: 14,
              }}>
                No agent data available.
              </div>
            )}

            {/* Quality bar chart */}
            {Object.keys(perAgentQuality).length > 0 && (
              <div style={{
                marginTop: 16, padding: '16px 18px',
                borderRadius: 14, background: t.cardBg, border: `1px solid ${t.cardBorder}`,
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: t.textSecondary, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Quality Scores
                </div>
                {Object.entries(perAgentQuality).map(([agentId, data]) => {
                  const score = data?.score;
                  if (score == null) return null;
                  const color = score >= 7 ? '#4ade80' : score >= 5 ? '#f59e0b' : '#ef4444';
                  return (
                    <div key={agentId} style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                        <span style={{ fontSize: 12, color: t.textSecondary, minWidth: 140 }}>
                          {getRoleEmoji(data?.role)} {data?.role?.split(' ').slice(-1)[0] || agentId}
                        </span>
                        <div style={{ flex: 1, height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.06)' }}>
                          <div style={{
                            height: '100%', width: `${(score / 10) * 100}%`,
                            background: color, borderRadius: 4,
                            boxShadow: `0 0 6px ${color}55`,
                            transition: 'width 0.8s cubic-bezier(0.16,1,0.3,1)',
                          }} />
                        </div>
                        <span style={{ fontSize: 12, fontWeight: 700, color, minWidth: 36, textAlign: 'right' }}>
                          {score.toFixed(1)}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Files tab */}
        {activeTab === 'files' && (
          <div style={{ maxWidth: 720, margin: '0 auto' }}>
            {filesGenerated.length > 0 ? (
              filesGenerated.map((filePath, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '12px 16px', marginBottom: 8,
                  borderRadius: 12, background: t.cardBg,
                  border: `1px solid ${t.cardBorder}`,
                }}>
                  <span style={{ fontSize: 16 }}>📄</span>
                  <span style={{ flex: 1, fontSize: 13, color: t.textPrimary, wordBreak: 'break-all' }}>
                    {typeof filePath === 'string' ? filePath : filePath?.original_name || filePath?.filepath || JSON.stringify(filePath)}
                  </span>
                  <a
                    href={buildDownloadUrl(apiBaseUrl, typeof filePath === 'string' ? filePath : filePath?.filepath)}
                    download
                    style={{
                      padding: '6px 12px', borderRadius: 8,
                      background: 'rgba(0,37,201,0.1)',
                      border: '1px solid rgba(0,37,201,0.2)',
                      color: '#4a6de5', fontSize: 12, fontWeight: 500,
                      display: 'flex', alignItems: 'center', gap: 5,
                      textDecoration: 'none',
                    }}
                  >
                    <DownloadIcon size={12} />
                    Download
                  </a>
                </div>
              ))
            ) : (
              <div style={{
                textAlign: 'center', padding: '40px 20px',
                color: t.textSecondary, fontSize: 14,
              }}>
                No files generated for this task.
              </div>
            )}
          </div>
        )}

        <div style={{ height: 40 }} />
      </div>
    </div>
  );
}
