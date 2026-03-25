// WebSocket hook for connecting to Hydra backend
import { useRef, useCallback } from 'react';

/**
 * Build the WebSocket URL from settings.
 * Falls back to window.location.origin if apiBaseUrl is empty.
 */
function buildWsUrl(apiBaseUrl) {
  const base = apiBaseUrl || window.location.origin;
  // http:// → ws://, https:// → wss://
  return base.replace(/^http/, 'ws').replace(/\/$/, '') + '/ws/task';
}

/**
 * Build the REST base URL for upload/history endpoints.
 */
function buildRestUrl(apiBaseUrl) {
  return (apiBaseUrl || window.location.origin).replace(/\/$/, '');
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

    const url = buildWsUrl(apiBaseUrl);
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      onError?.(err.message || 'Failed to connect');
      return;
    }
    wsRef.current = ws;

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
export async function uploadFiles(apiBaseUrl, files, serverToken) {
  const base = buildRestUrl(apiBaseUrl);
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
export async function fetchHistory(apiBaseUrl, serverToken, limit = 20) {
  const base = buildRestUrl(apiBaseUrl);
  const headers = {};
  if (serverToken) headers['X-API-Key'] = serverToken;
  const res = await fetch(`${base}/api/history?limit=${limit}`, { headers });
  if (!res.ok) throw new Error(`History fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch single history run.
 */
export async function fetchHistoryRun(apiBaseUrl, serverToken, taskId) {
  const base = buildRestUrl(apiBaseUrl);
  const headers = {};
  if (serverToken) headers['X-API-Key'] = serverToken;
  const res = await fetch(`${base}/api/history/${taskId}`, { headers });
  if (!res.ok) throw new Error(`Run fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Delete a history run.
 */
export async function deleteHistoryRun(apiBaseUrl, serverToken, taskId) {
  const base = buildRestUrl(apiBaseUrl);
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
export function buildDownloadUrl(apiBaseUrl, filePath) {
  const base = buildRestUrl(apiBaseUrl || window.location.origin);
  // TODO: Replace with /api/history/${taskId}/files/${filename} once backend implements it
  const filename = typeof filePath === 'string' ? filePath.split('/').pop() || filePath : String(filePath);
  return `${base}/api/files/${encodeURIComponent(filename)}`;
}
