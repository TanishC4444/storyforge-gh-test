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
  constructor({ baseUrl, token }) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.token = token || '';
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
    let response;
    try {
      response = await fetch(this.url(path), {
        method,
        headers: this.headers(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (err) {
      throw new ApiError(0, `Cannot reach the API at ${this.baseUrl}. Is the server running?`);
    }
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) {
      const detail = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).join('; ') : data?.detail;
      throw new ApiError(response.status, detail);
    }
    return data;
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
    const response = await fetch(this.url(`/runs/${id}/artifacts/${encodeURIComponent(name)}`), { headers: this.headers() });
    if (!response.ok) throw new ApiError(response.status, (await response.json().catch(() => ({}))).detail);
    return response.blob();
  }

  // Follow a run live. EventSource cannot send the token, so this reads the
  // server-sent event stream with fetch. Returns a function that stops it.
  // onRun receives a RunDetail each time it changes; onEnd fires when the run finishes.
  watchRun(id, { onRun, onEnd, onError } = {}) {
    const controller = new AbortController();
    (async () => {
      try {
        const response = await fetch(this.url(`/runs/${id}/events`), { headers: this.headers(), signal: controller.signal });
        if (!response.ok) throw new ApiError(response.status, (await response.json().catch(() => ({}))).detail);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary;
          while ((boundary = buffer.indexOf('\n\n')) >= 0) {
            const block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const event = /^event: (.*)$/m.exec(block)?.[1];
            const data = /^data: (.*)$/m.exec(block)?.[1];
            if (event === 'run' && data) onRun?.(JSON.parse(data));
            if (event === 'end') { onEnd?.(); return; }
          }
        }
        onEnd?.();
      } catch (err) {
        if (err.name !== 'AbortError') onError?.(err);
      }
    })();
    return () => controller.abort();
  }
}
