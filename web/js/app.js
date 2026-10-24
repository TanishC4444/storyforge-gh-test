// Playground UI over StoryforgeClient. Plain DOM, hash routing (#/ and #/runs/<id>).
import { ApiError, StoryforgeClient } from './api.js';

const $ = (selector, root = document) => root.querySelector(selector);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function store(kind) {
  try { return kind === 'local' ? window.localStorage : window.sessionStorage; } catch { return null; }
}
const read = (kind, key) => { try { return store(kind)?.getItem(key) || ''; } catch { return ''; } };
const write = (kind, key, value) => { try { value ? store(kind)?.setItem(key, value) : store(kind)?.removeItem(key); } catch { /* storage blocked */ } };

const params = new URLSearchParams(location.search);
const state = {
  apiUrl: params.get('api') || read('local', 'sf.api') || 'http://localhost:8000',
  token: read('session', 'sf.token'),
  client: null,
  modes: [],
  requests: [],
  stopWatch: null,
};

const STATUS_LABEL = {
  queued: 'Queued', running: 'Running', succeeded: 'Succeeded',
  succeeded_with_warnings: 'Succeeded with warnings', failed: 'Failed', cancelled: 'Cancelled',
};

function message(node, text, kind = '') {
  node.textContent = text;
  node.className = `msg ${kind}`;
}

function errorText(err) {
  if (err instanceof ApiError && err.status === 401) return `${err.message} (check the token)`;
  return err.message || String(err);
}

function ago(iso) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 90) return 'just now';
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 129600) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}

// Connection

async function connect(token) {
  const msg = $('#connect-msg');
  state.apiUrl = $('#api-url').value.trim();
  write('local', 'sf.api', state.apiUrl);
  state.client = new StoryforgeClient({ baseUrl: state.apiUrl, token });
  message(msg, 'Connecting…');
  try {
    const [health, auth] = await Promise.all([state.client.health(), state.client.authCheck()]);
    [state.modes, state.requests] = await Promise.all([state.client.modes(), state.client.listRequests()]);
    state.token = token;
    write('session', 'sf.token', token);
    const pill = $('#conn-pill');
    pill.textContent = auth.demo ? 'Demo data' : `${auth.login} · ${health.repo}${auth.can_dispatch ? '' : ' (read only)'}`;
    pill.classList.add('on');
    message(msg, auth.can_dispatch ? '' : 'This token can read runs but not start them.', auth.can_dispatch ? '' : 'error');
    if (auth.can_dispatch) $('#connect').classList.add('collapsed');
    route();
  } catch (err) {
    state.client = null;
    $('#conn-pill').textContent = 'Not connected';
    $('#conn-pill').classList.remove('on');
    message(msg, errorText(err), 'error');
  }
}

function setupConnect() {
  $('#api-url').value = state.apiUrl;
  $('#token').value = state.token && state.token !== 'demo' ? state.token : '';
  $('#connect-form').addEventListener('submit', (event) => {
    event.preventDefault();
    connect($('#token').value.trim());
  });
  $('#conn-pill').addEventListener('click', () => $('#connect').classList.toggle('collapsed'));
  $('#use-demo').addEventListener('click', () => { $('#token').value = ''; connect('demo'); });
  $('#disconnect').addEventListener('click', () => {
    write('session', 'sf.token', '');
    state.token = '';
    state.client = null;
    $('#token').value = '';
    $('#conn-pill').textContent = 'Not connected';
    $('#conn-pill').classList.remove('on');
    $('#connect').classList.remove('collapsed');
    route();
  });
}

// Home: start form and run list

function inputField(spec) {
  const name = spec.name;
  let control;
  if (spec.type === 'choice') {
    control = el('select', { name }, spec.options.map((o) => el('option', { value: o }, o)));
    if (spec.default !== null && spec.default !== undefined) control.value = String(spec.default);
  } else if (spec.type === 'boolean') {
    control = el('input', { name, type: 'checkbox' });
    control.checked = Boolean(spec.default);
  } else {
    control = el('input', { name, type: 'text', value: spec.default ?? '', placeholder: spec.description || '' });
  }
  return el('label', { title: spec.description || '' }, spec.label, control);
}

function renderHome() {
  const view = $('#view');
  view.replaceChildren($('#tpl-home').content.cloneNode(true));
  const startModes = state.modes.filter((m) => m.starts_from === 'request');
  let current = startModes[0];

  const brief = $('#brief');
  brief.replaceChildren(...state.requests.map((r) => el('option', { value: r.id }, `${r.title} (${r.id})`)));
  const showBrief = () => {
    const r = state.requests.find((x) => x.id === brief.value);
    $('#brief-card').replaceChildren(...(r ? [
      el('strong', {}, r.title), el('br'),
      `${r.medium || 'story'} · ${r.chapters}×${r.scenes_per_chapter} scenes · ~${r.words_per_scene} words/scene · ${r.characters} characters`,
      el('br'), r.premise.length > 240 ? `${r.premise.slice(0, 240)}…` : r.premise,
    ] : []));
  };
  brief.addEventListener('change', showBrief);

  const selectMode = (mode) => {
    current = mode;
    for (const tab of $('#mode-tabs').children) tab.classList.toggle('active', tab.dataset.mode === mode.id);
    $('#mode-desc').textContent = mode.description;
    $('#mode-inputs').replaceChildren(...mode.inputs.filter((s) => s.name !== 'request_file').map(inputField));
    const defaultBrief = { sequential: 'living-scale-practice', parallel: 'hard-chronology' }[mode.id];
    if (state.requests.some((r) => r.id === defaultBrief)) brief.value = defaultBrief;
    showBrief();
  };
  $('#mode-tabs').replaceChildren(...startModes.map((m) => el('button', { type: 'button', 'data-mode': m.id, onclick: () => selectMode(m) }, m.label)));
  if (current) selectMode(current);

  $('#start-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = event.submitter;
    const msg = $('#start-msg');
    const inputs = {};
    for (const control of $('#mode-inputs').querySelectorAll('[name]')) {
      inputs[control.name] = control.type === 'checkbox' ? control.checked : control.value;
    }
    const { backend, ...rest } = inputs;
    button.disabled = true;
    message(msg, 'Starting…');
    try {
      const started = await state.client.startRun({ mode: current.id, request_file: brief.value, backend, inputs: rest });
      if (started.run_id) location.hash = `#/runs/${started.run_id}`;
      else message(msg, `Dispatched. GitHub has not listed the run yet; it will appear under tag ${started.tracking_tag}.`, 'ok');
    } catch (err) {
      message(msg, errorText(err), 'error');
    } finally {
      button.disabled = false;
    }
  });

  $('#runs-mode').addEventListener('change', loadRuns);
  $('#refresh').addEventListener('click', loadRuns);
  loadRuns();
}

async function loadRuns() {
  const list = $('#runs');
  if (!list) return;
  list.replaceChildren(el('li', { class: 'empty' }, 'Loading…'));
  try {
    const { runs } = await state.client.listRuns({ mode: $('#runs-mode').value, limit: 30 });
    list.replaceChildren(...(runs.length ? runs.map((r) => el('li', {},
      el('a', { href: `#/runs/${r.id}` },
        el('span', { class: 'title' }, r.request_file || r.title),
        el('span', { class: `badge ${r.status}` }, STATUS_LABEL[r.status] || r.status),
        el('span', { class: 'meta' }, `${r.mode} · #${r.id}${r.attempt > 1 ? ` · attempt ${r.attempt}` : ''}`),
        el('span', { class: 'meta' }, ago(r.created_at))))) : [el('li', { class: 'empty' }, 'No runs yet.')]));
  } catch (err) {
    list.replaceChildren(el('li', { class: 'empty' }, errorText(err)));
  }
}

// Run detail

function renderRunDetail(run) {
  $('#run-title').textContent = run.request_file || run.title;
  $('#run-meta').textContent = `${run.mode} · ${run.workflow} · #${run.id}${run.attempt > 1 ? ` · attempt ${run.attempt}` : ''} · started ${ago(run.created_at)}`;
  const badge = $('#run-status');
  badge.textContent = STATUS_LABEL[run.status] || run.status;
  badge.className = `badge ${run.status}`;
  const p = run.progress;
  $('#progress-bar').style.width = `${p.jobs_total ? Math.round((100 * p.jobs_done) / p.jobs_total) : 0}%`;
  const scenes = p.accepted_scenes !== null && p.accepted_scenes !== undefined
    ? ` · ${p.accepted_scenes}${p.total_scenes ? ` of ${p.total_scenes}` : ''} scenes accepted` : '';
  $('#progress-text').textContent = `${p.jobs_done} of ${p.jobs_total} jobs done${scenes}`;
  $('#warnings').replaceChildren(...run.warnings.map((w) => el('li', {}, w)));
  $('#cancel').hidden = !['queued', 'running'].includes(run.status);
  const link = $('#gh-link');
  link.hidden = !run.html_url;
  if (run.html_url) link.href = run.html_url;
  $('#recover-form').hidden = !run.recoverable;
}

const tabs = {
  async story(body, run) {
    const story = await state.client.story(run.id);
    const prose = el('div', { class: 'prose' }, story.text || '(No prose yet.)');
    const showScene = async (id) => {
      const scene = await state.client.scene(run.id, id);
      prose.replaceChildren(el('p', { class: 'muted' }, `${scene.id} · ${scene.status} · ${scene.words} words`), scene.prose);
    };
    body.replaceChildren(
      el('p', { class: 'muted' }, `${story.title || ''} ${story.completion_status ? `· ${story.completion_status}` : ''}`),
      el('div', { class: 'scene-list' },
        el('button', { type: 'button', onclick: () => { prose.textContent = story.text; } }, 'Full text'),
        story.scenes.map((s) => el('button', { type: 'button', onclick: () => showScene(s.id) }, `${s.id} · ${s.status} · ${s.words}w`))),
      prose);
  },
  async jobs(body, run) {
    body.replaceChildren(el('ul', { class: 'jobs' }, run.jobs.map((j) => el('li', {},
      j.html_url ? el('a', { href: j.html_url, target: '_blank', rel: 'noopener' }, j.name) : el('span', {}, j.name),
      el('span', { class: `s-${j.status}` }, j.status)))));
  },
  async canon(body, run) {
    const canon = await state.client.canon(run.id);
    body.replaceChildren(
      el('p', { class: 'muted' }, `Version ${canon.version ?? '?'} · ${canon.memories.length} committed memories`),
      el('ul', { class: 'memories' }, canon.memories.map((m) => el('li', {}, el('span', { class: 'kind' }, m.kind), m.text))));
  },
  async artifacts(body, run) {
    const { artifacts } = await state.client.artifacts(run.id);
    body.replaceChildren(el('ul', { class: 'jobs' }, artifacts.length ? artifacts.map((a) => el('li', {},
      el('span', {}, a.name),
      a.expired ? el('span', { class: 's-skipped' }, 'expired') : el('button', {
        type: 'button', class: 'ghost',
        onclick: async () => {
          const url = URL.createObjectURL(await state.client.downloadArtifact(run.id, a.name));
          el('a', { href: url, download: `${a.name}.zip` }).click();
          setTimeout(() => URL.revokeObjectURL(url), 10000);
        },
      }, `Download (${Math.ceil(a.size_bytes / 1024)} KB)`))) : [el('li', {}, 'No artifacts yet.')]));
  },
};

async function renderRun(id) {
  const view = $('#view');
  view.replaceChildren($('#tpl-run').content.cloneNode(true));
  let run;
  let activeTab = 'story';
  const body = $('#tab-body');
  const showTab = async (name) => {
    activeTab = name;
    for (const button of view.querySelectorAll('[data-tab]')) button.classList.toggle('active', button.dataset.tab === name);
    body.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
    try {
      await tabs[name](body, run);
    } catch (err) {
      const pending = err.status === 404 && ['queued', 'running'].includes(run.status);
      body.replaceChildren(el('p', { class: 'muted' }, pending ? 'Appears here once the run uploads it.' : errorText(err)));
    }
  };
  for (const button of view.querySelectorAll('[data-tab]')) button.addEventListener('click', () => showTab(button.dataset.tab));

  try {
    run = await state.client.getRun(id);
  } catch (err) {
    view.replaceChildren(el('section', { class: 'panel' }, el('a', { href: '#/', class: 'back' }, '← All runs'), el('p', {}, errorText(err))));
    return;
  }
  renderRunDetail(run);
  showTab(activeTab);

  $('#cancel').addEventListener('click', async (event) => {
    event.target.disabled = true;
    try { await state.client.cancelRun(id); } catch (err) { alert(errorText(err)); }
    event.target.disabled = false;
  });
  $('#recover-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const msg = $('#recover-msg');
    message(msg, 'Starting recovery…');
    try {
      const started = await state.client.recoverRun(id, Object.fromEntries(form));
      const next = started.tracks_run_id || started.run_id;
      if (next) location.hash = `#/runs/${next}`;
      if (next === id) route();
      if (!next) message(msg, 'Dispatched; refresh the run list in a moment.', 'ok');
    } catch (err) {
      message(msg, errorText(err), 'error');
    }
  });

  if (['queued', 'running'].includes(run.status)) {
    state.stopWatch = state.client.watchRun(id, {
      onRun: (detail) => {
        const finished = !['queued', 'running'].includes(detail.status);
        run = detail;
        renderRunDetail(detail);
        if (activeTab === 'jobs' || finished) showTab(activeTab);
      },
      onError: (err) => { $('#progress-text').textContent = `Live updates stopped: ${errorText(err)}`; },
    });
  }
}

// Routing

function route() {
  state.stopWatch?.();
  state.stopWatch = null;
  const view = $('#view');
  if (!state.client) {
    view.replaceChildren(el('section', { class: 'panel' },
      el('h2', {}, 'Connect to a Storyforge API'),
      el('p', { class: 'muted' }, 'Start the API locally (see docs/API.md), then connect with a GitHub token or the demo data.')));
    return;
  }
  const match = /^#\/runs\/(\d+)/.exec(location.hash);
  if (match) renderRun(Number(match[1]));
  else renderHome();
}

window.addEventListener('hashchange', route);
setupConnect();
route();
if (state.token) connect(state.token);
