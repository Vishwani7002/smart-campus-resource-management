/* Smart Campus — single-page frontend (vanilla JS, no build step) */
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const view = html => { $('#view').innerHTML = html; };
const S = { me: null, types: [], depts: [] };
const pad = n => String(n).padStart(2, '0');
const ymd = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const today = () => ymd(new Date());
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'], MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function prettyDay(s) { const d = new Date(s.replace(' ', 'T')); return `${DAYS[d.getDay()]} ${d.getDate()} ${MON[d.getMonth()]}`; }
const when = (a, b) => `${prettyDay(a)}, ${a.slice(11)}–${b.slice(11)}`;
const badge = s => `<span class="badge ${esc(s)}">${esc(String(s).replace('_', ' '))}</span>`;
const empty = (t, d) => `<div class="empty"><b>${esc(t)}</b>${esc(d || '')}</div>`;

async function api(path, method = 'GET', body) {
  const r = await fetch('/api' + path, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined, credentials: 'same-origin' });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(data.error || 'Something went wrong'); e.status = r.status; e.data = data; throw e; }
  return data;
}
function toast(msg, type = '') {
  const t = document.createElement('div'); t.className = 'toast ' + type; t.textContent = msg;
  $('#toasts').appendChild(t); setTimeout(() => t.remove(), 4200);
}
function modal(html) {
  $('#modal-root').innerHTML = `<div class="overlay" id="ov"><div class="modal" role="dialog" aria-modal="true">${html}</div></div>`;
  $('#ov').addEventListener('mousedown', e => { if (e.target.id === 'ov') closeModal(); });
}
const closeModal = () => { $('#modal-root').innerHTML = ''; };
const typeOptions = (sel, all) => (all ? `<option value="">All types</option>` : '') + S.types.map(t => `<option value="${t.type_id}" ${String(sel) === String(t.type_id) ? 'selected' : ''}>${esc(t.icon)} ${esc(t.type_name)}</option>`).join('');
const deptOptions = () => `<option value="">Select department</option>` + S.depts.map(d => `<option value="${d.dept_id}">${esc(d.name)}</option>`).join('');
const isAdmin = () => S.me.role === 'admin';

/* ============================ AUTH ============================ */
function showAuth(tab = 'login') {
  $('#app').classList.add('hidden'); $('#auth').classList.remove('hidden');
  const box = $('#auth-box');
  if (tab === 'login') {
    box.innerHTML = `
      <div class="tabs"><button class="on">Log in</button><button id="to-reg">Create account</button></div>
      <h2>Welcome back</h2><p class="sub">Log in to book and manage campus resources.</p>
      <div id="a-err"></div>
      <div class="field"><label for="l-email">Email</label><input id="l-email" type="email" autocomplete="username" placeholder="you@campus.edu"></div>
      <div class="field"><label for="l-pass">Password</label><input id="l-pass" type="password" autocomplete="current-password" placeholder="Your password"></div>
      <button class="btn full" id="l-go">Log in</button>
      <div class="demo"><b>Demo accounts</b><br>
        <button data-e="admin@campus.edu" data-p="admin123">Administrator</button> ·
        <button data-e="meera.rao@campus.edu" data-p="faculty123">Faculty</button> ·
        <button data-e="rahul@campus.edu" data-p="student123">Student</button></div>`;
    $('#to-reg').onclick = () => showAuth('register');
    $('#l-go').onclick = doLogin;
    box.querySelectorAll('.demo button').forEach(b => b.onclick = () => { $('#l-email').value = b.dataset.e; $('#l-pass').value = b.dataset.p; doLogin(); });
    box.addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
  } else {
    box.innerHTML = `
      <div class="tabs"><button id="to-login">Log in</button><button class="on">Create account</button></div>
      <h2>Join Smart Campus</h2><p class="sub">New here? Register to start booking resources.</p>
      <div id="a-err"></div>
      <div class="field"><label for="r-name">Full name</label><input id="r-name" autocomplete="name" placeholder="e.g. Priya Menon"></div>
      <div class="field"><label for="r-email">Email</label><input id="r-email" type="email" autocomplete="email" placeholder="you@campus.edu"></div>
      <div class="row2">
        <div class="field"><label for="r-role">I am a</label><select id="r-role"><option value="student">Student</option><option value="faculty">Faculty</option><option value="staff">Staff</option></select></div>
        <div class="field"><label for="r-phone">Phone (optional)</label><input id="r-phone" placeholder="9876543210"></div>
      </div>
      <div class="field"><label for="r-dept">Department</label><select id="r-dept">${deptOptions()}</select></div>
      <div class="field"><label for="r-pass">Password</label><input id="r-pass" type="password" autocomplete="new-password" placeholder="At least 6 characters"></div>
      <button class="btn full" id="r-go">Create account</button>`;
    $('#to-login').onclick = () => showAuth('login');
    $('#r-go').onclick = doRegister;
  }
}
const authErr = m => { $('#a-err').innerHTML = `<div class="form-err" role="alert">${esc(m)}</div>`; };
async function doLogin() {
  try { S.me = await api('/login', 'POST', { email: $('#l-email').value, password: $('#l-pass').value }); boot(true); }
  catch (e) { authErr(e.message); }
}
async function doRegister() {
  try {
    S.me = await api('/register', 'POST', { full_name: $('#r-name').value, email: $('#r-email').value, password: $('#r-pass').value, role: $('#r-role').value, dept_id: $('#r-dept').value, phone: $('#r-phone').value });
    toast(`Welcome, ${S.me.full_name}! Your account is ready.`); boot(true);
  } catch (e) { authErr(e.message); }
}
async function logout() { await api('/logout', 'POST'); S.me = null; showAuth('login'); }

/* ============================ SHELL ============================ */
const NAV = [
  ['dashboard', '▦', 'Dashboard'], ['resources', '🏫', 'Resources'], ['book', '➕', 'Book a resource'], ['schedule', '🗓️', 'Schedule'],
  ['bookings', '📋', null], ['maintenance', '🛠️', 'Maintenance'],
  ['-', 'Admin'], ['reports', '📊', 'Reports', 1], ['audit', '🧾', 'Audit log', 1], ['users', '👥', 'Users', 1],
];
function buildNav() {
  $('#nav').innerHTML = NAV.filter(n => n[0] === '-' ? isAdmin() : (!n[3] || isAdmin())).map(n => n[0] === '-'
    ? `<div class="nav-h">${n[1]}</div>`
    : `<a data-p="${n[0]}" tabindex="0"><i>${n[1]}</i>${esc(n[2] || (isAdmin() ? 'All bookings' : 'My bookings'))}</a>`).join('')
    + `<a id="nav-out" tabindex="0" style="margin-top:12px"><i>⎋</i>Log out</a>`;
  $('#nav').querySelectorAll('a[data-p]').forEach(a => { a.onclick = () => go(a.dataset.p); a.onkeydown = e => { if (e.key === 'Enter') go(a.dataset.p); }; });
  $('#nav-out').onclick = logout;
  $('#u-av').textContent = S.me.full_name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
  $('#u-name').textContent = S.me.full_name; $('#u-role').textContent = S.me.role;
}
function go(p) { location.hash = p; }
async function route() {
  if (!S.me) return;
  const p = (location.hash || '#dashboard').slice(1);
  const page = PAGES[p] || PAGES.dashboard;
  document.querySelectorAll('.nav a[data-p]').forEach(a => a.classList.toggle('on', a.dataset.p === p));
  view('<div class="spin">Loading…</div>');
  try { await page(); } catch (e) { if (e.status === 401) return showAuth(); view(empty('Could not load this page', e.message)); }
  window.scrollTo(0, 0);
}
function header(title, sub, actions = '') {
  return `<div class="topbar"><div><h1>${esc(title)}</h1><p>${esc(sub || '')}</p></div><div class="top-actions">${actions}
    <button class="btn ghost bell" id="bell" aria-label="Notifications">🔔<span class="dot hidden" id="bell-n"></span></button></div></div>`;
}
async function wireBell() {
  const b = $('#bell'); if (!b) return;
  const n = await api('/notifications').catch(() => ({ items: [], unread: 0 }));
  if (n.unread) { const d = $('#bell-n'); d.textContent = n.unread; d.classList.remove('hidden'); }
  b.onclick = async () => {
    modal(`<h2>Notifications</h2>${n.items.length ? n.items.map(i => `<div class="notif ${i.is_read ? '' : 'new'}">${esc(i.message)}<small>${esc(i.created_at)}</small></div>`).join('') : empty('All caught up', 'Booking updates will appear here.')}<div class="btns"><button class="btn ghost" onclick="closeModal()">Close</button></div>`);
    if (n.unread) { await api('/notifications/read', 'POST'); $('#bell-n').classList.add('hidden'); }
  };
}
const PAGES = {};

/* ============================ DASHBOARD ============================ */
PAGES.dashboard = async () => {
  const d = await api('/dashboard'), s = d.stats, first = S.me.full_name.replace(/^(Dr|Prof)\.?\s+/i, '').split(' ')[0];
  const hr = new Date().getHours(), greet = hr < 12 ? 'morning' : hr < 17 ? 'afternoon' : 'evening';
  const max = Math.max(1, ...d.top.map(t => t.total_hours));
  view(`${header('Dashboard', 'Live overview of campus resources')}
    <div class="welcome"><div><h2>Good ${greet}, ${esc(first)}</h2><p>${isAdmin() ? `${s.pending} booking request${s.pending === 1 ? '' : 's'} waiting for your decision.` : 'Find a free room, lab or projector in a few clicks.'}</p>
      <div style="margin-top:14px"><button class="btn" onclick="go('book')">Book a resource</button></div></div>
      <div class="shield"><b>${s.conflicts_blocked}</b><small>double-bookings<br>blocked by the database</small></div></div>
    <div class="grid g3" style="margin-bottom:16px">
      <div class="card stat"><div class="ic t">🏛️</div><div><b>${s.resources}</b><span>Total resources</span></div></div>
      <div class="card stat"><div class="ic g">✅</div><div><b>${s.available_now}</b><span>Free right now</span></div></div>
      <div class="card stat"><div class="ic b">📡</div><div><b>${s.in_use_now}</b><span>In use now</span></div></div>
      <div class="card stat"><div class="ic a">⏳</div><div><b>${s.pending}</b><span>${isAdmin() ? 'Awaiting approval' : 'My pending requests'}</span></div></div>
      <div class="card stat"><div class="ic c">🛠️</div><div><b>${s.maintenance}</b><span>Under maintenance</span></div></div>
      <div class="card stat"><div class="ic t">📅</div><div><b>${s.today}</b><span>${isAdmin() ? 'Bookings today' : 'My bookings today'}</span></div></div>
    </div>
    <div class="grid g2">
      <div class="card"><h3>${isAdmin() ? "Today's bookings" : "My bookings today"}</h3>
        ${d.today.length ? `<div class="tbl-wrap"><table><tr><th>Time</th><th>Resource</th><th>Booked by</th><th>Status</th></tr>${d.today.map(b => `<tr><td>${b.start_time.slice(11)}–${b.end_time.slice(11)}</td><td>${esc(b.icon)} ${esc(b.resource_name)}</td><td>${esc(b.user_name)}</td><td>${badge(b.status)}</td></tr>`).join('')}</table></div>` : empty('Nothing scheduled today', 'Booked resources will show up here.')}</div>
      <div class="grid" style="align-content:start">
        <div class="card"><h3>Most used resources</h3><div class="bars">${d.top.map(t => `<div class="bar-row"><span class="nm">${esc(t.icon)} ${esc(t.name)}</span><div class="bar"><i style="width:${t.total_hours / max * 100}%"></i></div><b>${t.total_hours}h</b></div>`).join('')}</div></div>
        <div class="card"><h3>My upcoming</h3>${d.upcoming.length ? d.upcoming.map(b => `<div class="notif"><b>${esc(b.resource_name)}</b> ${badge(b.status)}<small>${esc(when(b.start_time, b.end_time))} · ${esc(b.title)}</small></div>`).join('') : empty('No upcoming bookings', 'Book a resource to get started.')}</div>
      </div></div>`);
  wireBell();
};

/* ============================ RESOURCES ============================ */
PAGES.resources = async () => {
  const f = { type_id: '', q: '', status: '' };
  view(`${header('Resources', 'Classrooms, labs, halls and equipment', isAdmin() ? '<button class="btn" id="add-res">Add resource</button>' : '')}
    <div class="filters"><input id="f-q" placeholder="Search by name or building" aria-label="Search"><select id="f-t">${typeOptions('', true)}</select>
    <select id="f-s"><option value="">Any status</option><option value="available">Available</option><option value="maintenance">Maintenance</option><option value="retired">Retired</option></select></div>
    <div id="rlist"></div>`);
  wireBell();
  async function load() {
    const list = await api(`/resources?type_id=${f.type_id}&q=${encodeURIComponent(f.q)}&status=${f.status}`);
    $('#rlist').innerHTML = list.length ? `<div class="rgrid">${list.map(r => `
      <div class="rcard ${r.status}"><div class="top"><div><h3>${esc(r.name)}</h3><div class="meta">${esc(r.building)}${r.floor ? ' · Floor ' + r.floor : ''}</div></div><span class="ico">${esc(r.icon)}</span></div>
      <div class="tags"><span class="tag">${esc(r.type_name)}</span>${r.capacity ? `<span class="tag">👥 ${r.capacity} seats</span>` : ''}${r.parent_name ? `<span class="tag">in ${esc(r.parent_name)}</span>` : ''}${r.equipment.map(e => `<span class="tag">🔌 ${esc(e)}</span>`).join('')}</div>
      <div class="meta">${esc(r.description || '')}</div>
      <div class="foot">${badge(r.status)}<span style="flex:1"></span>
        ${r.status === 'available' ? `<button class="btn sm" data-book="${r.resource_id}">Book</button>` : ''}
        <button class="btn sm ghost" data-sched="${r.resource_id}">Schedule</button>
        ${isAdmin() ? `<button class="btn sm ghost" data-edit="${r.resource_id}">Edit</button>` : ''}</div></div>`).join('')}</div>` : empty('No resources match', 'Try a different search or filter.');
    document.querySelectorAll('[data-book]').forEach(b => b.onclick = () => { S.preset = { resource_id: +b.dataset.book }; go('book'); });
    document.querySelectorAll('[data-sched]').forEach(b => b.onclick = () => { S.preset = { resource_id: +b.dataset.sched }; go('schedule'); });
    document.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => resourceForm(list.find(r => r.resource_id == b.dataset.edit), list, load));
  }
  let t; $('#f-q').oninput = e => { clearTimeout(t); t = setTimeout(() => { f.q = e.target.value; load(); }, 250); };
  $('#f-t').onchange = e => { f.type_id = e.target.value; load(); }; $('#f-s').onchange = e => { f.status = e.target.value; load(); };
  if (isAdmin()) $('#add-res').onclick = async () => resourceForm(null, await api('/resources'), load);
  load();
};
function resourceForm(r, all, reload) {
  const rooms = all.filter(x => !x.is_equipment && (!r || x.resource_id !== r.resource_id));
  modal(`<h2>${r ? 'Edit resource' : 'Add resource'}</h2><div id="m-err"></div>
    <div class="field"><label>Name</label><input id="x-name" value="${esc(r?.name || '')}"></div>
    <div class="row2"><div class="field"><label>Type</label><select id="x-type">${typeOptions(r?.type_id || '')}</select></div>
    <div class="field"><label>Capacity (0 for equipment)</label><input id="x-cap" type="number" min="0" value="${r?.capacity ?? 30}"></div></div>
    <div class="row2"><div class="field"><label>Building</label><input id="x-bld" value="${esc(r?.building || '')}"></div>
    <div class="field"><label>Floor</label><input id="x-floor" type="number" value="${r?.floor ?? 0}"></div></div>
    <div class="field"><label>Installed in (optional, for equipment)</label><select id="x-par"><option value="">None</option>${rooms.map(x => `<option value="${x.resource_id}" ${r?.parent_id === x.resource_id ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></div>
    ${r ? `<div class="field"><label>Status</label><select id="x-status">${['available', 'maintenance', 'retired'].map(s => `<option ${r.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></div>` : ''}
    <div class="field"><label>Description</label><textarea id="x-desc" rows="2">${esc(r?.description || '')}</textarea></div>
    <div class="btns"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn" id="x-save">${r ? 'Save changes' : 'Add resource'}</button></div>`);
  $('#x-save').onclick = async () => {
    const body = { name: $('#x-name').value, type_id: $('#x-type').value, capacity: $('#x-cap').value, building: $('#x-bld').value, floor: $('#x-floor').value, parent_id: $('#x-par').value, description: $('#x-desc').value };
    if (r) body.status = $('#x-status').value;
    try {
      const out = r ? await api('/resources/' + r.resource_id, 'PUT', body) : await api('/resources', 'POST', body);
      closeModal(); toast(r ? `Saved ${out.name}.${out.cancelled_bookings ? ` ${out.cancelled_bookings} booking(s) auto-cancelled.` : ''}` : `Added ${out.name}.`); reload();
    } catch (e) { $('#m-err').innerHTML = `<div class="form-err">${esc(e.message)}</div>`; }
  };
}

/* ============================ BOOK ============================ */
PAGES.book = async () => {
  const preset = S.preset || {}; S.preset = null;
  let d = new Date(); d.setMinutes(0, 0, 0); d.setHours(d.getHours() + 1);
  let day = ymd(d), st = pad(d.getHours()) + ':00', en = pad(d.getHours() + 1) + ':00';
  if (d.getHours() >= 21 || d.getHours() < 7) { const n = new Date(Date.now() + (d.getHours() >= 21 ? 864e5 : 0)); day = ymd(n); st = '09:00'; en = '10:00'; }
  let sel = preset.resource_id || null, list = [];
  view(`${header('Book a resource', 'Pick a time, choose a resource, confirm')}
    <div class="steps">
      <div class="card"><h3>1 · When do you need it?</h3>
        <div class="field"><label for="b-day">Date</label><input id="b-day" type="date" min="${today()}" value="${day}"></div>
        <div class="row2"><div class="field"><label for="b-st">From</label><input id="b-st" type="time" min="07:00" max="22:00" value="${st}"></div><div class="field"><label for="b-en">To</label><input id="b-en" type="time" min="07:00" max="22:00" value="${en}"></div></div>
        <div class="row2"><div class="field"><label for="b-type">Type</label><select id="b-type">${typeOptions('', true)}</select></div><div class="field"><label for="b-att">People</label><input id="b-att" type="number" min="1" value="10"></div></div>
        <p style="color:var(--muted);font-size:.82rem">Availability updates as you change the time. Campus hours: 07:00–22:00.</p></div>
      <div class="card"><h3>2 · Choose a resource</h3><div class="pick" id="b-list"></div></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>3 · Details</h3><div id="b-msg"></div>
      <div class="grid g2e"><div class="field"><label for="b-title">Title / purpose</label><input id="b-title" placeholder="e.g. DBMS practical session"></div>
      <div class="field"><label>Selected resource</label><input id="b-sel" readonly placeholder="Choose a resource above"></div></div>
      <p style="color:var(--muted);font-size:.85rem;margin-bottom:12px">${['admin', 'faculty'].includes(S.me.role) ? 'Your booking is confirmed instantly.' : 'Your request will be confirmed after admin approval, and the slot is held for you meanwhile.'}</p>
      <button class="btn" id="b-go">Confirm booking</button></div>`);
  wireBell();
  const val = () => ({ day: $('#b-day').value, st: $('#b-st').value, en: $('#b-en').value });
  const paintSel = () => { const r = list.find(x => x.resource_id === sel); $('#b-sel').value = r ? `${r.name}${r.free ? '' : '  (busy — try anyway to see alternatives)'}` : ''; };
  async function refresh() {
    const v = val(); if (!v.day || !v.st || !v.en) return;
    try {
      list = await api(`/availability?start=${v.day} ${v.st}&end=${v.day} ${v.en}&type_id=${$('#b-type').value}&capacity=0`);
      list.sort((a, b) => b.free - a.free);
      $('#b-list').innerHTML = list.length ? list.map(r => `<button class="opt ${r.free ? '' : 'busy'} ${r.resource_id === sel ? 'sel' : ''}" data-id="${r.resource_id}">
        <span class="ico">${esc(r.icon)}</span><span><b>${esc(r.name)}</b><small>${esc(r.free ? `${r.building}${r.capacity ? ' · ' + r.capacity + ' seats' : ''}` : r.reason)}</small></span><span class="st">${badge(r.free ? 'free' : 'busy')}</span></button>`).join('') : empty('Nothing found', 'Try another type.');
      document.querySelectorAll('.opt').forEach(o => o.onclick = () => { sel = +o.dataset.id; document.querySelectorAll('.opt').forEach(x => x.classList.toggle('sel', x === o)); paintSel(); });
      paintSel();
    } catch (e) { $('#b-list').innerHTML = empty('Check your times', e.message); }
  }
  ['b-day', 'b-st', 'b-en', 'b-type'].forEach(id => $('#' + id).addEventListener('change', refresh));
  async function submit(over = {}) {
    const v = { ...val(), ...over };
    if (!sel) { $('#b-msg').innerHTML = `<div class="form-err">Choose a resource first.</div>`; return; }
    $('#b-go').disabled = true;
    try {
      const b = await api('/bookings', 'POST', { resource_id: over.resource_id || sel, title: $('#b-title').value, start: `${v.day} ${v.st}`, end: `${v.day} ${v.en}`, attendees: $('#b-att').value });
      toast(b.status === 'approved' ? `Booked ${b.resource_name}. You're all set.` : `Request sent for ${b.resource_name}. Waiting for approval.`);
      go('bookings');
    } catch (e) {
      $('#b-go').disabled = false;
      const x = e.data || {};
      if (e.status === 409) {
        $('#b-msg').innerHTML = `<div class="conflict" role="alert"><h4>Slot not available</h4><p>${esc(e.message)} The database blocked this request to prevent a double booking.</p>
          ${x.next_slots?.length ? `<div>Free times on this resource:</div><div class="suggest">${x.next_slots.map(s => `<button class="btn sm" data-slot="${s.start}|${s.end}">${esc(s.start.slice(11))}–${esc(s.end.slice(11))}</button>`).join('')}</div>` : ''}
          ${x.alternatives?.length ? `<div style="margin-top:10px">Other free ${esc(list.find(r => r.resource_id === sel)?.type_name || 'resources')} at your time:</div><div class="suggest">${x.alternatives.map(a => `<button class="btn sm" data-alt="${a.resource_id}">${esc(a.name)}</button>`).join('')}</div>` : ''}</div>`;
        document.querySelectorAll('[data-slot]').forEach(b => b.onclick = () => { const [a, c] = b.dataset.slot.split('|'); $('#b-st').value = a.slice(11); $('#b-en').value = c.slice(11); $('#b-msg').innerHTML = ''; refresh(); });
        document.querySelectorAll('[data-alt]').forEach(b => b.onclick = () => { sel = +b.dataset.alt; $('#b-msg').innerHTML = ''; refresh(); });
      } else $('#b-msg').innerHTML = `<div class="form-err" role="alert">${esc(e.message)}</div>`;
    }
  }
  $('#b-go').onclick = () => submit();
  refresh();
};

/* ============================ SCHEDULE ============================ */
PAGES.schedule = async () => {
  const preset = S.preset || {}; S.preset = null;
  const res = await api('/resources');
  const busyToday = (await api('/dashboard')).today[0];
  let rid = preset.resource_id || busyToday?.resource_id || res[0].resource_id, day = today();
  view(`${header('Schedule', 'See exactly when a resource is free or taken')}
    <div class="filters"><select id="s-res" aria-label="Resource">${res.map(r => `<option value="${r.resource_id}" ${r.resource_id === rid ? 'selected' : ''}>${esc(r.icon)} ${esc(r.name)}</option>`).join('')}</select>
    <input type="date" id="s-day" value="${day}" aria-label="Date"><button class="btn ghost" id="s-prev">‹ Previous day</button><button class="btn ghost" id="s-next">Next day ›</button></div><div id="s-body"></div>`);
  wireBell();
  async function load() {
    const s = await api(`/resources/${rid}/schedule?date=${day}`), O = s.open, C = s.close, span = (C - O) * 60;
    const pos = t => Math.max(0, Math.min(100, ((+t.slice(11, 13) * 60 + +t.slice(14, 16)) - O * 60) / span * 100));
    const clipS = t => t.slice(0, 10) < day ? 0 : pos(t), clipE = t => t.slice(0, 10) > day ? 100 : pos(t);
    const blocks = [...s.bookings.map(b => ({ cls: b.status, a: b.start_time, b: b.end_time, label: `${b.title} · ${b.user_name}` })),
      ...s.maintenance.map(m => ({ cls: 'maint', a: m.start_time, b: m.end_time, label: `Maintenance: ${m.issue}` }))];
    const now = new Date(), nowPct = day === today() ? ((now.getHours() * 60 + now.getMinutes()) - O * 60) / span * 100 : -1;
    $('#s-body').innerHTML = `<div class="card"><h3>${esc(s.resource.icon)} ${esc(s.resource.name)} · ${esc(prettyDay(day))} ${badge(s.resource.status)}</h3>
      <div class="tl"><div class="tl-scale">${Array.from({ length: C - O + 1 }, (_, i) => `<span style="left:${i / (C - O) * 100}%">${pad(O + i)}</span>`).join('')}</div>
      <div class="tl-track">${blocks.map(b => `<div class="tl-block ${b.cls}" style="left:${clipS(b.a)}%;width:${clipE(b.b) - clipS(b.a)}%" title="${esc(b.label)}">${esc(b.label)}</div>`).join('')}${nowPct >= 0 && nowPct <= 100 ? `<div class="tl-now" style="left:${nowPct}%" title="Now"></div>` : ''}</div>
      <div class="legend"><span><i style="background:var(--brand)"></i>Approved</span><span><i style="background:var(--amber)"></i>Pending</span><span><i style="background:#8a9bb0"></i>Completed</span><span><i style="background:var(--blue)"></i>Maintenance</span><span><i style="background:var(--coral)"></i>Now</span></div></div>
      <div style="margin-top:16px">${blocks.length ? `<div class="tbl-wrap"><table><tr><th>Time</th><th>What</th><th>Status</th></tr>${[...s.bookings.map(b => `<tr><td>${b.start_time.slice(11)}–${b.end_time.slice(11)}</td><td>${esc(b.title)} · ${esc(b.user_name)}</td><td>${badge(b.status)}</td></tr>`), ...s.maintenance.map(m => `<tr><td>${esc(m.start_time.slice(5))} → ${esc(m.end_time.slice(5))}</td><td>${esc(m.issue)}</td><td>${badge(m.status)}</td></tr>`)].join('')}</table></div>` : empty('Free all day', 'No bookings or maintenance on this date.')}</div>
      ${s.resource.status === 'available' ? `<div style="margin-top:14px"><button class="btn" id="s-book">Book this resource</button></div>` : ''}</div>`;
    const bb = $('#s-book'); if (bb) bb.onclick = () => { S.preset = { resource_id: rid }; go('book'); };
  }
  const shift = n => { const d = new Date(day + 'T00:00'); d.setDate(d.getDate() + n); day = ymd(d); $('#s-day').value = day; load(); };
  $('#s-res').onchange = e => { rid = +e.target.value; load(); }; $('#s-day').onchange = e => { day = e.target.value; load(); };
  $('#s-prev').onclick = () => shift(-1); $('#s-next').onclick = () => shift(1);
  load();
};

/* ============================ BOOKINGS ============================ */
PAGES.bookings = async () => {
  let status = '';
  view(`${header(isAdmin() ? 'All bookings' : 'My bookings', isAdmin() ? 'Approve, reject or cancel any reservation' : 'Track and manage your reservations', '<button class="btn" onclick="go(\'book\')">New booking</button>')}
    <div class="filters"><div class="chips" id="chips">${['', 'pending', 'approved', 'completed', 'cancelled', 'rejected'].map(s => `<button class="chip ${s === '' ? 'on' : ''}" data-s="${s}">${s || 'All'}</button>`).join('')}</div></div><div id="b-table"></div>`);
  wireBell();
  async function load() {
    const list = await api('/bookings?status=' + status);
    $('#b-table').innerHTML = list.length ? `<div class="tbl-wrap"><table><tr><th>#</th><th>Resource</th>${isAdmin() ? '<th>Booked by</th>' : ''}<th>Title</th><th>When</th><th>Status</th><th></th></tr>
      ${list.map(b => `<tr><td>${b.booking_id}</td><td>${esc(b.icon)} ${esc(b.resource_name)}</td>${isAdmin() ? `<td>${esc(b.user_name)}<br><small style="color:var(--muted)">${esc(b.role)}</small></td>` : ''}<td>${esc(b.title)}${b.remarks ? `<br><small style="color:var(--muted)">${esc(b.remarks)}</small>` : ''}</td><td>${esc(when(b.start_time, b.end_time))}</td><td>${badge(b.status)}</td>
      <td><div class="actions">${isAdmin() && b.status === 'pending' ? `<button class="btn sm green" data-a="approved" data-id="${b.booking_id}">Approve</button><button class="btn sm danger" data-a="rejected" data-id="${b.booking_id}">Reject</button>` : ''}
      ${['pending', 'approved'].includes(b.status) && (isAdmin() || b.user_id === S.me.user_id) ? `<button class="btn sm ghost" data-a="cancelled" data-id="${b.booking_id}">Cancel</button>` : ''}</div></td></tr>`).join('')}</table></div>` : empty('No bookings here', 'Bookings that match this filter will appear here.');
    document.querySelectorAll('[data-a]').forEach(b => b.onclick = async () => {
      if (b.dataset.a !== 'approved' && !confirm(`${b.dataset.a === 'rejected' ? 'Reject' : 'Cancel'} booking #${b.dataset.id}?`)) return;
      try { await api(`/bookings/${b.dataset.id}/status`, 'POST', { status: b.dataset.a }); toast(`Booking ${b.dataset.a}.`); load(); } catch (e) { toast(e.message, 'err'); }
    });
  }
  $('#chips').onclick = e => { const c = e.target.closest('.chip'); if (!c) return; status = c.dataset.s; document.querySelectorAll('.chip').forEach(x => x.classList.toggle('on', x === c)); load(); };
  load();
};

/* ============================ MAINTENANCE ============================ */
PAGES.maintenance = async () => {
  view(`${header('Maintenance', 'Planned repairs and servicing', isAdmin() ? '<button class="btn" id="m-add">Schedule maintenance</button>' : '')}<div id="m-body"></div>`);
  wireBell();
  async function load() {
    const list = await api('/maintenance');
    $('#m-body').innerHTML = list.length ? `<div class="tbl-wrap"><table><tr><th>Resource</th><th>Issue</th><th>Technician</th><th>From</th><th>To</th><th>Status</th>${isAdmin() ? '<th></th>' : ''}</tr>
      ${list.map(m => `<tr><td>${esc(m.icon)} ${esc(m.resource_name)}</td><td>${esc(m.issue)}</td><td>${esc(m.technician || '—')}</td><td>${esc(m.start_time)}</td><td>${esc(m.end_time)}</td><td>${badge(m.status)}</td>
      ${isAdmin() ? `<td><div class="actions">${m.status === 'scheduled' ? `<button class="btn sm ghost" data-m="in_progress" data-id="${m.maint_id}">Start</button>` : ''}${['scheduled', 'in_progress'].includes(m.status) ? `<button class="btn sm green" data-m="completed" data-id="${m.maint_id}">Complete</button><button class="btn sm ghost" data-m="cancelled" data-id="${m.maint_id}">Cancel</button>` : ''}</div></td>` : ''}</tr>`).join('')}</table></div>` : empty('No maintenance scheduled', 'Planned servicing will appear here.');
    document.querySelectorAll('[data-m]').forEach(b => b.onclick = async () => { try { await api(`/maintenance/${b.dataset.id}/status`, 'POST', { status: b.dataset.m }); toast('Maintenance updated.'); load(); } catch (e) { toast(e.message, 'err'); } });
  }
  if (isAdmin()) $('#m-add').onclick = async () => {
    const res = await api('/resources'), d = today();
    modal(`<h2>Schedule maintenance</h2><div id="m-err"></div>
      <div class="field"><label>Resource</label><select id="m-res">${res.filter(r => r.status !== 'retired').map(r => `<option value="${r.resource_id}">${esc(r.icon)} ${esc(r.name)}</option>`).join('')}</select></div>
      <div class="field"><label>Issue</label><input id="m-issue" placeholder="e.g. Projector lamp replacement"></div>
      <div class="field"><label>Technician (optional)</label><input id="m-tech"></div>
      <div class="row2"><div class="field"><label>Start</label><input type="datetime-local" id="m-s" value="${d}T09:00"></div><div class="field"><label>End</label><input type="datetime-local" id="m-e" value="${d}T17:00"></div></div>
      <p style="color:var(--muted);font-size:.85rem">Bookings that overlap this window are cancelled automatically by a database trigger, and the affected users are notified.</p>
      <div class="btns"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn" id="m-save">Schedule</button></div>`);
    $('#m-save').onclick = async () => {
      try {
        const r = await api('/maintenance', 'POST', { resource_id: $('#m-res').value, issue: $('#m-issue').value, technician: $('#m-tech').value, start: $('#m-s').value, end: $('#m-e').value });
        closeModal(); toast(`Maintenance scheduled. ${r.cancelled_bookings} clashing booking(s) cancelled.`); load();
      } catch (e) { $('#m-err').innerHTML = `<div class="form-err">${esc(e.message)}</div>`; }
    };
  };
  load();
};

/* ============================ REPORTS ============================ */
PAGES.reports = async () => {
  const r = await api('/reports'), mx = Math.max(1, ...r.utilization.map(u => u.total_hours)), pk = Math.max(1, ...r.peak_hours.map(p => p.bookings));
  const dmx = Math.max(1, ...r.by_dept.map(d => d.bookings));
  view(`${header('Reports', 'Utilisation and demand across the campus')}
    <div class="grid g4" style="margin-bottom:16px">${r.by_type.map(t => `<div class="card stat"><div class="ic t">${esc(t.icon)}</div><div><b>${t.hours}h</b><span>${esc(t.type_name)} · ${t.bookings} bookings</span></div></div>`).join('')}
      <div class="card stat"><div class="ic c">🛡️</div><div><b>${r.conflicts_blocked}</b><span>Conflicts blocked</span></div></div></div>
    <div class="grid g2e"><div class="card"><h3>Resource utilisation (hours booked)</h3><div class="bars">${r.utilization.slice(0, 12).map(u => `<div class="bar-row"><span class="nm">${esc(u.icon)} ${esc(u.name)}</span><div class="bar"><i style="width:${u.total_hours / mx * 100}%"></i></div><b>${u.total_hours}h</b></div>`).join('')}</div></div>
      <div class="card"><h3>Peak booking hours</h3><div class="vbars">${r.peak_hours.map(p => `<div><b>${p.bookings}</b><i style="height:${p.bookings / pk * 100}%"></i>${pad(p.hour)}</div>`).join('')}</div></div>
      <div class="card"><h3>Bookings by department</h3><div class="bars">${r.by_dept.map(d => `<div class="bar-row"><span class="nm">${esc(d.dept)}</span><div class="bar"><i style="width:${d.bookings / dmx * 100}%"></i></div><b>${d.bookings}</b></div>`).join('')}</div></div>
      <div class="card"><h3>Most active users</h3>${r.top_users.map(u => `<div class="notif"><b>${esc(u.full_name)}</b> <span class="tag">${esc(u.role)}</span><small>${u.bookings} completed or approved bookings</small></div>`).join('') || empty('No data yet')}
        ${r.idle.length ? `<h3 style="margin-top:14px">Never used</h3><div class="tags">${r.idle.map(i => `<span class="tag">${esc(i.name)}</span>`).join('')}</div>` : ''}</div></div>`);
  wireBell();
};

/* ============================ AUDIT & USERS ============================ */
PAGES.audit = async () => {
  const list = await api('/audit');
  view(`${header('Audit log', 'Every change recorded automatically by database triggers')}<div class="tbl-wrap"><table><tr><th>#</th><th>Time</th><th>Table</th><th>Action</th><th>Details</th></tr>
    ${list.map(l => `<tr><td>${l.log_id}</td><td>${esc(l.logged_at)}</td><td>${esc(l.table_name)}</td><td>${l.action === 'CONFLICT_BLOCKED' ? '<span class="badge busy">conflict blocked</span>' : `<span class="tag">${esc(l.action)}</span>`}</td><td>${esc(l.details)}</td></tr>`).join('')}</table></div>`);
  wireBell();
};
PAGES.users = async () => {
  const list = await api('/users');
  view(`${header('Users', 'Registered campus members')}<div class="tbl-wrap"><table><tr><th>Name</th><th>Email</th><th>Role</th><th>Department</th><th>Bookings</th><th>Joined</th><th></th></tr>
    ${list.map(u => `<tr><td><b>${esc(u.full_name)}</b></td><td>${esc(u.email)}</td><td><span class="tag">${esc(u.role)}</span></td><td>${esc(u.dept_name || '—')}</td><td>${u.bookings}</td><td>${esc(u.created_at.slice(0, 10))}</td>
    <td>${u.user_id === S.me.user_id ? '' : `<button class="btn sm ${u.is_active ? 'ghost' : 'green'}" data-u="${u.user_id}" data-on="${u.is_active ? 0 : 1}">${u.is_active ? 'Deactivate' : 'Activate'}</button>`}</td></tr>`).join('')}</table></div>`);
  wireBell();
  document.querySelectorAll('[data-u]').forEach(b => b.onclick = async () => { try { await api(`/users/${b.dataset.u}/active`, 'POST', { active: b.dataset.on === '1' }); toast('User updated.'); PAGES.users(); } catch (e) { toast(e.message, 'err'); } });
};

/* ============================ BOOT ============================ */
async function boot(fresh) {
  if (!S.types.length) { const m = await api('/meta'); S.types = m.types; S.depts = m.departments; }
  if (!S.me) { try { S.me = await api('/me'); } catch { return showAuth('login'); } }
  $('#auth').classList.add('hidden'); $('#app').classList.remove('hidden');
  buildNav();
  if (fresh && location.hash !== '#dashboard') location.hash = 'dashboard'; else route();
}
window.addEventListener('hashchange', route);
api('/meta').then(m => { S.types = m.types; S.depts = m.departments; boot(false); });
