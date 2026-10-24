// API console: one button per endpoint, raw JSON out. Uses the same client as the playground.
import { StoryforgeClient } from './api.js';

const $ = (id) => document.getElementById(id);

const storage = {
  get(kind, key) { try { return (kind === 'local' ? localStorage : sessionStorage).getItem(key) || ''; } catch { return ''; } },
  set(kind, key, value) { try { (kind === 'local' ? localStorage : sessionStorage).setItem(key, value); } catch { /* blocked */ } },
};

// Record the HTTP status of the last API response so it can be shown next to the body.
let lastStatus = null;
const nativeFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const response = await nativeFetch(...args);
  lastStatus = response.status;
  return response;
};

$('c-api').value = new URLSearchParams(location.search).get('api') || storage.get('local', 'sf.api') || 'http://localhost:8000';
$('c-token').value = storage.get('session', 'sf.token');

function client() {
  storage.set('local', 'sf.api', $('c-api').value.trim());
  storage.set('session', 'sf.token', $('c-token').value.trim());
  return new StoryforgeClient({ baseUrl: $('c-api').value.trim(), token: $('c-token').value.trim() });
}

function json(id) {
  const text = $(id).value.trim();
  try {
    return text ? JSON.parse(text) : {};
  } catch (err) {
    throw new Error(`${id} is not valid JSON: ${err.message}`);
  }
}

const runId = () => Number($('c-run').value);

function log(text, kind) {
  const item = document.createElement('li');
  item.className = kind;
  item.textContent = `${new Date().toLocaleTimeString()}  ${text}`;
  $('c-log').prepend(item);
}

function show(label, status, ms, body, ok) {
  $('c-status').textContent = `${label} → ${status ?? 'no response'} in ${ms} ms`;
  $('c-status').className = ok ? 'ok' : 'err';
  $('c-out').textContent = typeof body === 'string' ? body : JSON.stringify(body, null, 2);
  log(`${label} → ${status ?? 'ERR'} (${ms} ms)`, ok ? 'ok' : 'err');
}

async function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// Each entry: [label, call]. Labels show the real path that was requested.
const calls = {
  health: (api) => ['GET /health', api.health()],
  authCheck: (api) => ['GET /auth/check', api.authCheck()],
  modes: (api) => ['GET /modes', api.modes()],
  listRequests: (api) => ['GET /requests', api.listRequests().then((list) => {
    $('c-briefs').replaceChildren(...list.map((r) => Object.assign(document.createElement('option'), { value: r.id })));
    return list;
  })],
  getRequest: (api) => [`GET /requests/${$('c-brief').value}`, api.getRequest($('c-brief').value)],
  validateRequest: (api) => ['POST /requests/validate', api.validateRequest(json('c-brief-json'))],
  listRuns: (api) => {
    const query = { mode: $('c-list-mode').value, status: $('c-list-status').value, tag: $('c-list-tag').value.trim(), limit: $('c-list-limit').value };
    return ['GET /runs', api.listRuns(query)];
  },
  startRun: (api) => {
    const body = { mode: $('c-start-mode').value, request_file: $('c-start-brief').value.trim(), backend: $('c-start-backend').value, inputs: json('c-start-inputs') };
    return ['POST /runs', api.startRun(body).then((started) => {
      if (started.run_id) $('c-run').value = started.run_id;
      if (started.tracking_tag) $('c-list-tag').value = started.tracking_tag;
      return started;
    })];
  },
  getRun: (api) => [`GET /runs/${runId()}`, api.getRun(runId())],
  story: (api) => [`GET /runs/${runId()}/story`, api.story(runId())],
  scene: (api) => [`GET /runs/${runId()}/scenes/${$('c-scene').value}`, api.scene(runId(), $('c-scene').value.trim())],
  canon: (api) => [`GET /runs/${runId()}/canon`, api.canon(runId())],
  artifacts: (api) => [`GET /runs/${runId()}/artifacts`, api.artifacts(runId())],
  downloadArtifact: (api) => {
    const name = $('c-artifact').value.trim();
    return [`GET /runs/${runId()}/artifacts/${name}`, api.downloadArtifact(runId(), name).then(async (blob) => {
      await saveBlob(blob, `${name}.zip`);
      return { saved: `${name}.zip`, type: blob.type, bytes: blob.size };
    })];
  },
  cancelRun: (api) => [`POST /runs/${runId()}/cancel`, api.cancelRun(runId())],
  recoverRun: (api) => {
    const body = {
      strategy: $('c-rec-strategy').value, scene: $('c-rec-scene').value, restart_stage: $('c-rec-stage').value,
      backend: $('c-rec-backend').value, inputs: json('c-rec-inputs'),
    };
    return [`POST /runs/${runId()}/recover`, api.recoverRun(runId(), body).then((started) => {
      const next = started.tracks_run_id || started.run_id;
      if (next) $('c-run').value = next;
      return started;
    })];
  },
};

for (const button of document.querySelectorAll('[data-call]')) {
  button.addEventListener('click', async () => {
    const started = performance.now();
    button.disabled = true;
    let label = button.textContent;
    try {
      const [name, promise] = calls[button.dataset.call](client());
      label = name;
      $('c-status').textContent = `${label} …`;
      $('c-status').className = '';
      const body = await promise;
      show(label, lastStatus, Math.round(performance.now() - started), body ?? '(empty body)', true);
    } catch (err) {
      show(label, err.status || lastStatus, Math.round(performance.now() - started), { error: err.message, status: err.status }, false);
    } finally {
      button.disabled = false;
    }
  });
}

$('c-demo').addEventListener('click', () => {
  $('c-token').value = 'demo';
  $('c-run').value = 9001;
  log('Token set to demo', 'ok');
});

$('c-load-brief').addEventListener('click', async () => {
  try {
    $('c-brief-json').value = JSON.stringify(await client().getRequest($('c-brief').value), null, 2);
    log(`Loaded ${$('c-brief').value} into the editor`, 'ok');
  } catch (err) {
    log(`Load brief failed: ${err.message}`, 'err');
  }
});

let stop = null;
$('c-watch').addEventListener('click', () => {
  stop?.();
  const id = runId();
  log(`Watching /runs/${id}/events`, 'ev');
  $('c-watch').disabled = true;
  $('c-unwatch').disabled = false;
  const done = () => { $('c-watch').disabled = false; $('c-unwatch').disabled = true; stop = null; };
  stop = client().watchRun(id, {
    onRun: (run) => {
      log(`event run: ${run.status} · ${run.progress.jobs_done}/${run.progress.jobs_total} jobs · scenes ${run.progress.accepted_scenes ?? '?'}/${run.progress.total_scenes ?? '?'}`, 'ev');
      $('c-out').textContent = JSON.stringify(run, null, 2);
    },
    onEnd: () => { log('event end', 'ev'); done(); },
    onError: (err) => { log(`events failed: ${err.message}`, 'err'); done(); },
  });
});
$('c-unwatch').addEventListener('click', () => { stop?.(); log('Stopped watching', 'ev'); $('c-watch').disabled = false; $('c-unwatch').disabled = true; });
$('c-clear').addEventListener('click', () => { $('c-log').replaceChildren(); $('c-out').textContent = ''; });
