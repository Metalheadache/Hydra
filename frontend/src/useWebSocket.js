// WebSocket hook for connecting to Hydra backend
import { useRef, useCallback, useState } from 'react';

/**
 * Build the WebSocket URL from settings.
 * ALWAYS uses window.location.origin (the Hydra server).
 */
function buildWsUrl() {
  // ALWAYS connect to the Hydra server (same origin), NOT the LLM provider
  const base = window.location.origin;
  return base.replace(/^http/, 'ws').replace(/\/$/, '') + '/ws/task';
}

/**
 * Build the REST base URL for Hydra server endpoints (upload/history/files).
 * ALWAYS uses window.location.origin — apiBaseUrl is for LLM provider config only.
 */
function buildRestUrl() {
  return window.location.origin.replace(/\/$/, '');
}

// ── Error normalization ──────────────────────────────────────────────────────
export function normalizeError(error) {
  const raw = typeof error === 'string' ? { message: error } : (error || {});
  return {
    code: raw.code || 'UNKNOWN',
    message: raw.message || 'An unexpected error occurred',
    source: raw.source || 'unknown', // 'network', 'server', 'llm', 'auth'
    retriable: raw.retriable ?? true,
    timestamp: Date.now(),
  };
}



export function useWebSocket() {
  const wsRef = useRef(null);
  const lastConnectOptsRef = useRef(null);
  const hasActiveTaskRef = useRef(false);
  const intentionalCloseRef = useRef(false);

  // Connection state exposed for UI
  const [connectionState, setConnectionState] = useState('idle');
  // idle | connecting | connected | failed

  /**
   * Internal: create a WebSocket connection. Used by both connect() and reconnect.
   */
  const createConnection = useCallback((opts, isReconnect = false) => {
    const {
      serverToken,
      task,
      files = [],
      configOverrides = {},
      onEvent,
      onError,
      onClose,
      onConnectionStateChange,
    } = opts;

    if (!isReconnect) {
      setConnectionState('connecting');
      onConnectionStateChange?.('connecting');
    }

    const url = buildWsUrl();
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      const normalized = normalizeError({ message: err.message || 'Failed to connect', source: 'network' });
      onError?.(normalized.message);
      setConnectionState('failed');
      onConnectionStateChange?.('failed');
      return;
    }
    wsRef.current = ws;

    let pingInterval = null;

    ws.onopen = () => {
      try {
        setConnectionState('connected');
        setReconnectAttempt(0);
        onConnectionStateChange?.('connected');

        if (serverToken) {
          ws.send(JSON.stringify({ type: 'auth', token: serverToken }));
        }
        // Only send start_task on initial connect, not reconnect
        if (!isReconnect) {
          hasActiveTaskRef.current = true;
          ws.send(JSON.stringify({
            type: 'start_task',
            task,
            files: files.length > 0 ? files : null,
            config_overrides: Object.keys(configOverrides).length > 0 ? configOverrides : undefined,
          }));
        }
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      } catch (err) {
        onError?.(err.message);
      }
    };

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        onEvent?.(event);
        // Mark task as no longer active on completion/error
        if (event.type === 'pipeline_complete' || event.type === 'pipeline_error') {
          hasActiveTaskRef.current = false;
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onerror = () => {
      const normalized = normalizeError({ message: 'WebSocket connection failed', source: 'network' });
      onError?.(normalized.message);
    };

    ws.onclose = (e) => {
      if (pingInterval) clearInterval(pingInterval);
      wsRef.current = null;

      // On unexpected close during an active task, don't silently reconnect
      // (reconnecting can't resume the pipeline — it's 1:1 per WS session).
      // Instead, mark as failed so the user knows to check History for results.
      if (!intentionalCloseRef.current && e.code !== 1000) {
        if (hasActiveTaskRef.current) {
          setConnectionState('failed');
          onConnectionStateChange?.('failed');
          hasActiveTaskRef.current = false;
        } else {
          setConnectionState('idle');
          onConnectionStateChange?.('idle');
        }
      } else {
        setConnectionState('idle');
        onConnectionStateChange?.('idle');
      }
      onClose?.(e.code, e.reason);
    };
  }, []);

  /**
   * Connect to the backend and start a task.
   */
  const connect = useCallback(({
    apiBaseUrl,
    serverToken,
    task,
    files = [],
    configOverrides = {},
    onEvent,
    onError,
    onClose,
    onConnectionStateChange,
  }) => {
    // Close existing connection
    intentionalCloseRef.current = true;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    intentionalCloseRef.current = false;

    const opts = { apiBaseUrl, serverToken, task, files, configOverrides, onEvent, onError, onClose, onConnectionStateChange };
    lastConnectOptsRef.current = opts;
    createConnection(opts, false);
  }, [createConnection]);

  const cancel = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'cancel' }));
    }
  }, []);

  const respondConfirmation = useCallback((confirmationId, approved) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'confirmation_response',
        confirmation_id: confirmationId,
        approved,
      }));
    }
  }, []);

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    hasActiveTaskRef.current = false;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnectionState('idle');
    intentionalCloseRef.current = false;
  }, []);

  /** Retry — re-run the last task from scratch */
  const retry = useCallback(() => {
    if (lastConnectOptsRef.current) {
      setConnectionState('connecting');
      createConnection(lastConnectOptsRef.current, false);
    }
  }, [createConnection]);

  return {
    connect, cancel, respondConfirmation, disconnect, retry,
    connectionState,
  };
}

/**
 * Upload files to /api/upload
 * Returns array of FileAttachment objects from server.
 */
export async function uploadFiles(files, serverToken) {
  const base = buildRestUrl();
  const formData = new FormData();
  for (const f of files) {
    formData.append('files', f.file || f, f.name || 'file');
  }
  const headers = {};
  if (serverToken) headers['X-API-Key'] = serverToken;
  const res = await fetch(`${base}/api/upload`, { method: 'POST', headers, body: formData });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch history list.
 */
export async function fetchHistory(serverToken, limit = 20) {
  const base = buildRestUrl();
  const headers = {};
  if (serverToken) headers['X-API-Key'] = serverToken;
  const res = await fetch(`${base}/api/history?limit=${limit}`, { headers });
  if (!res.ok) throw new Error(`History fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch single history run.
 */
export async function fetchHistoryRun(serverToken, taskId) {
  const base = buildRestUrl();
  const headers = {};
  if (serverToken) headers['X-API-Key'] = serverToken;
  const res = await fetch(`${base}/api/history/${taskId}`, { headers });
  if (!res.ok) throw new Error(`Run fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Delete a history run.
 */
export async function deleteHistoryRun(serverToken, taskId) {
  const base = buildRestUrl();
  const headers = {};
  if (serverToken) headers['X-API-Key'] = serverToken;
  const res = await fetch(`${base}/api/history/${taskId}`, { method: 'DELETE', headers });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
  return res.json();
}

/**
 * Download file URL builder.
 * TODO: The backend /api/download endpoint does not exist yet.
 * Files are served from output_dir on the server.
 * Using /api/files/ as a placeholder until the endpoint is implemented.
 */
export function buildDownloadUrl(filePath) {
  const base = buildRestUrl();
  const cleanPath = typeof filePath === 'string' ? filePath : String(filePath);
  // Encode each path segment separately to preserve directory structure
  const encoded = cleanPath.split('/').map(seg => encodeURIComponent(seg)).join('/');
  return `${base}/api/files/${encoded}`;
}
