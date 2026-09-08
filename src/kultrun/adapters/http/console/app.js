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
  { name: 'Runtime candidates', probe: '/runtimes/candidates' },
  { name: 'Runtime foundation', probe: '/runtimes/foundation' },
  { name: 'Runtime installations', probe: '/runtimes/installations' },
  { name: 'Runtime capability profiles', probe: '/runtimes/capability-profiles' },
  { name: 'Model catalog', probe: '/models' },
  { name: 'Model selection', probe: '/models/selection' },
  { name: 'Model inventory', probe: '/models/inventory' },
  { name: 'Resource admission', probe: '/resources' },
  { name: 'Inference instances', probe: '/inference/instances' },
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

async function destroy(path) {
  const response = await fetch(API + path, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
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
  if (value === null) return true;
  if (typeof value !== 'object') return false;
  if ('$unresolved' in value) return true;
  return 'kind' in value && String(value.kind).startsWith('unresolved');
}

function unresolvedLabel(value) {
  if (value === null) return 'unknown';
  if (value && typeof value === 'object' && value.$unresolved) {
    const reason = String(value.$unresolved.reason || '').replace(/_/g, ' ');
    return reason || 'unknown';
  }
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
      ['host evidence', String(mode.host_evidence_kind || mode.evidence_mode).replace(/_/g, ' ')],
      ['storage evidence', String(mode.storage_evidence_kind).replace(/_/g, ' ')],
      ['process evidence', String(mode.process_evidence_kind || 'not reported').replace(/_/g, ' ')],
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

    const executor = state.executor || {};
    const profiles = state.profiles || [];
    const executions = state.executions || [];
    const processEvidence = (state.process_evidence && state.process_evidence.kind)
      || 'not reported';
    const profileName = profiles.length
      ? profiles.map((profile) => profile.display_name || profile.runtime).join(', ')
      : 'none registered';

    const containerCapability = state.container_executor_capability || {};
    const pairs = [
      ['executor', executor.identity || 'not reported'],
      ['executor kind', executor.kind || 'not reported'],
      ['container executor', containerCapability.availability || 'not reported'],
      ['runtime / profile', profileName],
      ['acceptance workload', state.workload || 'none configured'],
      ['process evidence', String(processEvidence).replace(/_/g, ' ')],
      ['host evidence mode', String(state.host_evidence_mode || '').replace(/_/g, ' ')],
      ['executions', String(executions.length)],
    ];
    rows(target, pairs);

    if (executions.length === 0) {
      target.append(span('muted', 'No executions started.'));
    }
    for (const execution of executions) {
      target.append(executionCard(execution));
    }

    const controls = state.controls || {};
    if (controls.start_reference || controls.stop) {
      target.append(runtimeControls(executions, controls));
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

async function renderRuntimeCandidates() {
  const panel = document.getElementById('candidates-panel');
  const target = document.getElementById('candidates');
  const summary = document.getElementById('candidates-summary');
  try {
    const state = await get('/runtimes/candidates');
    let foundation = {};
    try {
      foundation = await get('/runtimes/foundation') || {};
    } catch (error) {
      foundation = {};
    }
    panel.classList.remove('hidden');
    const resolution = state.resolution || {};
    const policy = state.policy || {};
    const preferred = resolution.preferred_candidate_id;
    const recommended = foundation.recommended_candidate_id;
    const selected = foundation.selected_candidate_id;
    const byId = {};
    for (const item of foundation.candidates || []) {
      byId[item.candidate_id] = item;
    }
    rows(summary, [
      ['resolver mode', policy.mode || 'not reported'],
      ['selection mode', foundation.selection_mode || 'auto'],
      ['host', state.host_id || 'not reported'],
      ['recommended to provision', recommended && typeof recommended === 'string' ? recommended : 'none'],
      ['selected', selected && typeof selected === 'string' ? selected : 'none'],
      ['downstream stale', foundation.downstream_stale ? 'yes' : 'no'],
      ['mutations', state.mutations === false ? 'none' : 'unexpected'],
    ]);
    target.replaceChildren();
    target.append(foundationActions(foundation));
    const groups = [
      ['candidates', resolution.candidates || []],
      ['unresolved', resolution.unresolved || []],
      ['unsupported', resolution.unsupported || []],
    ];
    let shown = 0;
    for (const [label, items] of groups) {
      for (const item of items) {
        shown += 1;
        const classified = byId[item.candidate_id] || {};
        const card = document.createElement('div');
        card.className = 'pool';
        const head = document.createElement('div');
        head.className = 'pool-head';
        const title = document.createElement('span');
        title.className = 'pool-path';
        title.textContent = `${item.runtime || 'runtime'} / ${item.executor || 'executor'}`;
        const klass = String(item.compatibility || 'unresolved');
        head.append(
          title,
          pill(klass, klass === 'compatible' ? 'ok' : klass === 'unsupported' ? 'bad' : 'unknown'),
        );
        if (classified.role === 'recommended_to_provision') {
          head.append(pill('recommended to provision', 'ok'));
        }
        if (classified.selected) {
          head.append(pill('selected', 'ok'));
        }
        if (classified.confidence) {
          head.append(pill(String(classified.confidence).replace(/_/g, ' '), classified.confidence === 'verified_executable' ? 'ok' : classified.confidence === 'blocked' ? 'bad' : 'unknown'));
        }
        if (preferred && item.candidate_id === preferred && classified.role !== 'recommended_to_provision') {
          head.append(pill('resolver preferred', 'unknown'));
        }
        card.append(head);
        const grid = document.createElement('div');
        grid.className = 'grid';
        rows(grid, [
          ['support tier', item.support_tier],
          ['version', item.version || 'unspecified'],
          ['reason', item.reason],
          ['codes', (item.reason_codes || []).join(', ') || 'none'],
          ['group', label],
          ['role', classified.role || 'unclassified'],
        ]);
        card.append(grid);
        card.append(candidateActions(item, classified));
        target.append(card);
      }
    }
    if (shown === 0) {
      target.append(span('muted', ' No runtime candidates.'));
    }
    json(document.getElementById('candidates-json'), { candidates: state, foundation });
    await renderInstallations();
  } catch (error) {
    if (error.message.startsWith('404')) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    failure(target, error);
  }
}

function foundationActions(foundation) {
  const action = document.createElement('div');
  action.className = 'action';
  const auto = document.createElement('button');
  auto.textContent = 'Use AUTO';
  const realize = document.createElement('button');
  realize.textContent = 'Realize selected';
  const status = span('muted', '');
  auto.addEventListener('click', async () => {
    auto.disabled = true;
    status.textContent = ' selecting AUTO…';
    try {
      const result = await post('/runtimes/foundation/select', { mode: 'auto' });
      status.textContent = ` ${result.selection_mode} ${result.selected_candidate_id || 'none'}`;
      await renderRuntimeCandidates();
    } catch (error) {
      status.textContent = ` ${error.message}`;
    } finally {
      auto.disabled = false;
    }
  });
  realize.addEventListener('click', async () => {
    realize.disabled = true;
    status.textContent = ' realizing…';
    try {
      const installed = await post('/runtimes/foundation/realize', {});
      status.textContent = ` ${installed.status} ${installed.installation_id}`;
      await renderRuntimeCandidates();
    } catch (error) {
      status.textContent = ` ${error.message}`;
    } finally {
      realize.disabled = false;
    }
  });
  action.append(auto, realize, status);
  return action;
}

function candidateActions(item, classified) {
  const action = document.createElement('div');
  action.className = 'action';
  const select = document.createElement('button');
  select.textContent = 'Select foundation';
  select.disabled = classified && classified.confidence === 'blocked';
  const plan = document.createElement('button');
  plan.textContent = 'Create plan';
  const provision = document.createElement('button');
  provision.textContent = 'Provision';
  provision.disabled = true;
  const status = span('muted', '');
  select.addEventListener('click', async () => {
    select.disabled = true;
    status.textContent = ' selecting…';
    try {
      const result = await post('/runtimes/foundation/select', {
        mode: 'manual',
        candidate_id: item.candidate_id,
      });
      status.textContent = ` ${result.selection_mode} ${result.selected_candidate_id || 'none'}`;
      await renderRuntimeCandidates();
    } catch (error) {
      status.textContent = ` ${error.message}`;
    } finally {
      select.disabled = classified && classified.confidence === 'blocked';
    }
  });
  plan.addEventListener('click', async () => {
    plan.disabled = true;
    status.textContent = ' planning…';
    try {
      const created = await post('/runtimes/provisioning-plans', {
        candidate_id: item.candidate_id,
      });
      status.textContent = ` plan ${created.plan_id}`;
      provision.disabled = false;
      provision.dataset.planId = created.plan_id;
    } catch (error) {
      status.textContent = ` ${error.message}`;
    } finally {
      plan.disabled = false;
    }
  });
  provision.addEventListener('click', async () => {
    const planId = provision.dataset.planId;
    if (!planId) return;
    provision.disabled = true;
    status.textContent = ' provisioning…';
    try {
      const installed = await post('/runtimes/provision', { plan_id: planId });
      status.textContent = ` ${installed.status} ${installed.installation_id}`;
      await renderInstallations();
    } catch (error) {
      status.textContent = ` ${error.message}`;
    } finally {
      provision.disabled = false;
    }
  });
  action.append(select, plan, provision, status);
  return action;
}

async function renderInstallations() {
  const target = document.getElementById('installations');
  if (!target) return;
  try {
    const state = await get('/runtimes/installations');
    let profiles = { profiles: [] };
    try {
      profiles = await get('/runtimes/capability-profiles');
    } catch (error) {
      profiles = { profiles: [] };
    }
    const byInstall = {};
    for (const profile of profiles.profiles || []) {
      byInstall[profile.installation_id] = profile;
    }
    target.replaceChildren();
    const items = state.installations || [];
    if (!items.length) {
      target.append(span('muted', ' No runtime installations.'));
      return;
    }
    for (const item of items) {
      const card = document.createElement('div');
      card.className = 'pool';
      const head = document.createElement('div');
      head.className = 'pool-head';
      const title = document.createElement('span');
      title.className = 'pool-path';
      title.textContent = `${item.runtime || 'runtime'} ${item.runtime_version || ''}`;
      const profile = byInstall[item.installation_id];
      const verification = profile ? profile.status : 'unverified';
      head.append(
        title,
        pill(String(item.status || 'unknown'), item.status === 'installed' ? 'ok' : 'unknown'),
        pill(verification, verification === 'verified' ? 'ok' : verification === 'failed' ? 'bad' : 'unknown'),
      );
      card.append(head);
      const grid = document.createElement('div');
      grid.className = 'grid';
      const checks = (profile && profile.checks || []).map((check) => `${check.name}:${check.outcome}`).join(', ');
      const reasons = (profile && profile.reason_codes || []).join(', ');
      rows(grid, [
        ['installation', item.installation_id],
        ['plan', item.plan_id],
        ['executor', item.executor],
        ['host', profile && profile.host_id ? profile.host_id : item.host_id],
        ['path', item.installation_root],
        ['verification', verification],
        ['last verified', profile && profile.verified_at ? profile.verified_at : 'never'],
        ['checks', checks || 'none'],
        ['failure', reasons || (profile && profile.last_failure_message) || 'none'],
      ]);
      card.append(grid);
      card.append(verifyAction(item, profile));
      target.append(card);
    }
  } catch (error) {
    failure(target, error);
  }
}

function verifyAction(item, profile) {
  const action = document.createElement('div');
  action.className = 'action';
  const button = document.createElement('button');
  button.textContent = 'Verify';
  const status = span('muted', profile ? ` ${profile.status}` : ' unverified');
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = ' verifying…';
    try {
      const result = await post('/runtimes/verify', {
        installation_id: item.installation_id,
      });
      status.textContent = ` ${result.status} ${result.profile_id}`;
      await renderInstallations();
    } catch (error) {
      status.textContent = ` ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });
  action.append(button, status);
  return action;
}

function executionCard(execution) {
  const card = document.createElement('div');
  card.className = 'pool';
  const head = document.createElement('div');
  head.className = 'pool-head';
  const title = document.createElement('span');
  title.className = 'pool-path';
  title.textContent = execution.execution_id || 'unknown execution';
  const observed = String(execution.observed_state || '').replace(/_/g, ' ');
  head.append(title, pill(observed,
    execution.observed_state === 'running' ? 'ok'
      : execution.observed_state === 'failed' ? 'bad' : 'unknown'));
  card.append(head);

  const grid = document.createElement('div');
  grid.className = 'grid';
    rows(grid, [
    ['desired state', execution.desired_state],
    ['observed state', execution.observed_state],
    ['executor', execution.executor],
    ['health', execution.health],
    ['ownership', execution.ownership],
    ['pid', execution.pid],
    ['external identity', execution.external_identity],
    ['started', execution.started_at],
    ['exited', execution.exited_at],
    ['exit code', execution.exit_code],
    ['output truncated', execution.output_truncated],
  ]);
  card.append(grid);

  for (const stream of ['stdout', 'stderr']) {
    if (!execution[stream]) continue;
    const block = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = stream;
    const pre = document.createElement('pre');
    pre.textContent = execution[stream];
    block.append(summary, pre);
    card.append(block);
  }
  return card;
}

function runtimeControls(executions, controls) {
  const wrap = document.createElement('div');
  wrap.style.marginTop = '0.9rem';
  const running = executions.some((execution) =>
    execution.observed_state === 'running' || execution.observed_state === 'starting');

  const start = document.createElement('button');
  start.textContent = 'Start test workload';
  start.disabled = !controls.start_reference;
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
  stop.disabled = !controls.stop || !running;
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

async function renderCatalog() {
  const panel = document.getElementById('catalog-panel');
  const summary = document.getElementById('catalog-summary');
  const target = document.getElementById('catalog');
  try {
    const state = await get('/models');
    panel.classList.remove('hidden');
    const source = state.source || {};
    rows(summary, [
      ['source', source.identity || 'not reported'],
      ['live hub fetch', source.live_fetch ? 'yes' : 'no'],
      ['ranking', state.ranking ? 'yes' : 'no'],
      ['selection', state.selection ? 'yes' : 'no'],
      ['download', state.download ? 'yes' : 'no'],
      ['candidates', String((state.candidates || []).length)],
    ]);
    target.replaceChildren();
    if (!state.candidates || state.candidates.length === 0) {
      target.append(span('muted', 'No candidates in the catalog.'));
    }
    for (const entry of state.candidates || []) {
      target.append(catalogCard(entry));
    }
    json(document.getElementById('catalog-json'), state);
  } catch (error) {
    if (error.message.startsWith('404')) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    failure(target, error);
  }
}

function catalogCard(entry) {
  const meta = entry.metadata || {};
  const req = entry.requirement || {};
  const card = document.createElement('div');
  card.className = 'pool';
  const head = document.createElement('div');
  head.className = 'pool-head';
  const title = document.createElement('span');
  title.className = 'pool-path';
  title.textContent = fmt(meta.display_name) !== 'unknown'
    ? fmt(meta.display_name)
    : fmt(meta.logical_name);
  head.append(title, pill(fmt(meta.quantization), 'unknown'));
  card.append(head);
  const grid = document.createElement('div');
  grid.className = 'grid';
  const params = isUnresolved(meta.parameter_count) || meta.parameter_count == null
    ? fmt(meta.parameter_count)
    : `${(Number(meta.parameter_count) / 1e9).toFixed(1)}B`;
  const action = document.createElement('div');
  action.style.marginTop = '0.9rem';
  const button = document.createElement('button');
  button.textContent = 'Acquire';
  const status = span('muted', ' stores this variant; does not start serving');
  button.addEventListener('click', async () => {
    button.disabled = true;
    button.textContent = 'acquiring…';
    try {
      const result = await post('/models/acquire', { candidate: meta.logical_name });
      status.textContent =
        ` ${result.outcome} · ${String(result.state || '').replace(/_/g, ' ')} · serving no`;
      await refresh();
    } catch (error) {
      button.disabled = false;
      button.textContent = 'Acquire';
      status.textContent = ` failed: ${error.message}`;
    }
  });
  action.append(button, status);
  rows(grid, [
    ['source ref', meta.source_ref],
    ['parameters', params],
    ['quantization', meta.quantization],
    ['artifact size', bytes(req.storage_bytes)],
    ['peak acquisition', bytes(req.peak_additional_bytes)],
    ['estimated RAM', bytes(req.ram_bytes)],
    ['estimated VRAM', bytes(req.estimated_vram_bytes)],
    ['unified memory', bytes(req.unified_memory_bytes)],
    ['context', meta.context_length_tokens],
    ['runtime', (meta.supported_runtimes || []).join(', ') || 'unstated'],
    ['license', meta.license_id],
    ['requirement confidence', req.confidence],
    ['estimation method', req.estimation_method],
  ]);
  card.append(grid, action);
  return card;
}

function fallbackLabel(state, rec) {
  const used = state.fallback_used === true || rec.fallback_used === true;
  if (!used) return 'no';
  const reason = state.fallback_reason || rec.fallback_reason;
  if (reason === 'provider_unavailable') return 'llmfit unavailable';
  if (reason && !isUnresolved(reason)) return String(reason).replace(/_/g, ' ');
  return 'yes';
}

function percent(value) {
  if (isUnresolved(value) || value == null) return fmt(value);
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function fitTone(value) {
  if (value === 'preferred') return 'ok';
  if (value === 'underutilized') return 'warn';
  if (value === 'exceeds_safe') return 'bad';
  return 'unknown';
}

async function renderSelection() {
  const panel = document.getElementById('selection-panel');
  const summary = document.getElementById('selection-summary');
  const target = document.getElementById('selection');
  try {
    const state = await get('/models/selection');
    panel.classList.remove('hidden');
    const rec = state.recommendation || {};
    const primary = rec.primary || null;
    const plan = state.plan || null;
    rows(summary, [
      ['estimator mode', state.estimator_mode || rec.estimator_mode],
      ['active estimator', state.estimator_provider || rec.estimator_provider],
      ['estimator version', state.estimator_version || rec.estimator_version],
      ['fallback', fallbackLabel(state, rec)],
      ['policy', state.policy_version || rec.policy_version],
      ['outcome', state.outcome || rec.outcome],
    ]);
    target.replaceChildren();
    if (primary) {
      const card = document.createElement('div');
      card.className = 'pool';
      const head = document.createElement('div');
      head.className = 'pool-head';
      const title = document.createElement('span');
      title.className = 'pool-path';
      title.textContent = fmt(primary.logical_name);
      head.append(title, pill(fmt(primary.capacity_fit), fitTone(primary.capacity_fit)));
      card.append(head);
      const grid = document.createElement('div');
      grid.className = 'grid';
      const util = primary.utilization || {};
      rows(grid, [
        ['requirement RAM', bytes(primary.required_ram_bytes)],
        ['requirement VRAM', bytes(primary.required_vram_bytes)],
        ['SAFE RAM', bytes(primary.safe_ram_bytes)],
        ['SAFE VRAM', bytes(primary.safe_vram_bytes)],
        ['utilization', percent(util.ratio)],
        ['limiting resource', util.limiting_resource],
        ['fit class', primary.capacity_fit],
        ['quantization', primary.quantization],
      ]);
      card.append(grid);
      target.append(card);
    } else {
      target.append(span('muted', 'No preferred candidate for this host and policy.'));
    }
    if (plan) {
      const note = document.createElement('p');
      note.className = 'note';
      note.textContent =
        `Plan: ${fmt(plan.logical_name)} · placement ${fmt(plan.placement)} · ` +
        `estimator ${fmt(plan.estimator_provider)}`;
      target.append(note);
    }
    json(document.getElementById('selection-json'), state);
  } catch (error) {
    if (error.message.startsWith('404')) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    failure(target, error);
  }
}

async function renderInventory() {
  const panel = document.getElementById('inventory-panel');
  const summary = document.getElementById('inventory-summary');
  const target = document.getElementById('inventory');
  try {
    const state = await get('/models/inventory');
    panel.classList.remove('hidden');
    rows(summary, [
      ['stored artifacts', String(state.count || 0)],
      ['running instances', String((state.running || []).length)],
      ['stored implies running', state.stored_implies_running ? 'yes' : 'no'],
      ['serving', state.serving ? 'yes' : 'no'],
      ['provider', (state.provider && state.provider.identity) || 'not reported'],
    ]);
    target.replaceChildren();
    target.append(span('muted',
      'Stored artifacts occupy disk. They are not loaded, reserved, or serving.'));
    if (state.acceptance_target) {
      target.append(acceptanceAcquire(state.acceptance_target));
    }
    if (!state.artifacts || state.artifacts.length === 0) {
      target.append(span('muted', 'No stored artifacts.'));
    }
    for (const artifact of state.artifacts || []) {
      target.append(inventoryCard(artifact));
    }
    json(document.getElementById('inventory-json'), state);
  } catch (error) {
    if (error.message.startsWith('404')) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    failure(target, error);
  }
}

function acceptanceAcquire(target) {
  const wrap = document.createElement('div');
  wrap.className = 'pool';
  const head = document.createElement('div');
  head.className = 'pool-head';
  const title = document.createElement('span');
  title.className = 'pool-path';
  title.textContent = target.logical_name;
  head.append(title, pill('acceptance target', 'unknown'));
  wrap.append(head);
  const note = document.createElement('p');
  note.className = 'note';
  note.textContent = target.note || 'bounded provider proof; not a recommendation';
  wrap.append(note);
  const button = document.createElement('button');
  button.textContent = 'Acquire acceptance artifact';
  const status = span('muted', ` ${target.source_ref || ''}`);
  button.addEventListener('click', async () => {
    button.disabled = true;
    button.textContent = 'acquiring…';
    try {
      const result = await post('/models/acquire', { candidate: target.logical_name });
      status.textContent =
        ` ${result.outcome} · ${String(result.state || '').replace(/_/g, ' ')} · serving no`;
      await refresh();
    } catch (error) {
      button.disabled = false;
      button.textContent = 'Acquire acceptance artifact';
      status.textContent = ` failed: ${error.message}`;
    }
  });
  wrap.append(button, status);
  return wrap;
}

function inventoryCard(artifact) {
  const card = document.createElement('div');
  card.className = 'pool';
  const head = document.createElement('div');
  head.className = 'pool-head';
  const title = document.createElement('span');
  title.className = 'pool-path';
  title.textContent = fmt(artifact.logical_name);
  const state = String(artifact.state || '').replace(/_/g, ' ');
  head.append(title, pill(state, artifact.state === 'stored' ? 'ok' : 'unknown'));
  card.append(head);
  const grid = document.createElement('div');
  grid.className = 'grid';
  rows(grid, [
    ['artifact id', artifact.artifact_id],
    ['revision', artifact.revision],
    ['quantization', artifact.quantization],
    ['format', artifact.artifact_format],
    ['state', artifact.state],
    ['verification', artifact.verification_state],
    ['disk usage', bytes(artifact.installed_bytes)],
    ['source', artifact.source_ref],
    ['acquired', artifact.acquired_at],
    ['provider', artifact.acquisition_provider],
    ['serving', 'no'],
  ]);
  card.append(grid);
  const action = document.createElement('div');
  action.style.marginTop = '0.9rem';
  const button = document.createElement('button');
  button.className = 'danger';
  button.textContent = 'Delete';
  const status = span('muted', ' removes stored files; does not stop a runtime');
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await destroy('/models/artifact?artifact_id=' + encodeURIComponent(artifact.artifact_id));
      await refresh();
    } catch (error) {
      button.disabled = false;
      status.textContent = ` failed: ${error.message}`;
    }
  });
  if (artifact.state === 'stored') {
    const reserve = document.createElement('button');
    reserve.textContent = 'Reserve';
    const reserveStatus = span('muted', ' commits capacity; does not start a process');
    reserve.addEventListener('click', async () => {
      reserve.disabled = true;
      try {
        const result = await post('/resources/reservations', {
          artifact_id: artifact.artifact_id,
        });
        reserveStatus.textContent =
          ` ${result.verdict} · serving no`;
        await refresh();
      } catch (error) {
        reserve.disabled = false;
        reserveStatus.textContent = ` failed: ${error.message}`;
      }
    });
    action.append(reserve, reserveStatus);
  }
  action.append(button, status);
  card.append(action);
  return card;
}

async function renderResources() {
  const panel = document.getElementById('resources-panel');
  const summary = document.getElementById('resources-summary');
  const target = document.getElementById('resources');
  try {
    const state = await get('/resources');
    const listing = await get('/resources/reservations');
    panel.classList.remove('hidden');
    const body = state.summary || {};
    rows(summary, [
      ['ledger health', body.health],
      ['active reservations', String(body.active_count || 0)],
      ['running instances', String(state.running_instances || 0)],
      ['reserved implies running', state.reserved_implies_running ? 'yes' : 'no'],
      ['RAM SAFE', bytes(body.safe_ram_bytes)],
      ['RAM reserved', bytes(body.reserved_ram_bytes)],
      ['RAM available', bytes(body.available_ram_bytes)],
    ]);
    for (const device of body.accelerators || []) {
      rows(summary, [
        [`GPU ${device.index} SAFE`, bytes(device.safe_bytes)],
        [`GPU ${device.index} reserved`, bytes(device.reserved_bytes)],
        [`GPU ${device.index} available`, bytes(device.available_bytes)],
      ]);
    }
    target.replaceChildren();
    target.append(span('muted',
      'SAFE / RESERVED / AVAILABLE are the ledger. Stored and active are states, not capacity partitions.'));
    if (!listing.reservations || listing.reservations.length === 0) {
      target.append(span('muted', ' No active reservations.'));
    }
    const inUse = new Set(listing.in_use_reservation_ids || []);
    for (const item of listing.reservations || []) {
      target.append(reservationCard(item, inUse.has(item.reservation_id)));
    }
    json(document.getElementById('resources-json'), { summary: state, reservations: listing });
  } catch (error) {
    if (error.message.startsWith('404')) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    failure(target, error);
  }
}

function reservationCard(item, inUse) {
  const card = document.createElement('div');
  card.className = 'pool';
  const head = document.createElement('div');
  head.className = 'pool-head';
  const title = document.createElement('span');
  title.className = 'pool-path';
  title.textContent = fmt(item.logical_name);
  head.append(title, pill(String(item.state || '').replace(/_/g, ' '),
    item.state === 'active' ? 'ok' : 'unknown'));
  card.append(head);
  const grid = document.createElement('div');
  grid.className = 'grid';
  rows(grid, [
    ['reservation id', item.reservation_id],
    ['artifact', item.artifact_id],
    ['state', item.state],
    ['RAM reserved', bytes(item.admitted_ram_bytes)],
    ['accelerator', item.accelerator_index == null ? 'none' : String(item.accelerator_index)],
    ['accelerator memory', bytes(item.admitted_vram_bytes)],
    ['unified memory', bytes(item.admitted_unified_bytes)],
    ['created', item.created_at],
    ['estimator', item.estimator_provider],
    ['serving', inUse ? 'instance in use' : 'no'],
  ]);
  card.append(grid);
  const action = document.createElement('div');
  action.style.marginTop = '0.9rem';
  const button = document.createElement('button');
  button.className = 'danger';
  button.textContent = 'Release';
  const status = span('muted', inUse
    ? ' blocked while a live instance uses this reservation'
    : ' frees the commitment; does not stop a runtime');
  if (inUse) {
    button.disabled = true;
  }
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await destroy('/resources/reservations?reservation_id=' +
        encodeURIComponent(item.reservation_id));
      await refresh();
    } catch (error) {
      button.disabled = false;
      status.textContent = ` failed: ${error.message}`;
    }
  });
  action.append(button, status);
  const create = document.createElement('button');
  create.textContent = 'Create instance';
  const createStatus = span('muted', ' record only; does not start');
  create.addEventListener('click', async () => {
    create.disabled = true;
    try {
      await post('/inference/instances', { reservation_id: item.reservation_id });
      await refresh();
    } catch (error) {
      create.disabled = false;
      createStatus.textContent = ` failed: ${error.message}`;
    }
  });
  action.append(create, createStatus);
  card.append(action);
  return card;
}

async function renderInstances() {
  const panel = document.getElementById('instances-panel');
  const summary = document.getElementById('instances-summary');
  const target = document.getElementById('instances');
  try {
    const listing = await get('/inference/instances');
    panel.classList.remove('hidden');
    const items = listing.instances || [];
    rows(summary, [
      ['instances', String(listing.count || items.length)],
      ['fixed stored/active partition', listing.fixed_stored_active_partition ? 'yes' : 'no'],
    ]);
    target.replaceChildren();
    if (items.length === 0) {
      target.append(span('muted', ' No inference instances.'));
    }
    for (const item of items) {
      target.append(instanceCard(item));
    }
    json(document.getElementById('instances-json'), listing);
  } catch (error) {
    if (error.message.startsWith('404')) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    failure(target, error);
  }
}

function instanceCard(item) {
  const card = document.createElement('div');
  card.className = 'pool';
  const head = document.createElement('div');
  head.className = 'pool-head';
  const title = document.createElement('span');
  title.className = 'pool-path';
  title.textContent = item.instance_id;
  const observed = String(item.observed_state || '');
  head.append(title, pill(observed.replace(/_/g, ' '),
    observed === 'running' ? 'ok' : observed === 'failed' ? 'bad' : 'unknown'));
  card.append(head);
  const grid = document.createElement('div');
  grid.className = 'grid';
  const endpoint = item.endpoint
    ? `${item.endpoint.address}:${item.endpoint.port}`
    : null;
  rows(grid, [
    ['instance id', item.instance_id],
    ['artifact', item.artifact_id],
    ['reservation', item.reservation_id],
    ['desired', item.desired_state],
    ['observed', item.observed_state],
    ['runtime', item.runtime],
    ['executor', item.executor],
    ['execution id', item.execution_id],
    ['pid', item.pid],
    ['endpoint', endpoint],
    ['ready', item.ready],
    ['created', item.created_at],
    ['started', item.started_at],
    ['stopped', item.stopped_at],
    ['failure', item.failure_reason],
  ]);
  card.append(grid);
  const action = document.createElement('div');
  action.style.marginTop = '0.9rem';
  const start = document.createElement('button');
  start.textContent = 'Start';
  const stop = document.createElement('button');
  stop.className = 'danger';
  stop.textContent = 'Stop';
  const status = span('muted', ' stop does not release the reservation');
  start.addEventListener('click', async () => {
    start.disabled = true;
    try {
      await post('/inference/instances/start', { instance_id: item.instance_id });
      await refresh();
    } catch (error) {
      start.disabled = false;
      status.textContent = ` failed: ${error.message}`;
    }
  });
  stop.addEventListener('click', async () => {
    stop.disabled = true;
    try {
      await post('/inference/instances/stop', { instance_id: item.instance_id });
      await refresh();
    } catch (error) {
      stop.disabled = false;
      status.textContent = ` failed: ${error.message}`;
    }
  });
  action.append(start, stop, status);
  card.append(action);
  return card;
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
    await renderRuntimeCandidates();
    await renderCatalog();
    await renderSelection();
    await renderInventory();
    await renderResources();
    await renderInstances();
    await renderHost();
    await renderProviders();
    await renderProgress();
  } finally {
    refreshing = false;
  }
}

document.getElementById('refresh').addEventListener('click', refresh);
refresh();
