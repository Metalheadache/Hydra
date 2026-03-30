import React, { useState, useEffect, useRef, useCallback } from 'react';
import { tokens, getRoleEmoji, formatTokens, formatCost, formatElapsed,
  ChevronDownIcon, ChevronUpIcon } from './tokens.jsx';

// ─── BrainPanel ───────────────────────────────────────────────────────────────
export const BrainPanel = ({ brainState, plan, isDark }) => {
  const t = tokens(isDark);
  const [visible, setVisible] = useState(false);
  useEffect(() => { setTimeout(() => setVisible(true), 50); }, []);

  const isPlanning = brainState === 'planning';
  const isDone = brainState === 'complete';

  return (
    <div style={{
      padding: '14px 18px',
      borderRadius: 16,
      background: t.cardBg,
      border: `1px solid ${isDone ? 'rgba(74,222,128,0.25)' : isPlanning ? 'rgba(0,37,201,0.3)' : t.cardBorder}`,
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      boxShadow: isPlanning
        ? '0 0 20px rgba(0,37,201,0.15), inset 0 1px 1px rgba(255,255,255,0.08)'
        : 'inset 0 1px 1px rgba(255,255,255,0.06)',
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0)' : 'translateY(12px)',
      transition: 'all 0.5s cubic-bezier(0.16,1,0.3,1)',
      marginBottom: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{
          fontSize: 18,
          display: 'inline-block',
          animation: isPlanning ? 'hydra-pulse 1.4s ease-in-out infinite' : 'none',
        }}>🧠</span>
        <div style={{ flex: 1 }}>
          {isPlanning ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: t.textPrimary }}>Planning...</span>
              <div style={{ display: 'flex', gap: 3 }}>
                {[0, 1, 2].map(i => (
                  <div key={i} style={{
                    width: 5, height: 5, borderRadius: '50%',
                    background: '#4a6de5',
                    animation: `hydra-dot-bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
                  }} />
                ))}
              </div>
            </div>
          ) : isDone && plan ? (
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: t.textPrimary, marginBottom: 4 }}>
                ✅ {plan.sub_tasks?.length ?? 0} sub-tasks • {plan.execution_groups?.length ?? 0} groups
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {plan.agent_specs?.map(spec => (
                  <span key={spec.agent_id} style={{
                    fontSize: 11, padding: '2px 8px', borderRadius: 999,
                    background: 'rgba(0,37,201,0.1)',
                    border: '1px solid rgba(0,37,201,0.2)',
                    color: '#4a6de5',
                  }}>
                    {getRoleEmoji(spec.role)} {spec.role.split(' ').slice(-1)[0]}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <span style={{ fontSize: 14, color: t.textSecondary }}>Brain Model</span>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── AgentCard ────────────────────────────────────────────────────────────────
export const AgentCard = ({ agent, isDark }) => {
  const t = tokens(isDark);
  const [expanded, setExpanded] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => { setTimeout(() => setVisible(true), 80); }, []);

  const statusConfig = {
    pending:   { badge: '⏳', color: t.textSecondary, bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.2)' },
    running:   { badge: '🔄', color: '#4a6de5', bg: 'rgba(74,109,229,0.1)', border: 'rgba(74,109,229,0.3)' },
    completed: { badge: '✅', color: '#4ade80', bg: 'rgba(74,222,128,0.1)', border: 'rgba(74,222,128,0.25)' },
    failed:    { badge: '❌', color: '#ef4444', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.25)' },
    retrying:  { badge: '🔄', color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.25)' },
  };

  const cfg = statusConfig[agent.status] || statusConfig.pending;
  const isRunning = agent.status === 'running';
  const isDone = agent.status === 'completed' || agent.status === 'failed';

  const progressPct = agent.estimatedTokens > 0
    ? Math.min(100, (agent.tokensUsed / agent.estimatedTokens) * 100)
    : (isRunning ? null : (isDone ? 100 : 0));

  const scoreColor = agent.qualityScore != null
    ? (agent.qualityScore >= 7 ? '#4ade80' : agent.qualityScore >= 5 ? '#f59e0b' : '#ef4444')
    : null;

  return (
    <div style={{
      flex: '1 1 220px', minWidth: 200, maxWidth: 300,
      padding: '14px 14px 12px 14px',
      borderRadius: 14,
      background: t.cardBg,
      border: `1px solid ${isRunning ? cfg.border : t.cardBorder}`,
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      boxShadow: isRunning
        ? `0 0 16px ${cfg.bg}, inset 0 1px 1px rgba(255,255,255,0.08)`
        : 'inset 0 1px 1px rgba(255,255,255,0.05)',
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0) scale(1)' : 'translateY(10px) scale(0.97)',
      transition: 'all 0.5s cubic-bezier(0.16,1,0.3,1), border-color 0.3s ease, box-shadow 0.3s ease',
      cursor: agent.output ? 'pointer' : 'default',
    }} onClick={() => agent.output && setExpanded(e => !e)}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 16 }}>{getRoleEmoji(agent.role)}</span>
        <span style={{
          flex: 1, fontSize: 13, fontWeight: 600, color: t.textPrimary,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {agent.role || 'Agent'}
        </span>
        {/* Status badge */}
        <span style={{
          fontSize: 10, padding: '2px 7px', borderRadius: 999, fontWeight: 600,
          background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.color,
          whiteSpace: 'nowrap',
        }}>
          {cfg.badge} {agent.status}
          {/* Issue #9: retrying badge */}
          {agent.status === 'retrying' && (
            <span style={{ marginLeft: 4, fontSize: 9, opacity: 0.8 }}>↺</span>
          )}
        </span>
      </div>

      {/* Current activity */}
      {isRunning && agent.currentTool && (
        <div style={{
          fontSize: 11, color: '#4a6de5', marginBottom: 6,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          🔧 {agent.currentTool}
        </div>
      )}
      {isRunning && agent.tokenPreview && (
        <div style={{
          fontSize: 11, color: t.textSecondary, marginBottom: 6,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          fontStyle: 'italic',
        }}>
          {agent.tokenPreview.slice(-80)}
        </div>
      )}

      {/* Progress bar */}
      <div style={{
        height: 3, borderRadius: 2,
        background: 'rgba(255,255,255,0.06)',
        marginBottom: 8, overflow: 'hidden',
      }}>
        {progressPct !== null ? (
          <div style={{
            height: '100%', width: `${progressPct}%`,
            background: isDone
              ? (agent.status === 'failed' ? '#ef4444' : 'linear-gradient(90deg, #4ade80, #22d3ee)')
              : 'linear-gradient(90deg, #4a6de5, #0025C9)',
            borderRadius: 2,
            transition: 'width 0.3s ease',
            boxShadow: isDone ? 'none' : '0 0 6px rgba(0,37,201,0.4)',
          }} />
        ) : isRunning ? (
          <div style={{
            height: '100%', width: '40%',
            background: 'linear-gradient(90deg, transparent, #4a6de5, transparent)',
            borderRadius: 2,
            animation: 'hydra-shimmer 1.5s ease-in-out infinite',
          }} />
        ) : null}
      </div>

      {/* Footer stats */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: t.textSecondary }}>
        {agent.tokensUsed > 0 && (
          <span>🪙 {formatTokens(agent.tokensUsed)}</span>
        )}
        {agent.executionTimeMs > 0 && (
          <span>⏱ {formatElapsed(agent.executionTimeMs)}</span>
        )}
        {agent.qualityScore != null && (
          <span style={{
            marginLeft: 'auto', fontWeight: 700, fontSize: 12,
            color: scoreColor,
            padding: '1px 6px', borderRadius: 999,
            background: `${scoreColor}22`,
          }}>
            {agent.qualityScore.toFixed(1)}/10
          </span>
        )}
        {agent.output && (
          <span style={{ marginLeft: agent.qualityScore != null ? 4 : 'auto', color: '#4a6de5' }}>
            {expanded ? <ChevronUpIcon size={12} /> : <ChevronDownIcon size={12} />}
          </span>
        )}
      </div>

      {/* Expanded output */}
      {expanded && agent.output && (
        <div style={{
          marginTop: 10,
          padding: '10px 12px',
          borderRadius: 10,
          background: isDark ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.05)',
          border: `1px solid ${t.cardBorder}`,
          fontSize: 12, color: t.textSecondary,
          lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          maxHeight: 200, overflowY: 'auto',
        }}>
          {typeof agent.output === 'string' ? agent.output : JSON.stringify(agent.output, null, 2)}
        </div>
      )}
    </div>
  );
};

// ─── GroupPanel ───────────────────────────────────────────────────────────────
export const GroupPanel = ({ groupIndex, groupData, agents, status, isDark }) => {
  const t = tokens(isDark);
  const [visible, setVisible] = useState(false);
  useEffect(() => { setTimeout(() => setVisible(true), groupIndex * 80 + 100); }, [groupIndex]);

  const isActive = status === 'running';
  const isWaiting = status === 'waiting';
  const isDone = status === 'complete';

  const label = groupData?.parallel !== false ? 'Parallel' : 'Sequential';

  return (
    <div style={{
      marginBottom: 16,
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0)' : 'translateY(14px)',
      transition: 'all 0.5s cubic-bezier(0.16,1,0.3,1)',
    }}>
      {/* Group header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
        padding: '8px 14px',
        borderRadius: 10,
        background: isActive
          ? 'rgba(0,37,201,0.08)'
          : isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.04)',
        border: `1px solid ${isActive ? 'rgba(0,37,201,0.25)' : isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'}`,
        transition: 'all 0.3s ease',
      }}>
        <span style={{ fontSize: 15 }}>⚡</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: t.textPrimary }}>
          Group {groupIndex + 1} — {label}
        </span>
        {isWaiting && (
          <span style={{ fontSize: 11, color: t.textSecondary, marginLeft: 4 }}>
            ⏳ Waiting for Group {groupIndex}...
          </span>
        )}
        {isDone && (
          <span style={{ fontSize: 11, color: '#4ade80', marginLeft: 4 }}>✓ Done</span>
        )}
        <div style={{
          marginLeft: 'auto', fontSize: 11, color: t.textSecondary,
        }}>
          {agents.length} agent{agents.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Agent cards */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, paddingLeft: 4 }}>
        {agents.map(agent => (
          <AgentCard key={agent.agentId} agent={agent} isDark={isDark} />
        ))}
      </div>
    </div>
  );
};

// ─── QualityBar ───────────────────────────────────────────────────────────────
export const QualityBar = ({ scores, isDark }) => {
  const t = tokens(isDark);
  const [visible, setVisible] = useState(false);
  useEffect(() => { setTimeout(() => setVisible(true), 100); }, []);

  if (!scores || Object.keys(scores).length === 0) return null;

  return (
    <div style={{
      padding: '14px 18px',
      borderRadius: 14,
      background: t.cardBg,
      border: `1px solid ${t.cardBorder}`,
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      marginBottom: 12,
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0)' : 'translateY(10px)',
      transition: 'all 0.5s cubic-bezier(0.16,1,0.3,1)',
    }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: t.textSecondary, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        📊 Quality Scores
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {Object.entries(scores).map(([agentId, scoreData]) => {
          const score = typeof scoreData === 'object' ? scoreData.score : scoreData;
          const feedback = typeof scoreData === 'object' ? scoreData.feedback : '';
          const color = score >= 7 ? '#4ade80' : score >= 5 ? '#f59e0b' : '#ef4444';
          const role = typeof scoreData === 'object' ? scoreData.role : agentId;

          return (
            <div key={agentId} title={feedback}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: t.textSecondary, minWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {getRoleEmoji(role)} {typeof role === 'string' ? role.split(' ').slice(-1)[0] : agentId}
                </span>
                <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${(score / 10) * 100}%`,
                    background: color,
                    borderRadius: 3,
                    boxShadow: `0 0 6px ${color}55`,
                    transition: 'width 0.8s cubic-bezier(0.16,1,0.3,1)',
                  }} />
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color, minWidth: 36, textAlign: 'right' }}>
                  {score.toFixed(1)}
                </span>
              </div>
              {feedback && (
                <div style={{ fontSize: 11, color: t.textSecondary, paddingLeft: 128, fontStyle: 'italic', marginBottom: 2 }}>
                  {feedback.slice(0, 80)}{feedback.length > 80 ? '...' : ''}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ─── SynthesisPanel ───────────────────────────────────────────────────────────
export const SynthesisPanel = ({ text, isStreaming, isDark }) => {
  const t = tokens(isDark);
  const [visible, setVisible] = useState(false);
  const scrollRef = useRef(null);
  useEffect(() => { setTimeout(() => setVisible(true), 80); }, []);

  useEffect(() => {
    if (isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [text, isStreaming]);

  if (!text && !isStreaming) return null;

  return (
    <div style={{
      padding: '14px 18px',
      borderRadius: 14,
      background: t.cardBg,
      border: `1px solid ${isStreaming ? 'rgba(0,37,201,0.25)' : t.cardBorder}`,
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      boxShadow: isStreaming ? '0 0 20px rgba(0,37,201,0.1)' : 'none',
      marginBottom: 12,
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0)' : 'translateY(10px)',
      transition: 'all 0.5s cubic-bezier(0.16,1,0.3,1), border-color 0.3s ease',
    }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: t.textSecondary, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        📝 Synthesis
      </div>
      <div
        ref={scrollRef}
        style={{
          maxHeight: 240, overflowY: 'auto',
          fontSize: 14, color: t.textPrimary, lineHeight: 1.7,
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          scrollbarWidth: 'thin',
        }}
      >
        {text}
        {isStreaming && (
          <span style={{
            display: 'inline-block', width: 2, height: 14, background: '#4a6de5',
            marginLeft: 2, borderRadius: 1, verticalAlign: 'text-bottom',
            animation: 'hydra-cursor-blink 0.8s ease-in-out infinite',
          }} />
        )}
      </div>
    </div>
  );
};

// ─── StatusBar ────────────────────────────────────────────────────────────────
export const StatusBar = ({ startTime, totalTokens, isDark }) => {
  const t = tokens(isDark);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed(Date.now() - startTime);
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime]);

  return (
    <div style={{
      position: 'sticky', bottom: 0,
      padding: '10px 18px',
      display: 'flex', alignItems: 'center', gap: 16,
      background: isDark ? 'rgba(5,7,10,0.9)' : 'rgba(240,244,248,0.9)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      borderTop: `1px solid ${t.cardBorder}`,
      fontSize: 12, color: t.textSecondary,
      flexWrap: 'wrap',
    }}>
      <span>⏱ {formatElapsed(elapsed)}</span>
      <span>🪙 {formatTokens(totalTokens)} tokens</span>
      <span>💰 {formatCost(totalTokens)}</span>
    </div>
  );
};

// ─── Confirmation Modal ───────────────────────────────────────────────────────
export const ConfirmationModal = ({ data, onApprove, onReject, isDark }) => {
  const t = tokens(isDark);

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 3000,
      background: 'rgba(0,0,0,0.6)',
      backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }}>
      <div style={{
        maxWidth: 480, width: '100%',
        padding: '24px',
        borderRadius: 20,
        background: t.panelBg,
        border: `1px solid ${t.panelBorder}`,
        backdropFilter: 'blur(40px)',
        WebkitBackdropFilter: 'blur(40px)',
        boxShadow: '0 0 60px rgba(0,0,0,0.8)',
      }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: t.textPrimary, marginBottom: 8 }}>
          ⚠️ Confirmation Required
        </div>
        <div style={{ fontSize: 13, color: t.textSecondary, marginBottom: 16, lineHeight: 1.5 }}>
          Agent wants to use <strong style={{ color: t.textPrimary }}>{data?.tool_name}</strong>:
        </div>
        {data?.args && (
          <pre style={{
            fontSize: 12, color: t.textSecondary,
            background: isDark ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.05)',
            padding: '10px 12px', borderRadius: 10,
            overflow: 'auto', maxHeight: 200,
            marginBottom: 20,
            border: `1px solid ${t.cardBorder}`,
          }}>
            {JSON.stringify(data.args, null, 2)}
          </pre>
        )}
        <div style={{ display: 'flex', gap: 10 }}>
          {/* Issue #3: wire approve/reject to callbacks that also clear pendingConfirmation */}
          <button onClick={onApprove} style={{
            flex: 1, padding: '10px', borderRadius: 10, border: 'none', cursor: 'pointer',
            background: 'rgba(74,222,128,0.2)', color: '#4ade80',
            fontWeight: 600, fontSize: 14,
            border: '1px solid rgba(74,222,128,0.3)',
            transition: 'all 0.2s ease',
          }}>
            ✅ Approve
          </button>
          <button onClick={onReject} style={{
            flex: 1, padding: '10px', borderRadius: 10, border: 'none', cursor: 'pointer',
            background: 'rgba(239,68,68,0.15)', color: '#ef4444',
            fontWeight: 600, fontSize: 14,
            border: '1px solid rgba(239,68,68,0.3)',
            transition: 'all 0.2s ease',
          }}>
            ❌ Reject
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Main OrchestrationView ───────────────────────────────────────────────────
export default function OrchestrationView({
  taskText,
  events,
  isDark,
  onCancel,
  isCancelling,
  onConfirmationApprove,
  onConfirmationReject,
  connectionState,
  onRetryPipeline,
}) {
  const t = tokens(isDark);

  // Derived state from events
  const [brainState, setBrainState] = useState('idle'); // idle | planning | complete
  const [plan, setPlan] = useState(null);
  const [groups, setGroups] = useState([]); // [{groupIndex, data, status, agentIds}]
  const [agentMap, setAgentMap] = useState({}); // agentId → agent state
  const [qualityScores, setQualityScores] = useState({});
  const [showQuality, setShowQuality] = useState(false);
  const [synthesisText, setSynthesisText] = useState('');
  const [isSynthesizing, setIsSynthesizing] = useState(false);
  const [totalTokens, setTotalTokens] = useState(0);
  const [startTime] = useState(() => Date.now());
  const [pendingConfirmation, setPendingConfirmation] = useState(null);
  // Issue #9: pipeline error state
  const [pipelineError, setPipelineError] = useState(null);
  const lastEventRef = useRef(null);
  const scrollRef = useRef(null);

  // Issue #5: token buffer ref to accumulate tokens and flush at 5/sec (200ms)
  const tokenBufferRef = useRef({}); // agentId → { tokens_n, latestPreview }

  // Issue #4 & #5: use useRef for processEvent to avoid stale closures and infinite loops
  const processEventRef = useRef(null);

  processEventRef.current = useCallback((event) => {
    const type = event.type;

    // Issue #9: pipeline_start — brain_start covers it, but acknowledge it
    if (type === 'pipeline_start') {
      // pipeline_start is a no-op here; brain_start event handles UI initialization
      return;
    }
    else if (type === 'brain_start') {
      setBrainState('planning');
    }
    else if (type === 'brain_complete') {
      setBrainState('complete');
      const p = event.data;
      setPlan(p);
      // Initialize groups from plan
      if (p?.execution_groups) {
        const initialGroups = p.execution_groups.map((subTaskIds, idx) => ({
          groupIndex: idx,
          data: { parallel: true, sub_task_ids: subTaskIds },
          status: 'waiting',
          agentIds: [],
        }));

        // Initialize agents from specs — use functional updater (Issue #4)
        const agentInitial = {};
        p.agent_specs?.forEach(spec => {
          agentInitial[spec.agent_id] = {
            agentId: spec.agent_id,
            role: spec.role,
            status: 'pending',
            tokensUsed: 0,
            estimatedTokens: Array.isArray(p.sub_tasks) ? (p.sub_tasks.find(st => st.id === spec.sub_task_id)?.estimated_tokens || 2000) : 2000,
            executionTimeMs: 0,
            qualityScore: null,
            currentTool: null,
            tokenPreview: '',
            output: null,
            subTaskId: spec.sub_task_id,
          };
        });
        setAgentMap(agentInitial);

        // Wire agents to groups
        setGroups(initialGroups.map((g, idx) => {
          const subTaskIds = p.execution_groups[idx];
          const agentIds = p.agent_specs
            ?.filter(spec => subTaskIds.includes(spec.sub_task_id))
            .map(spec => spec.agent_id) || [];
          return { ...g, agentIds };
        }));
      }
    }
    else if (type === 'group_start') {
      const gi = event.group_index ?? event.data?.group_index ?? 0;
      const parallel = event.data?.parallel !== false;
      // Issue #4: functional updater
      setGroups(prev => prev.map(g =>
        g.groupIndex === gi
          ? { ...g, status: 'running', data: { ...g.data, parallel } }
          : g
      ));
    }
    else if (type === 'group_complete') {
      const gi = event.group_index ?? event.data?.group_index ?? 0;
      setGroups(prev => prev.map(g =>
        g.groupIndex === gi ? { ...g, status: 'complete' } : g
      ));
    }
    else if (type === 'agent_start') {
      const agentId = event.agent_id || event.data?.agent_id;
      const role = event.data?.role || event.data?.agent_spec?.role;
      // Issue #4: functional updater — no direct read of agentMap
      setAgentMap(prev => ({
        ...prev,
        [agentId]: {
          ...(prev[agentId] || {}),
          agentId,
          role: role || prev[agentId]?.role || 'Agent',
          status: 'running',
          startTime: Date.now(),
        },
      }));
    }
    else if (type === 'agent_tool_call') {
      const agentId = event.agent_id;
      const toolName = event.data?.tool_name;
      const args = event.data?.args;
      const argStr = args ? `(${Object.values(args).slice(0, 1).join(', ').slice(0, 40)})` : '';
      setAgentMap(prev => ({
        ...prev,
        [agentId]: { ...(prev[agentId] || {}), currentTool: `${toolName}${argStr}` },
      }));
    }
    else if (type === 'agent_token') {
      // Issue #5: accumulate tokens in ref, not state — flush via interval
      const agentId = event.agent_id;
      const token = event.data?.token || '';
      const tokens_n = event.tokens || 1;
      const buf = tokenBufferRef.current[agentId] || { tokens_n: 0, latestPreview: '' };
      buf.tokens_n += tokens_n;
      buf.latestPreview = (buf.latestPreview + token).slice(-100);
      tokenBufferRef.current[agentId] = buf;
      // Also accumulate total tokens in ref
      if (!tokenBufferRef.current.__total) tokenBufferRef.current.__total = 0;
      tokenBufferRef.current.__total += tokens_n;
    }
    else if (type === 'agent_complete') {
      const agentId = event.agent_id || event.data?.agent_id;
      const data = event.data || {};
      setAgentMap(prev => ({
        ...prev,
        [agentId]: {
          ...(prev[agentId] || {}),
          agentId,
          status: data.status || 'completed',
          output: data.output,
          tokensUsed: data.tokens_used || event.tokens || prev[agentId]?.tokensUsed || 0,
          executionTimeMs: data.execution_time_ms || 0,
          currentTool: null,
        },
      }));
      if (event.tokens) setTotalTokens(prev => prev + event.tokens);
    }
    else if (type === 'agent_error') {
      const agentId = event.agent_id;
      setAgentMap(prev => ({
        ...prev,
        [agentId]: { ...(prev[agentId] || {}), status: 'failed', error: event.data?.error },
      }));
    }
    else if (type === 'agent_retry') {
      const agentId = event.agent_id;
      setAgentMap(prev => ({
        ...prev,
        [agentId]: { ...(prev[agentId] || {}), status: 'retrying' },
      }));
    }
    // Issue #9: quality_retry — mark agent as retrying with visual badge
    else if (type === 'quality_retry') {
      const agentId = event.agent_id || event.data?.agent_id;
      if (agentId) {
        setAgentMap(prev => ({
          ...prev,
          [agentId]: { ...(prev[agentId] || {}), status: 'retrying' },
        }));
      }
    }
    // Issue #9: file_processed — ignore with explanation comment
    // file_processed events track individual file processing within an agent task.
    // The OrchestrationView doesn't display file-level granularity; agent progress covers it.
    else if (type === 'file_processed') {
      // intentionally ignored — agent-level status tracks progress
    }
    // Issue #9: pipeline_error — show error banner
    else if (type === 'pipeline_error') {
      const errMsg = event.data?.error || 'An unknown pipeline error occurred.';
      setPipelineError(errMsg);
    }
    else if (type === 'quality_start') {
      setShowQuality(true);
    }
    else if (type === 'quality_score') {
      const agentId = event.agent_id;
      const score = event.data?.score;
      const feedback = event.data?.feedback || '';
      // Issue #4: get role from event data itself (no direct agentMap read)
      const role = event.data?.role || agentId;
      setQualityScores(prev => ({
        ...prev,
        [agentId]: { score, feedback, role },
      }));
      setAgentMap(prev => ({
        ...prev,
        [agentId]: { ...(prev[agentId] || {}), qualityScore: score },
      }));
    }
    else if (type === 'synthesis_start') {
      setIsSynthesizing(true);
    }
    else if (type === 'synthesis_token') {
      const token = event.data?.token || '';
      setSynthesisText(prev => prev + token);
      if (event.tokens) setTotalTokens(prev => prev + event.tokens);
    }
    else if (type === 'synthesis_complete') {
      setIsSynthesizing(false);
    }
    else if (type === 'confirmation_required') {
      setPendingConfirmation(event.data);
    }
    else if (type === 'confirmation_response') {
      setPendingConfirmation(null);
    }
  }, []); // empty deps — all state updates use functional updaters (Issue #4)

  // Process incoming events
  useEffect(() => {
    if (!events || events.length === 0) return;
    const latestEvents = events.slice(lastEventRef.current || 0);
    lastEventRef.current = events.length;

    for (const event of latestEvents) {
      processEventRef.current(event);
    }
  }, [events]); // processEvent via ref — no stale closure issue (Issue #4)

  // M1: flush token buffer every 200ms — only update tokenPreview for display.
  // Token counting (tokensUsed, totalTokens) is authoritative from agent_complete events only.
  useEffect(() => {
    const interval = setInterval(() => {
      const buf = tokenBufferRef.current;
      const agentIds = Object.keys(buf).filter(k => k !== '__total');
      if (agentIds.length === 0) return;

      if (agentIds.length > 0) {
        setAgentMap(prev => {
          const next = { ...prev };
          for (const agentId of agentIds) {
            const entry = buf[agentId];
            if (!entry) continue;
            const agent = prev[agentId] || {};
            next[agentId] = {
              ...agent,
              // Only update tokenPreview — do NOT accumulate tokensUsed here
              // (authoritative count comes from agent_complete event)
              tokenPreview: entry.latestPreview,
            };
          }
          return next;
        });
      }

      // Do NOT accumulate __total from streaming tokens — only agent_complete counts
      // Clear the buffer after flush
      tokenBufferRef.current = {};
    }, 200);
    return () => clearInterval(interval);
  }, []);

  // Scroll to bottom as content grows
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [groups, synthesisText, showQuality]);

  const [hoveredCancel, setHoveredCancel] = useState(false);

  return (
    <div style={{
      position: 'fixed', inset: 0,
      display: 'flex', flexDirection: 'column',
      background: 'transparent',
    }}>
      {/* Task header */}
      <div style={{
        padding: '16px 24px 16px 140px',
        display: 'flex', alignItems: 'center', gap: 12,
        background: isDark ? 'rgba(5,7,10,0.85)' : 'rgba(240,244,248,0.85)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderBottom: `1px solid ${t.cardBorder}`,
        flexShrink: 0,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 11, color: t.textSecondary, fontWeight: 500, marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Active Task
          </div>
          <div style={{
            fontSize: 14, fontWeight: 600, color: t.textPrimary,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {taskText}
          </div>
        </div>

        {/* Cancel button */}
        <button
          onClick={onCancel}
          onMouseEnter={() => setHoveredCancel(true)}
          onMouseLeave={() => setHoveredCancel(false)}
          disabled={isCancelling}
          style={{
            flexShrink: 0,
            padding: '8px 16px', borderRadius: 10,
            background: hoveredCancel ? 'rgba(239,68,68,0.2)' : 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
            color: '#ef4444', cursor: isCancelling ? 'default' : 'pointer',
            fontSize: 13, fontWeight: 600,
            backdropFilter: 'blur(10px)',
            transition: 'all 0.2s ease',
            display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          <svg viewBox="0 0 24 24" width={14} height={14} stroke="currentColor" strokeWidth="2" fill="none">
            <rect x="3" y="3" width="18" height="18" rx="2" />
          </svg>
          {isCancelling ? 'Cancelling...' : 'Cancel'}
        </button>
      </div>

      {/* Issue #9: pipeline error banner */}
      {pipelineError && (
        <div style={{
          padding: '12px 20px',
          background: 'rgba(239,68,68,0.12)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderTop: 'none',
          color: '#ef4444', fontSize: 13, fontWeight: 500,
          display: 'flex', alignItems: 'center', gap: 10,
          flexShrink: 0,
        }}>
          <span>⚠️ Pipeline Error:</span>
          <span style={{ flex: 1 }}>{pipelineError}</span>
          {onRetryPipeline && (
            <button onClick={onRetryPipeline} style={{
              padding: '4px 12px', borderRadius: 6,
              background: 'rgba(239,68,68,0.2)', border: '1px solid rgba(239,68,68,0.4)',
              color: '#ef4444', cursor: 'pointer', fontSize: 12, fontWeight: 600,
            }}>
              Try Again
            </button>
          )}
          <button onClick={() => setPipelineError(null)} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#ef4444', fontSize: 16, lineHeight: 1, padding: 0,
          }}>×</button>
        </div>
      )}

      {/* Connection lost during pipeline */}
      {(connectionState === 'reconnecting' || connectionState === 'failed') && !pipelineError && (
        <div style={{
          padding: '12px 20px',
          background: connectionState === 'failed' ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)',
          border: `1px solid ${connectionState === 'failed' ? 'rgba(239,68,68,0.3)' : 'rgba(245,158,11,0.3)'}`,
          borderTop: 'none',
          color: connectionState === 'failed' ? '#ef4444' : '#f59e0b',
          fontSize: 13, fontWeight: 500,
          display: 'flex', alignItems: 'center', gap: 10,
          flexShrink: 0,
        }}>
          <span>{connectionState === 'failed' ? '⚠️' : '🔄'}</span>
          <span style={{ flex: 1 }}>
            {connectionState === 'failed'
              ? 'Connection lost during execution. Partial results may be available.'
              : 'Connection lost during execution. Attempting to reconnect...'}
          </span>
        </div>
      )}

      {/* Scrollable content */}
      <div
        ref={scrollRef}
        style={{
          flex: 1, overflowY: 'auto',
          padding: '16px 20px',
          scrollbarWidth: 'thin',
        }}
      >
        {/* Brain panel */}
        {(brainState !== 'idle') && (
          <BrainPanel brainState={brainState} plan={plan} isDark={isDark} />
        )}

        {/* Group panels */}
        {groups.map((group) => {
          const agents = group.agentIds.map(id => agentMap[id]).filter(Boolean);
          return (
            <GroupPanel
              key={group.groupIndex}
              groupIndex={group.groupIndex}
              groupData={group.data}
              agents={agents}
              status={group.status}
              isDark={isDark}
            />
          );
        })}

        {/* Quality bar */}
        {showQuality && (
          <QualityBar
            scores={qualityScores}
            isDark={isDark}
          />
        )}

        {/* Synthesis panel */}
        {(synthesisText || isSynthesizing) && (
          <SynthesisPanel
            text={synthesisText}
            isStreaming={isSynthesizing}
            isDark={isDark}
          />
        )}

        {/* Bottom padding */}
        <div style={{ height: 60 }} />
      </div>

      {/* Status bar */}
      <StatusBar startTime={startTime} totalTokens={totalTokens} isDark={isDark} />

      {/* Confirmation modal — Issue #3: wired to onConfirmationApprove/Reject props */}
      {pendingConfirmation && (
        <ConfirmationModal
          data={pendingConfirmation}
          isDark={isDark}
          onApprove={() => {
            onConfirmationApprove?.(pendingConfirmation.confirmation_id);
            setPendingConfirmation(null);
          }}
          onReject={() => {
            onConfirmationReject?.(pendingConfirmation.confirmation_id);
            setPendingConfirmation(null);
          }}
        />
      )}
    </div>
  );
}
