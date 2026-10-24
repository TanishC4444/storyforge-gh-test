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

// Motion and feedback helpers

const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const MODE_ICON = { sequential: 'i-seq', parallel: 'i-par', recovery: 'i-rec' };

function icon(id, cls = 'ico') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#${id}`);
  svg.append(use);
  return svg;
}

function toast(text, kind = 'info') {
  const node = el('div', { class: `toast ${kind}` }, icon(kind === 'error' ? 'i-rec' : 'i-spark'), el('span', {}, text));
  $('#toasts').append(node);
  setTimeout(() => node.classList.add('leaving'), 4200);
  setTimeout(() => node.remove(), 4700);
}

function countUp(node, value) {
  const from = Number(node.dataset.count) || 0;
  node.dataset.count = value;
  if (reduceMotion() || from === value) { node.textContent = value; return; }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / 700);
    node.textContent = Math.round(from + (value - from) * (1 - (1 - t) ** 3));
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function skeleton(count, cls = 'skeleton-row') {
  return Array.from({ length: count }, (_, i) => el('li', { class: cls, style: `--i:${i}`, 'aria-hidden': 'true' }, el('span'), el('span'), el('span')));
}

// Slides the highlight pill under the active button of a tab group.
function moveThumb(group) {
  const thumb = group?.querySelector('.tab-thumb');
  const active = group?.querySelector('button.active');
  if (!thumb || !active) return;
  thumb.style.width = `${active.offsetWidth}px`;
  thumb.style.transform = `translateX(${active.offsetLeft}px)`;
}

function setPill(text, on) {
  const pill = $('#conn-pill');
  pill.querySelector('b').textContent = text;
  pill.classList.toggle('on', on);
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
    setPill(auth.demo ? 'Demo data' : `${auth.login} · ${health.repo}${auth.can_dispatch ? '' : ' (read only)'}`, true);
    countUp($('#stat-briefs'), state.requests.length);
    message(msg, auth.can_dispatch ? '' : 'This token can read runs but not start them.', auth.can_dispatch ? '' : 'error');
    if (auth.can_dispatch) $('#connect').classList.add('collapsed');
    route();
  } catch (err) {
    state.client = null;
    setPill('Not connected', false);
    message(msg, errorText(err), 'error');
    toast(errorText(err), 'error');
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
    setPill('Not connected', false);
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
      el('strong', {}, r.title),
      el('div', { class: 'facts' },
        el('span', {}, r.medium || 'story'),
        el('span', {}, `${r.chapters}×${r.scenes_per_chapter} scenes`),
        el('span', {}, `~${r.words_per_scene} words/scene`),
        el('span', {}, `${r.characters} characters`)),
      el('p', {}, r.premise.length > 240 ? `${r.premise.slice(0, 240)}…` : r.premise),
    ] : []));
  };
  brief.addEventListener('change', () => {
    showBrief();
    $('#brief-card').animate?.([{ opacity: 0, transform: 'translateY(4px)' }, { opacity: 1, transform: 'none' }], { duration: reduceMotion() ? 0 : 260, easing: 'ease-out' });
  });

  const selectMode = (mode) => {
    current = mode;
    for (const tab of $('#mode-tabs').querySelectorAll('button')) {
      tab.classList.toggle('active', tab.dataset.mode === mode.id);
      tab.setAttribute('aria-selected', String(tab.dataset.mode === mode.id));
    }
    moveThumb($('#mode-tabs'));
    $('#mode-desc').textContent = mode.description;
    $('#mode-desc').animate?.([{ opacity: 0 }, { opacity: 1 }], { duration: reduceMotion() ? 0 : 300 });
    $('#mode-inputs').replaceChildren(...mode.inputs.filter((s) => s.name !== 'request_file').map(inputField));
    const defaultBrief = { sequential: 'living-scale-practice', parallel: 'hard-chronology' }[mode.id];
    if (state.requests.some((r) => r.id === defaultBrief)) brief.value = defaultBrief;
    showBrief();
  };
  $('#mode-tabs').replaceChildren(el('span', { class: 'tab-thumb', 'aria-hidden': 'true' }),
    ...startModes.map((m) => el('button', { type: 'button', role: 'tab', 'data-mode': m.id, onclick: () => selectMode(m) }, icon(MODE_ICON[m.id] || 'i-spark'), m.label)));
  window.addEventListener('resize', () => moveThumb($('#mode-tabs')));
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
      toast(`Run started${started.run_id ? ` · #${started.run_id}` : ''}`, 'ok');
      if (started.run_id) location.hash = `#/runs/${started.run_id}`;
      else message(msg, `Dispatched. GitHub has not listed the run yet; it will appear under tag ${started.tracking_tag}.`, 'ok');
    } catch (err) {
      message(msg, errorText(err), 'error');
      toast(errorText(err), 'error');
    } finally {
      button.disabled = false;
    }
  });

  $('#runs-mode').addEventListener('change', loadRuns);
  $('#refresh').addEventListener('click', (event) => {
    event.currentTarget.classList.remove('spin');
    void event.currentTarget.offsetWidth;
    event.currentTarget.classList.add('spin');
    loadRuns();
  });
  loadRuns();
}

async function loadRuns() {
  const list = $('#runs');
  if (!list) return;
  list.replaceChildren(...skeleton(4));
  try {
    const { runs } = await state.client.listRuns({ mode: $('#runs-mode').value, limit: 30 });
    list.replaceChildren(...(runs.length ? runs.map((r, i) => el('li', { class: 'run-card', style: `--i:${i}` },
      el('a', { href: `#/runs/${r.id}` },
        el('span', { class: `mode-tile ${r.mode}` }, icon(MODE_ICON[r.mode] || 'i-spark')),
        el('span', { class: 'run-text' },
          el('span', { class: 'title' }, r.request_file || r.title),
          el('span', { class: 'meta' }, `${r.mode} · #${r.id}${r.attempt > 1 ? ` · attempt ${r.attempt}` : ''} · ${ago(r.created_at)}`)),
        el('span', { class: `badge ${r.status}` }, el('i', { class: 'dot', 'aria-hidden': 'true' }), STATUS_LABEL[r.status] || r.status)))) : [emptyState('No runs yet', 'Start one on the left and it will show up here.')]));
    const ok = runs.filter((r) => r.status.startsWith('succeeded')).length;
    countUp($('#stat-runs'), runs.length);
    countUp($('#stat-ok'), ok);
    countUp($('#stat-live'), runs.filter((r) => ['queued', 'running'].includes(r.status)).length);
    $('#stat-rate').textContent = runs.length ? `${Math.round((100 * ok) / runs.length)}% success rate` : '—';
  } catch (err) {
    list.replaceChildren(emptyState('Could not load runs', errorText(err)));
    toast(errorText(err), 'error');
  }
}

function emptyState(title, text) {
  return el('li', { class: 'empty-state' }, icon('i-book', 'empty-art'), el('strong', {}, title), el('span', {}, text));
}

// Run detail

function renderRunDetail(run) {
  $('#run-title').textContent = run.request_file || run.title;
  const mode = $('#run-mode');
  mode.replaceChildren(icon(MODE_ICON[run.mode] || 'i-spark'), `${run.mode} mode`);
  $('#run-meta').textContent = `${run.mode} · ${run.workflow} · #${run.id}${run.attempt > 1 ? ` · attempt ${run.attempt}` : ''} · started ${ago(run.created_at)}`;
  const badge = $('#run-status');
  badge.textContent = STATUS_LABEL[run.status] || run.status;
  badge.className = `badge ${run.status}`;
  const p = run.progress;
  const pct = p.jobs_total ? Math.round((100 * p.jobs_done) / p.jobs_total) : 0;
  $('#progress-bar').style.width = `${pct}%`;
  $('#progress').classList.toggle('live', ['queued', 'running'].includes(run.status));
  const ring = $('#ring');
  ring.style.setProperty('--p', pct);
  ring.dataset.status = run.status;
  $('#ring-pct').textContent = `${pct}%`;
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
    const page = el('article', { class: 'book' }, prose);
    const chips = el('div', { class: 'scene-list', role: 'tablist' });
    const pick = (button) => {
      for (const chip of chips.children) chip.classList.toggle('active', chip === button);
      page.animate?.([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: reduceMotion() ? 0 : 320, easing: 'ease-out' });
    };
    const showScene = async (id, button) => {
      const scene = await state.client.scene(run.id, id);
      prose.replaceChildren(el('p', { class: 'scene-meta' }, `${scene.id} · ${scene.status} · ${scene.words} words`), scene.prose);
      pick(button);
    };
    chips.append(
      el('button', { type: 'button', class: 'active', onclick: (e) => { prose.textContent = story.text; pick(e.currentTarget); } }, 'Full text'),
      ...story.scenes.map((s) => el('button', { type: 'button', onclick: (e) => showScene(s.id, e.currentTarget) },
        el('i', { class: `dot s-${s.status}`, 'aria-hidden': 'true' }), `${s.id}`, el('small', {}, `${s.words}w`))));
    body.replaceChildren(
      el('div', { class: 'story-head' },
        el('h2', {}, story.title || 'Story'),
        story.completion_status ? el('span', { class: 'chip' }, story.completion_status.replaceAll('_', ' ')) : null),
      chips,
      page);
  },
  async jobs(body, run) {
    body.replaceChildren(el('ol', { class: 'timeline' }, run.jobs.map((j, i) => el('li', { class: `t-${j.status}`, style: `--i:${i}` },
      el('i', { class: 'node', 'aria-hidden': 'true' }),
      j.html_url ? el('a', { href: j.html_url, target: '_blank', rel: 'noopener' }, j.name) : el('span', {}, j.name),
      el('span', { class: `s-${j.status}` }, j.status)))));
  },
  async canon(body, run) {
    const canon = await state.client.canon(run.id);
    body.replaceChildren(
      el('p', { class: 'muted' }, `Version ${canon.version ?? '?'} · ${canon.memories.length} committed memories`),
      el('ul', { class: 'memories' }, canon.memories.map((m, i) => el('li', { style: `--i:${Math.min(i, 20)}` }, el('span', { class: 'kind' }, m.kind), m.text))));
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
    moveThumb(view.querySelector('.tabs'));
    body.replaceChildren(el('ul', { class: 'runs' }, skeleton(3)));
    try {
      await tabs[name](body, run);
    } catch (err) {
      const pending = err.status === 404 && ['queued', 'running'].includes(run.status);
      body.replaceChildren(el('p', { class: 'muted' }, pending ? 'Appears here once the run uploads it.' : errorText(err)));
    }
  };
  for (const button of view.querySelectorAll('[data-tab]')) button.addEventListener('click', () => showTab(button.dataset.tab));
  requestAnimationFrame(() => moveThumb(view.querySelector('.tabs')));

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
    try { await state.client.cancelRun(id); toast('Cancel requested', 'ok'); } catch (err) { toast(errorText(err), 'error'); }
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
      toast('Recovery started', 'ok');
    } catch (err) {
      message(msg, errorText(err), 'error');
      toast(errorText(err), 'error');
    }
  });

  if (['queued', 'running'].includes(run.status)) {
    state.stopWatch = state.client.watchRun(id, {
      onRun: (detail) => {
        const finished = !['queued', 'running'].includes(detail.status);
        if (finished) toast(`Run #${detail.id}: ${STATUS_LABEL[detail.status] || detail.status}`, detail.status === 'failed' ? 'error' : 'ok');
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
  const match = /^#\/runs\/(\d+)/.exec(location.hash);
  document.querySelector('.hero')?.toggleAttribute('hidden', Boolean(match && state.client));
  $('#stats')?.toggleAttribute('hidden', !state.client);
  const render = () => {
    if (!state.client) {
      view.replaceChildren(el('section', { class: 'panel welcome reveal' },
        el('h2', {}, 'Every story needs a world that remembers'),
        el('p', { class: 'muted' }, 'Start the API locally (see docs/API.md), then connect with a GitHub token, or try the demo data to look around.')));
    } else if (match) renderRun(Number(match[1]));
    else renderHome();
    window.scrollTo({ top: 0, behavior: reduceMotion() ? 'auto' : 'smooth' });
  };
  if (document.startViewTransition && !reduceMotion()) document.startViewTransition(render);
  else render();
}

window.addEventListener('hashchange', route);
setupConnect();
route();
if (state.token) connect(state.token);
