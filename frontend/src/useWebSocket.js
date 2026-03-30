// WebSocket hook for connecting to Hydra backend
import { useRef, useCallback } from 'react';

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

export function useWebSocket() {
  const wsRef = useRef(null);

  /**
   * Connect to the backend and start a task.
   *
   * @param {object} options
   * @param {string} options.apiBaseUrl
   * @param {string} options.serverToken  — optional auth token
   * @param {string} options.task
   * @param {string[]} options.files      — file paths from upload API
   * @param {object} options.configOverrides
   * @param {function} options.onEvent    — called with each HydraEvent object
   * @param {function} options.onError    — called on error
   * @param {function} options.onClose    — called when socket closes
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
  }) => {
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const url = buildWsUrl();
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      onError?.(err.message || 'Failed to connect');
      return;
    }
    wsRef.current = ws;

    // Keepalive ping every 30s to prevent proxy/browser from killing idle WS
    let pingInterval = null;

    ws.onopen = () => {
      try {
        // Send auth first if token configured
        if (serverToken) {
          ws.send(JSON.stringify({ type: 'auth', token: serverToken }));
        }
        // Send start_task
        ws.send(JSON.stringify({
          type: 'start_task',
          task,
          files: files.length > 0 ? files : null,
          config_overrides: Object.keys(configOverrides).length > 0 ? configOverrides : undefined,
        }));
        // Start keepalive
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
      } catch {
        // ignore parse errors
      }
    };

    ws.onerror = () => {
      onError?.('WebSocket connection failed');
    };

    ws.onclose = (e) => {
      if (pingInterval) clearInterval(pingInterval);
      wsRef.current = null;
      onClose?.(e.code, e.reason);
    };
  }, []);

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
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  return { connect, cancel, respondConfirmation, disconnect };
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
