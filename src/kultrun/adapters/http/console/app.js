/*
 * Kultrun Prototype Console.
 *
 * The one rule: this file contains no product intelligence. It does not
 * classify a filesystem, compute a reserve, decide what is safe, or judge
 * whether a subsystem works. Every one of those answers arrives from the
 * Platform API, and this only lays them out.
 *
 * Formatting bytes and picking a colour are presentation. Deciding that
 * 507 TiB should not be trusted is the product's job, and if that decision
 * were made here it would be untested, unversioned and invisible to the
 * architecture tests.
 *
 * Nothing on this page mutates anything on load or on refresh. The one
 * action that performs real storage work needs a deliberate click.
 */

'use strict';

const API = '/v1';

/* Subsystems, and the endpoint whose answer proves each one works. A
 * subsystem is "working" because the product answered, never because it is
 * listed here. */
const SUBSYSTEMS = [
  { name: 'Host discovery', probe: '/host' },
  { name: 'Capacity', probe: '/capacity' },
  { name: 'Storage sanity', probe: '/storage/sanity' },
  { name: 'Runtime / executor', probe: '/runtime' },
  { name: 'Model presence', probe: null, stage: '1.4' },
  { name: 'Resource admission', probe: null, stage: '1.5' },
  { name: 'Inference', probe: null, stage: '1.6' },
];

/* ---------- transport ------------------------------------------------- */

async function get(path) {
  const response = await fetch(API + path, { headers: { Accept: 'application/json' } });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && body.error ? body.error.message || body.error.code : response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }
  return body ? body.payload : null;
}

async function post(path, payload) {
  const response = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && body.error ? body.error.message || body.error.code : response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }
  return body ? body.payload : null;
}

/* ---------- presentation ---------------------------------------------- */

/* An unresolved value arrives as an object naming its kind. It is never
 * rendered as 0, blank or infinity: the product went to some trouble to
 * distinguish "unknown" from "none", and flattening it here would throw
 * that away at the last step. */
function isUnresolved(value) {
  return value === null || (typeof value === 'object' && value !== null && 'kind' in value);
}

function unresolvedLabel(value) {
  if (value === null) return 'unknown';
  const kind = String(value.kind || '').replace('unresolved.', '').replace(/_/g, ' ');
  return kind || 'unknown';
}

function bytes(value) {
  if (isUnresolved(value)) return span('unknown', unresolvedLabel(value));
  if (typeof value !== 'number') return span('unknown', 'unknown');
  const units = [['PiB', 2 ** 50], ['TiB', 2 ** 40], ['GiB', 2 ** 30], ['MiB', 2 ** 20]];
  for (const [unit, size] of units) {
    if (value >= size) return text(`${(value / size).toFixed(1)} ${unit}`);
  }
  return text(`${value} B`);
}

function plain(value) {
  if (isUnresolved(value)) return span('unknown', unresolvedLabel(value));
  if (value === undefined) return span('unknown', 'not reported');
  if (typeof value === 'boolean') return text(value ? 'yes' : 'no');
  return text(String(value));
}

function text(value) {
  return document.createTextNode(value);
}

function span(className, value) {
  const node = document.createElement('span');
  node.className = className;
  node.textContent = value;
  return node;
}

function pill(label, tone) {
  const node = document.createElement('span');
  node.className = `pill pill-${tone}`;
  node.textContent = label;
  return node;
}

function rows(target, pairs) {
  target.replaceChildren();
  for (const [key, value] of pairs) {
    const k = document.createElement('div');
    k.className = 'key';
    k.textContent = key;
    const v = document.createElement('div');
    v.className = 'value';
    v.append(value instanceof Node ? value : plain(value));
    target.append(k, v);
  }
}

function failure(target, error) {
  const node = document.createElement('div');
  node.className = 'error';
  node.textContent = `unavailable: ${error.message}`;
  target.replaceChildren(node);
}

function json(target, value) {
  target.textContent = JSON.stringify(value, null, 2);
}

/* Tone for a capacity requirement or sanity status. Purely visual: the
 * product decided the status, this only chooses a colour for it. */
const TONES = {
  sufficient: 'ok',
  restricted: 'warn',
  empirical_evidence_needed: 'warn',
  unknown: 'unknown',
  policy_cap_verified: 'ok',
  partially_verified: 'warn',
  contradicted: 'bad',
  unsupported: 'unknown',
  inconclusive: 'unknown',
  not_checked: 'unknown',
};

function tone(status) {
  return TONES[status] || 'unknown';
}

/* ---------- panels ---------------------------------------------------- */

async function renderMode() {
  const badge = document.getElementById('mode');
  const target = document.getElementById('evidence');
  const note = document.getElementById('evidence-note');
  try {
    const mode = await get('/mode');
    const replaying = mode.evidence_mode === 'fixture_replay';
    document.body.classList.toggle('replay', replaying);

    badge.className = `pill pill-${replaying ? 'warn' : 'ok'}`;
    badge.textContent = replaying ? 'mode: fixture replay' : 'mode: live host';

    const pairs = [
      ['mode', String(mode.evidence_mode).replace(/_/g, ' ')],
      ['physical host connected', mode.physical_host_connected
        ? pill('yes', 'ok') : pill('no', 'warn')],
      ['storage evidence', String(mode.storage_evidence_kind).replace(/_/g, ' ')],
    ];
    if (mode.fixture) {
      pairs.push(
        ['fixture shape', mode.fixture.shape_id],
        ['captured', mode.fixture.captured],
        ['evidence level', mode.fixture.evidence_level],
        ['profile earned', mode.fixture.deployment_profile],
        ['hardware', mode.fixture.description],
      );
      note.textContent = mode.fixture.note;
    } else {
      note.textContent =
        'Facts below were observed on this machine by the current providers.';
    }
    pairs.push(['available fixtures', (mode.available_fixtures || []).join(', ') || 'none']);
    rows(target, pairs);
    return mode;
  } catch (error) {
    badge.className = 'pill pill-bad';
    badge.textContent = 'mode unknown';
    failure(target, error);
    return null;
  }
}

async function renderBuild() {
  const connection = document.getElementById('connection');
  try {
    const version = await get('/version');
    const config = await get('/config').catch(() => null);
    rows(document.getElementById('build'), [
      ['version', version.version],
      ['origin', version.origin === 'artifact'
        ? pill('installed artifact', 'ok')
        : pill('source checkout', 'warn')],
      ['source commit', version.source_commit || 'unknown'],
      ['build id', version.build_id || 'unknown'],
      ['built at', version.built_at || 'unknown'],
      ['acceptable as evidence', version.acceptable_as_evidence
        ? pill('yes', 'ok') : pill('development only', 'warn')],
      ['state root', config && config.platform ? config.platform.state_root : 'unknown'],
    ]);
    connection.className = 'pill pill-ok';
    connection.textContent = 'connected';
    document.getElementById('footer-build').textContent =
      `${version.version} · ${version.build_id || 'source'}`;
    return version;
  } catch (error) {
    connection.className = 'pill pill-bad';
    connection.textContent = 'disconnected';
    failure(document.getElementById('build'), error);
    return null;
  }
}

async function renderProgress() {
  const target = document.getElementById('progress');
  target.replaceChildren();
  for (const subsystem of SUBSYSTEMS) {
    const row = document.createElement('div');
    row.className = 'progress-row';
    const label = document.createElement('span');
    label.textContent = subsystem.name;
    row.append(label);

    if (!subsystem.probe) {
      row.append(pill(`not implemented · stage ${subsystem.stage}`, 'unknown'));
    } else {
      try {
        await get(subsystem.probe);
        row.append(pill('working', 'ok'));
      } catch (error) {
        const missing = error.message.startsWith('404');
        row.append(pill(missing ? 'not implemented' : `error · ${error.message}`,
          missing ? 'unknown' : 'bad'));
      }
    }
    target.append(row);
  }
}

async function renderCapacity() {
  const body = document.querySelector('#capacity tbody');
  const defects = document.getElementById('capacity-defects');
  try {
    const envelope = await get('/capacity');
    body.replaceChildren();

    addCapacityRow(body, 'System memory', envelope.memory,
      envelope.memory_note || envelope.memory_requirement);
    for (const accelerator of envelope.accelerators || []) {
      addCapacityRow(body, `Accelerator ${accelerator.index}`, accelerator.memory,
        accelerator.note || accelerator.requirement);
    }
    for (const pool of envelope.pools || []) {
      addCapacityRow(body, pool.mount_point, pool.space,
        pool.note || pool.requirement, pool.filesystem_type);
    }

    defects.replaceChildren();
    for (const defect of envelope.defects || []) {
      const node = document.createElement('div');
      node.className = 'defect';
      node.textContent = defect;
      defects.append(node);
    }
    json(document.getElementById('capacity-json'), envelope);
    return envelope;
  } catch (error) {
    failure(defects, error);
    body.replaceChildren();
    return null;
  }
}

function addCapacityRow(body, label, layered, reason, filesystem) {
  const row = document.createElement('tr');
  const name = document.createElement('td');
  name.textContent = label;
  if (filesystem && !isUnresolved(filesystem)) {
    name.append(document.createElement('br'), span('muted', String(filesystem)));
  }
  const reported = document.createElement('td');
  reported.className = 'num reported';
  reported.append(bytes(layered.reported_bytes));
  const effective = document.createElement('td');
  effective.className = 'num';
  effective.append(bytes(layered.effective_bytes));
  const safe = document.createElement('td');
  safe.className = 'num safe';
  safe.append(bytes(layered.safe_bytes));
  const basis = document.createElement('td');
  basis.append(typeof reason === 'string' && TONES[reason]
    ? pill(reason.replace(/_/g, ' '), tone(reason))
    : plain(reason));
  row.append(name, reported, effective, safe, basis);
  body.append(row);
}

async function renderSanity(envelope) {
  const target = document.getElementById('sanity');
  try {
    const state = await get('/storage/sanity');
    const replayed = state.evidence_kind === 'replayed_test_evidence';
    const pools = (envelope && envelope.pools) || [];
    const candidates = pools.filter(
      (pool) => pool.sanity_check_required || pool.sanity_status !== 'not_checked');

    if (candidates.length === 0) {
      target.replaceChildren(span('muted',
        'No pool currently needs empirical verification.'));
      return;
    }

    target.replaceChildren();
    const kind = document.createElement('div');
    kind.style.marginBottom = '0.8rem';
    kind.append(pill(replayed ? 'replayed test evidence' : 'live empirical verification',
      replayed ? 'warn' : 'ok'));
    target.append(kind);
    for (const pool of candidates) {
      const evidence = (state.evidence || {})[pool.mount_point] || null;
      target.append(sanityCard(pool, evidence, replayed));
    }
  } catch (error) {
    failure(target, error);
  }
}

function sanityCard(pool, evidence, replayed) {
  const card = document.createElement('div');
  card.className = 'pool';

  const head = document.createElement('div');
  head.className = 'pool-head';
  const path = document.createElement('span');
  path.className = 'pool-path';
  path.textContent = pool.mount_point;
  head.append(path, pill((pool.sanity_status || 'not_checked').replace(/_/g, ' '),
    tone(pool.sanity_status)));
  card.append(head);

  const grid = document.createElement('div');
  grid.className = 'grid';
  const pairs = [
    ['reported', bytes(pool.space.reported_bytes)],
    ['policy effective', bytes(pool.space.effective_bytes)],
    ['safe', bytes(pool.space.safe_bytes)],
    ['trigger', pool.sanity_check_required
      ? 'large and not credible; empirical verification would establish whether the bound is earned'
      : 'not currently flagged'],
    ['verified lower bound', bytes(pool.sanity_verified_lower_bound_bytes)],
  ];
  if (evidence) {
    pairs.push(
      ['failure upper bound', bytes(evidence.observed_failure_upper_bytes)],
      ['policy target', bytes(evidence.policy_target_bytes)],
      ['stop reason', String(evidence.stop_reason || '').replace(/_/g, ' ')],
      ['attempts', evidence.attempts],
      ['cleanup verified', evidence.cleanup_verified],
      ['checked at', evidence.observed_at],
    );
  }
  rows(grid, pairs);
  card.append(grid);

  if (pool.sanity_check_required) {
    const action = document.createElement('div');
    action.style.marginTop = '0.9rem';
    const button = document.createElement('button');
    button.className = 'danger';
    button.textContent = `Run sanity check on ${pool.mount_point}`;
    const status = span('muted', replayed
      ? ' replays scripted outcomes; reserves nothing'
      : ' performs real storage work — reserves space, then releases it');
    button.addEventListener('click', async () => {
      button.disabled = true;
      button.textContent = 'reserving space…';
      status.textContent = ' running; this can take up to the probe time budget';
      try {
        const result = await post('/storage/sanity-check', { mount_point: pool.mount_point });
        status.textContent = ` ${result.status.replace(/_/g, ' ')} · stopped: ` +
          `${String(result.stop_reason).replace(/_/g, ' ')}`;
        await refresh();
      } catch (error) {
        button.disabled = false;
        button.textContent = `Run sanity check on ${pool.mount_point}`;
        status.textContent = ` failed: ${error.message}`;
      }
    });
    action.append(button, status);
    card.append(action);
  }
  return card;
}

async function renderRuntime() {
  const panel = document.getElementById('runtime-panel');
  const target = document.getElementById('runtime');
  try {
    const state = await get('/runtime');
    panel.classList.remove('hidden');
    const pairs = [
      ['executor', state.executor],
      ['runtime', state.runtime],
      ['acceptance workload', state.workload || 'none configured'],
    ];
    const execution = state.execution;
    if (execution) {
      pairs.push(
        ['execution id', execution.execution_id],
        ['state', pill(String(execution.state).replace(/_/g, ' '),
          execution.state === 'running' ? 'ok'
            : execution.state === 'failed' ? 'bad' : 'unknown')],
        ['pid', execution.pid],
        ['started', execution.started_at],
        ['exited', execution.exited_at],
        ['exit code', execution.exit_code],
      );
    } else {
      pairs.push(['execution', 'none started']);
    }
    rows(target, pairs);

    if (execution && (execution.stdout || execution.stderr)) {
      for (const stream of ['stdout', 'stderr']) {
        if (!execution[stream]) continue;
        const block = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = stream;
        const pre = document.createElement('pre');
        pre.textContent = execution[stream];
        block.append(summary, pre);
        target.append(block);
      }
    }
    if (state.controls_available) {
      target.append(runtimeControls(execution));
    }
    json(document.getElementById('runtime-json'), state);
  } catch (error) {
    if (error.message.startsWith('404')) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    failure(target, error);
  }
}

function runtimeControls(execution) {
  const wrap = document.createElement('div');
  wrap.style.marginTop = '0.9rem';
  const running = execution && (execution.state === 'running' || execution.state === 'starting');

  const start = document.createElement('button');
  start.textContent = 'Start acceptance workload';
  start.disabled = Boolean(running);
  start.addEventListener('click', async () => {
    start.disabled = true;
    try {
      await post('/runtime/execution', {});
    } finally {
      await refresh();
    }
  });

  const stop = document.createElement('button');
  stop.className = 'danger';
  stop.style.marginLeft = '0.5rem';
  stop.textContent = 'Stop';
  stop.disabled = !running;
  stop.addEventListener('click', async () => {
    stop.disabled = true;
    try {
      await post('/runtime/execution/stop', {});
    } finally {
      await refresh();
    }
  });

  wrap.append(start, stop);
  return wrap;
}

async function renderHost() {
  const target = document.getElementById('host');
  const conflicts = document.getElementById('host-conflicts');
  try {
    const host = await get('/host');
    const profile = await get('/host/profile').catch(() => null);
    const environment = host.operating_environment || {};
    const cpu = host.cpu || {};

    const pairs = [
      ['operating system', `${environment.os_name || '?'} ${environment.os_version || ''}`.trim()],
      ['distribution', environment.distribution],
      ['architecture', environment.architecture],
      ['kernel', environment.kernel_version],
      ['virtualized', environment.virtualized],
      ['cpu', cpu.model_name],
      ['cores / threads', `${fmt(cpu.physical_cores)} / ${fmt(cpu.logical_cores)}`],
      ['reported memory', bytes(host.memory ? host.memory.total_bytes : null)],
      ['deployment memory limit', bytes(host.memory ? host.memory.limit_bytes : null)],
      ['assigned accelerators', (host.accelerators || []).length],
    ];
    for (const accelerator of host.accelerators || []) {
      pairs.push([`accelerator ${accelerator.index}`,
        `${accelerator.vendor} ${fmt(accelerator.model_name)} · ` +
        `${bytes(accelerator.memory_total_bytes).textContent || ''} · driver ${fmt(accelerator.driver_version)}`]);
    }
    for (const mount of host.mounts || []) {
      pairs.push([`mount ${mount.mount_point}`,
        `${fmt(mount.filesystem_type)} · reported total ${bytes(mount.total_bytes).textContent || ''}`]);
    }
    pairs.push(['fingerprint', host.fingerprint]);
    if (profile) {
      pairs.push(
        ['deployment profile', pill(profile.profile, tone(profile.profile === 'compatible' ? 'sufficient' : 'unknown'))],
        ['shape', profile.shape],
        ['earned by', profile.earned_by],
      );
    }
    rows(target, pairs);

    conflicts.replaceChildren();
    for (const conflict of host.conflicts || []) {
      const node = document.createElement('div');
      node.className = 'defect';
      const settled = conflict.resolution
        ? `resolved: ${conflict.resolution}`
        : 'UNRESOLVED — the value is left unknown';
      node.textContent =
        `${conflict.observations.length} competing observation(s) at ` +
        `${conflict.path} — ${settled}`;
      conflicts.append(node);
    }
    json(document.getElementById('host-json'), host);
  } catch (error) {
    failure(target, error);
  }
}

function fmt(value) {
  if (isUnresolved(value)) return unresolvedLabel(value);
  return value === undefined ? 'unknown' : String(value);
}

async function renderProviders() {
  const body = document.querySelector('#providers tbody');
  try {
    const providers = await get('/host/providers');
    body.replaceChildren();
    for (const provider of providers) {
      const row = document.createElement('tr');
      for (const value of [provider.provider, provider.status,
        provider.observations, provider.detail || '']) {
        const cell = document.createElement('td');
        cell.append(plain(value));
        row.append(cell);
      }
      body.append(row);
    }
  } catch (error) {
    body.replaceChildren();
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 4;
    cell.append(span('error', `unavailable: ${error.message}`));
    row.append(cell);
    body.append(row);
  }
}

/* ---------- orchestration --------------------------------------------- */

let refreshing = false;

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    /* All reads. Loading or refreshing this page mutates nothing. */
    await renderMode();
    await renderBuild();
    const envelope = await renderCapacity();
    await renderSanity(envelope);
    await renderRuntime();
    await renderHost();
    await renderProviders();
    await renderProgress();
  } finally {
    refreshing = false;
  }
}

document.getElementById('refresh').addEventListener('click', refresh);
refresh();
