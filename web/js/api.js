// Storyforge API client. Framework-free so any frontend can import it.
//
//   import { StoryforgeClient } from './api.js';
//   const api = new StoryforgeClient({ baseUrl: 'http://localhost:8000', token: 'demo' });
//   const { runs } = await api.listRuns();
//
// Every method returns parsed JSON or throws ApiError. Response shapes are in
// docs/API.md and web/openapi.json.

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export class StoryforgeClient {
  constructor({ baseUrl, token, timeoutMs = 30000 }) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.token = token || '';
    this.timeoutMs = timeoutMs;
    this.lastStatus = null;
  }

  url(path) {
    return `${this.baseUrl}/api/v1${path}`;
  }

  headers(extra = {}) {
    const headers = { ...extra };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    return headers;
  }

  async request(method, path, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    this.lastStatus = null;
    try {
      const response = await fetch(this.url(path), {
        method, signal: controller.signal,
        headers: this.headers(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      this.lastStatus = response.status;
      const text = await response.text();
      let data;
      try { data = text ? JSON.parse(text) : null; }
      catch { throw new ApiError(response.status, response.ok ? 'The API returned invalid JSON.' : `The API returned HTTP ${response.status}.`); }
      if (!response.ok) {
        const detail = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).join('; ') : data?.detail;
        throw new ApiError(response.status, typeof detail === 'string' ? detail : undefined);
      }
      return data;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (controller.signal.aborted) throw new ApiError(0, method === 'POST'
        ? 'Request timed out. A submitted run may still have started; check the run list before retrying.'
        : 'Request timed out. Check the connection and try again.');
      throw new ApiError(0, `Cannot reach the API at ${this.baseUrl}. Is the server running?`);
    } finally { clearTimeout(timer); }
  }

  // Public
  health() { return this.request('GET', '/health'); }
  modes() { return this.request('GET', '/modes'); }
  listRequests() { return this.request('GET', '/requests'); }
  getRequest(id) { return this.request('GET', `/requests/${encodeURIComponent(id)}`); }
  validateRequest(brief) { return this.request('POST', '/requests/validate', brief); }

  // Authenticated
  authCheck() { return this.request('GET', '/auth/check'); }

  listRuns({ mode, status, tag, limit } = {}) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries({ mode, status, tag, limit })) {
      if (value !== undefined && value !== null && value !== '') params.set(key, value);
    }
    const query = params.toString();
    return this.request('GET', `/runs${query ? `?${query}` : ''}`);
  }

  // body: { mode: 'sequential'|'parallel', request_file, backend, inputs: {...} }
  startRun(body) { return this.request('POST', '/runs', body); }
  getRun(id) { return this.request('GET', `/runs/${id}`); }
  // body: { strategy: 'fresh'|'rerun', scene, restart_stage, backend, inputs }
  recoverRun(id, body = {}) { return this.request('POST', `/runs/${id}/recover`, body); }
  cancelRun(id) { return this.request('POST', `/runs/${id}/cancel`); }
  story(id) { return this.request('GET', `/runs/${id}/story`); }
  scene(id, sceneId) { return this.request('GET', `/runs/${id}/scenes/${encodeURIComponent(sceneId)}`); }
  canon(id) { return this.request('GET', `/runs/${id}/canon`); }
  artifacts(id) { return this.request('GET', `/runs/${id}/artifacts`); }

  async downloadArtifact(id, name) {
    this.lastStatus = null;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(this.timeoutMs, 120000));
    try {
      const response = await fetch(this.url(`/runs/${id}/artifacts/${encodeURIComponent(name)}`), { headers: this.headers(), signal: controller.signal });
      this.lastStatus = response.status;
      if (!response.ok) throw new ApiError(response.status, (await response.json().catch(() => ({}))).detail);
      return await response.blob();
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError(0, controller.signal.aborted ? 'Artifact download timed out.' : 'Artifact download failed. Check the API connection.');
    } finally { clearTimeout(timer); }
  }

  // Follow a run live. EventSource cannot send the token, so this reads the
  // server-sent event stream with fetch. Returns a function that stops it.
  // onRun receives a RunDetail each time it changes; onEnd fires when the run finishes.
  watchRun(id, { onRun, onEnd, onError } = {}) {
    const controller = new AbortController();
    (async () => {
      let reader;
      try {
        const response = await fetch(this.url(`/runs/${id}/events`), { headers: this.headers(), signal: controller.signal });
        this.lastStatus = response.status;
        if (!response.ok) throw new ApiError(response.status, (await response.json().catch(() => ({}))).detail);
        if (!response.body) throw new ApiError(0, 'Live updates are unavailable in this response.');
        reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (controller.signal.aborted) return;
          if (done) throw new ApiError(0, 'Live update connection closed before completion; refresh to reconnect.');
          buffer += decoder.decode(value, { stream: true });
          if (buffer.length > 2000000) throw new ApiError(0, 'Live update exceeded the supported event size.');
          let boundary;
          while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
            const block = buffer.slice(0, boundary.index);
            buffer = buffer.slice(boundary.index + boundary[0].length);
            const lines = block.split(/\r?\n/);
            const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
            const data = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).replace(/^ /, '')).join('\n');
            if (event === 'run' && data) onRun?.(JSON.parse(data));
            if (event === 'end') { onEnd?.(); return; }
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) onError?.(err);
      } finally {
        if (reader) {
          await reader.cancel().catch(() => {});
          reader.releaseLock();
        }
      }
    })();
    return () => controller.abort();
  }
}
