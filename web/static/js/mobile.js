// iPhone page for the trading bot (/m). Read-only: polls /api/mobile and renders five tabs.
// Tab behaviour mirrors the Earlswood Road home dashboard (bottom tab bar, last tab remembered, #tab links).
// The charts are phone versions of the desktop dashboard's graphics: equity trajectory, trade journey,
// risk gauge, health rings, allocation donut, R-multiple histogram, sparklines, score dials and heatmap.
'use strict';

const REFRESH_MS = 15000;
const STALE_AFTER_SEC = 120; // the bot refreshes its status every poll (~15 s)
const TABS = ['home', 'positions', 'trades', 'results', 'screener'];
const FIRST_PAGE = 20; // screener rows shown before "Show all"
const state = { tab: 'home', snap: null, error: null, eqView: '1D', scrView: 'list', showAll: false, scrubbing: false };
let ACCT = '£';

// ------------------------------------------------------------ helpers
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v));
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const tone = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
const signed = (n, body) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${body}`;
const money = (v, withSign = true) => {
  const n = num(v) || 0;
  const body = `${ACCT}${Math.abs(n).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return withSign ? signed(n, body) : `${n < 0 ? '−' : ''}${body}`;
};
const pct = (v, d = 1) => { const n = num(v) || 0; return signed(n, `${Math.abs(n).toFixed(d)}%`); };
const rMult = (v) => { const n = num(v) || 0; return signed(n, `${Math.abs(n).toFixed(2)}R`); };
// Prices are in the instrument's currency; money amounts in the account currency.
const priceCcy = (sym) => (String(sym).endsWith('_UK_EQ') ? '£' : '$');
const price = (sym, v) => `${priceCcy(sym)}${(num(v) || 0).toFixed(2)}`;
const cleanSym = (sym) => String(sym || '').replace('_US_EQ', '').replace('_UK_EQ', '.L');
const trades = (n) => `${n} trade${Number(n) === 1 ? '' : 's'}`;
const tradeReason = (r) => String(r || '').split(' (')[0].split(':')[0].replace(/\s+hit at .*$/i, '');
// Safari only parses ISO dates ("2026-10-30T22:12:00"), not the log's "2026-10-30 22:12:00"
const parseTs = (v) => { if (!v) return null; const d = new Date(String(v).replace(' ', 'T')); return Number.isNaN(d.getTime()) ? null : d; };
const fmtShort = (v) => { const d = parseTs(v); return d ? d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''; };
const fmtDay = (v) => { const d = parseTs(v); return d ? d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : ''; };

function ago(iso) {
  if (!iso) return '';
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}
function duration(minutes) {
  const m = Math.max(0, Math.round(minutes));
  if (m < 60) return `${m}m`;
  if (m < 1440) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return `${Math.floor(m / 1440)}d ${Math.floor((m % 1440) / 60)}h`;
}
function ring(pctVal, color) {
  return `<svg class="ring" viewBox="0 0 44 44" aria-hidden="true"><circle class="track" cx="22" cy="22" r="18"/>
    <circle class="prog" cx="22" cy="22" r="18" pathLength="100" stroke="${color}" stroke-dasharray="${Math.max(0, Math.min(100, pctVal || 0))} 100"/></svg>`;
}
const okMsg = (text, sub = '') => `<div class="ok-msg"><i>✓</i><div>${esc(text)}${sub ? `<div class="sub">${esc(sub)}</div>` : ''}</div></div>`;
const alertRow = (level, title, detail) =>
  `<div class="alert ${level}"><span class="ic">!</span><div class="tx"><div class="tt">${esc(title)}</div><div class="dt">${esc(detail)}</div></div></div>`;

function botHealth(s) {
  const updated = s.activity && s.activity.updated_at;
  const age = updated ? (Date.now() - new Date(updated).getTime()) / 1000 : Infinity;
  if (state.error) return { level: 'critical', label: 'Offline', detail: state.error };
  if (age > STALE_AFTER_SEC) return { level: 'critical', label: 'Stopped', detail: `No update since ${ago(updated)}` };
  if (s.portfolio && s.portfolio.circuit_breaker_tripped) return { level: 'serious', label: 'Paused', detail: 'Circuit breaker tripped' };
  return { level: 'good', label: 'Running', detail: `Updated ${ago(updated)}` };
}

// ------------------------------------------------------------ small graphics (logos, sparklines, dials)
function sectorGradient(sector) {
  const sec = sector || '';
  if (/Crypto|Bitcoin/.test(sec)) return 'linear-gradient(135deg, #ff9500, #ffb340)';
  if (/Clean|Nuclear|Solar/.test(sec)) return 'linear-gradient(135deg, #34c759, #66d982)';
  if (/Fintech|Banking|Lending/.test(sec)) return 'linear-gradient(135deg, #af52de, #c77ded)';
  if (/Cyber|Cloud/.test(sec)) return 'linear-gradient(135deg, #5856d6, #7a79e0)';
  if (/EV|Auto/.test(sec)) return 'linear-gradient(135deg, #ff2d55, #ff6482)';
  return 'linear-gradient(135deg, #0071e3, #42a5f5)';
}
const stockMeta = (sym) => (typeof STOCK_META !== 'undefined' && STOCK_META[sym]) || null;
// Company favicon over a coloured monogram: if the favicon can't load, the monogram shows.
function logo(sym, size = 34) {
  const meta = stockMeta(sym);
  const mono = `<div class="mono" style="background:${sectorGradient(meta && meta[1])}">${esc(cleanSym(sym).slice(0, 2))}</div>`;
  const img = meta && meta[2]
    ? `<img src="https://www.google.com/s2/favicons?domain=${esc(meta[2])}&sz=128" alt="" loading="lazy" onerror="this.remove()">` : '';
  return `<span class="logo" style="width:${size}px;height:${size}px;border-radius:${Math.round(size * 0.27)}px">${mono}${img}</span>`;
}
function spark(points, roc, w = 58, h = 22) {
  if (!points || points.length < 2) return `<svg width="${w}" height="${h}"></svg>`;
  const lo = Math.min(...points), hi = Math.max(...points), range = hi - lo || lo * 0.01 || 1;
  const padX = 2, padY = 3;
  const xy = points.map((v, i) => [padX + (i / (points.length - 1)) * (w - padX * 2), h - padY - ((v - lo) / range) * (h - padY * 2)]);
  const col = (roc ?? (points[points.length - 1] - points[0])) >= 0 ? css('--good') : css('--critical');
  const line = xy.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const [lx, ly] = xy[xy.length - 1];
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polygon points="${line} ${lx.toFixed(1)},${h} ${xy[0][0].toFixed(1)},${h}" fill="${col}" opacity="0.14"/>
    <polyline points="${line}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="2.2" fill="${col}"/></svg>`;
}
function dial(score) {
  const sc = Math.max(0, Math.min(100, num(score) || 0));
  const col = sc >= 80 ? css('--good') : sc >= 65 ? css('--s1') : sc >= 50 ? css('--warning') : css('--critical');
  return `<span class="dial" title="Score ${sc.toFixed(1)}"><svg viewBox="0 0 38 38"><circle class="tr" cx="19" cy="19" r="15"/>
    <circle class="fl" cx="19" cy="19" r="15" pathLength="100" stroke="${col}" stroke-dasharray="${sc} 100"/></svg><b>${Math.round(sc)}</b></span>`;
}
// Trade path for a closed trade (the "journey replay" thumbnail)
function miniJourney(t) {
  const entry = num(t.entry_price) || 0, exit = num(t.exit_price) || entry;
  const pts = (t.path && t.path.length >= 2 ? t.path : [entry, exit]).map(Number);
  const w = 80, h = 28, padX = 3, padY = 4;
  const all = pts.concat([entry, exit]);
  let lo = Math.min(...all), hi = Math.max(...all);
  const span = Math.max(hi - lo, entry * 0.003, 0.02);
  lo -= span * 0.2; hi += span * 0.2;
  const y = (v) => h - padY - ((v - lo) / (hi - lo)) * (h - padY * 2);
  const xy = pts.map((v, i) => [padX + (i / (pts.length - 1)) * (w - padX * 2), y(v)]);
  const win = (num(t.net_pnl) || 0) >= 0;
  const col = win ? css('--good') : css('--critical');
  const line = xy.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const first = xy[0], last = xy[xy.length - 1];
  return `<svg class="mini" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
    <line x1="${padX}" x2="${w - padX}" y1="${y(entry).toFixed(1)}" y2="${y(entry).toFixed(1)}" stroke="${css('--axis')}" stroke-dasharray="2,2"/>
    <polygon points="${line} ${last[0].toFixed(1)},${h - padY} ${first[0].toFixed(1)},${h - padY}" fill="${col}" opacity="0.15"/>
    <polyline points="${line}" fill="none" stroke="${col}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${first[0].toFixed(1)}" cy="${first[1].toFixed(1)}" r="2.2" fill="${css('--s1')}"/>
    <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.4" fill="${col}" stroke="${css('--card')}" stroke-width="1"/></svg>`;
}

// ------------------------------------------------------------ area charts with touch scrubbing
// One drawing routine for the equity trajectory, trade journey, all-time equity and cumulative P&L charts.
//  o.pts   [{v, x?: 0..1, label}]   o.lines [{v, label, color, side, include}]   o.ticks [{x, label}]
function areaChart(o) {
  const W = o.W || 330, H = o.H || 170;
  const padL = o.padL ?? 6, padR = o.padR ?? 54, padT = o.padT ?? 14, padB = o.padB ?? 22;
  const pw = W - padL - padR, ph = H - padT - padB;
  const pts = o.pts, n = pts.length;
  const lines = (o.lines || []).filter((l) => l.v != null);
  const rangeVals = pts.map((p) => p.v).concat(lines.filter((l) => l.include).map((l) => l.v), o.zero ? [0] : []);
  let lo = Math.min(...rangeVals), hi = Math.max(...rangeVals);
  const pad = Math.max((hi - lo) * (o.margin ?? 0.14), o.minPad ?? 0);
  lo -= pad; hi += pad;
  if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  const X = (p, i) => padL + (p.x != null ? p.x : n > 1 ? i / (n - 1) : 0) * pw;
  const Y = (v) => padT + (1 - (v - lo) / (hi - lo)) * ph;
  const coords = pts.map((p, i) => ({ x: X(p, i), y: Y(p.v), v: p.v, label: p.label, i }));
  const line = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  const first = coords[0], last = coords[n - 1];
  const baseY = o.zero ? Y(0) : padT + ph;
  const up = o.up != null ? o.up : last.v >= (o.upRef ?? pts[0].v);
  const col = up ? css('--good') : css('--critical');
  const gid = `g-${o.id}`;
  const out = [];
  out.push(`<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${col}" stop-opacity="0.3"/><stop offset="100%" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>`);
  (o.ticks || []).forEach((t, k, arr) => {
    const tx = padL + t.x * pw;
    out.push(`<line x1="${tx.toFixed(1)}" x2="${tx.toFixed(1)}" y1="${padT}" y2="${padT + ph}" stroke="${css('--grid')}" stroke-dasharray="3,3"/>`);
    out.push(`<text x="${tx.toFixed(1)}" y="${H - 6}" text-anchor="${k === 0 ? 'start' : k === arr.length - 1 ? 'end' : 'middle'}">${esc(t.label)}</text>`);
  });
  if (o.xLabels) {
    out.push(`<text x="${padL}" y="${H - 6}">${esc(o.xLabels[0])}</text><text x="${padL + pw}" y="${H - 6}" text-anchor="end">${esc(o.xLabels[1])}</text>`);
  }
  if (o.zero) out.push(`<line x1="${padL}" x2="${padL + pw}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" stroke="${css('--axis')}" stroke-dasharray="3,3"/>`);
  lines.forEach((l) => {
    const ly = Y(l.v);
    if (ly < padT - 2 || ly > padT + ph + 2) return;
    const left = (l.side || 'left') === 'left';
    out.push(`<line x1="${padL}" x2="${padL + pw}" y1="${ly.toFixed(1)}" y2="${ly.toFixed(1)}" stroke="${l.color}" stroke-dasharray="4,4" stroke-width="1.1" opacity="0.8"/>`);
    out.push(`<text class="halo" x="${left ? padL + (o.anchor ? 12 : 4) : padL + pw - 2}" y="${(ly - 4 < padT + 8 ? ly + 11 : ly - 4).toFixed(1)}" text-anchor="${left ? 'start' : 'end'}" style="fill:${l.color};font-weight:600">${esc(l.label)}</text>`);
  });
  out.push(`<polygon points="${line} ${last.x.toFixed(1)},${baseY.toFixed(1)} ${first.x.toFixed(1)},${baseY.toFixed(1)}" fill="url(#${gid})"/>`);
  if (o.projectTo != null) {
    const px = padL + o.projectTo * pw;
    out.push(`<line x1="${last.x.toFixed(1)}" x2="${px.toFixed(1)}" y1="${last.y.toFixed(1)}" y2="${last.y.toFixed(1)}" stroke="${col}" stroke-dasharray="3,3" opacity="0.5"/>`);
    out.push(`<line x1="${last.x.toFixed(1)}" x2="${last.x.toFixed(1)}" y1="${padT}" y2="${padT + ph}" stroke="${col}" stroke-dasharray="2,2" opacity="0.4"/>`);
    out.push(`<text x="${Math.max(padL + 20, last.x - 4).toFixed(1)}" y="${padT + 10}" text-anchor="end" style="fill:${col};font-weight:700">NOW</text>`);
  }
  out.push(`<polyline points="${line}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`);
  if (o.anchor) out.push(`<circle cx="${first.x.toFixed(1)}" cy="${first.y.toFixed(1)}" r="3.6" fill="${css('--s1')}" stroke="${css('--card')}" stroke-width="1.5"/>`);
  if (o.peakAbove != null && n >= 3) {
    let k = 0;
    coords.forEach((c, i) => { if (c.v > coords[k].v) k = i; });
    if (k > 0 && k < n - 1 && coords[k].v > o.peakAbove) {
      const c = coords[k];
      out.push(`<circle cx="${c.x.toFixed(1)}" cy="${c.y.toFixed(1)}" r="3" fill="${css('--good')}" stroke="${css('--card')}" stroke-width="1.2"/>`);
      out.push(`<text class="halo" x="${c.x.toFixed(1)}" y="${Math.max(padT + 8, c.y - 6).toFixed(1)}" text-anchor="middle" style="fill:${css('--good')};font-weight:600">▲ ${esc(o.fmt(c.v))}</text>`);
    }
  }
  out.push(`<circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="8" fill="none" stroke="${col}" opacity="0.4"/><circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="4" fill="${col}" stroke="${css('--card')}" stroke-width="2"/>`);
  out.push(`<text class="halo strong" x="${(last.x - 9).toFixed(1)}" y="${(last.y - 8).toFixed(1)}" text-anchor="end">${esc(o.fmt(last.v))}</text>`);
  out.push(`<text x="${W - 2}" y="${padT + 8}" text-anchor="end">${esc(o.fmt(hi))}</text><text x="${W - 2}" y="${padT + ph}" text-anchor="end">${esc(o.fmt(lo))}</text>`);
  out.push(`<line class="xh-line" x1="0" x2="0" y1="${padT}" y2="${padT + ph}" stroke="${css('--text')}" stroke-width="1" opacity="0"/><circle class="xh-dot" cx="0" cy="0" r="4.5" fill="${css('--s1')}" stroke="${css('--card')}" stroke-width="2" opacity="0"/>`);
  return { svg: `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.label || 'Chart')}">${out.join('')}</svg>`, coords };
}

// Drag a finger across a chart to read values (phones have no hover)
function attachScrub(plotEl, coords, onPick) {
  const svg = plotEl && plotEl.querySelector('svg');
  if (!svg) return;
  const hair = svg.querySelector('.xh-line'), dot = svg.querySelector('.xh-dot');
  const vb = svg.viewBox.baseVal;
  const pick = (ev) => {
    const r = svg.getBoundingClientRect();
    const x = ((ev.clientX - r.left) / r.width) * vb.width;
    let best = 0, bd = Infinity;
    coords.forEach((c, i) => { const d = Math.abs(c.x - x); if (d < bd) { bd = d; best = i; } });
    const c = coords[best];
    hair.setAttribute('x1', c.x); hair.setAttribute('x2', c.x); hair.setAttribute('opacity', '0.55');
    dot.setAttribute('cx', c.x); dot.setAttribute('cy', c.y); dot.setAttribute('opacity', '1');
    onPick(c, best);
  };
  svg.addEventListener('pointerdown', (ev) => { state.scrubbing = true; pick(ev); });
  svg.addEventListener('pointermove', (ev) => { if (state.scrubbing) pick(ev); });
  const end = () => { state.scrubbing = false; };
  svg.addEventListener('pointerup', end);
  svg.addEventListener('pointercancel', end);
  svg.addEventListener('pointerleave', end);
}

// ------------------------------------------------------------ home
function renderHome(s) {
  const p = s.portfolio || {};
  const si = s.session_info || {};
  const lt = s.long_term || {};
  const j = lt.journal || {};
  const st = (lt.equity || {}).stats || {};
  const positions = s.positions || [];
  const openPnl = positions.reduce((a, x) => a + (num(x.unrealized_pnl) || 0), 0);
  const health = botHealth(s);

  $('#today-date').textContent = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
  const pill = $('#status');
  pill.className = `pill ${health.level}`;
  pill.querySelector('span').textContent = `${health.label} · ${String(s.execution_mode || '').toUpperCase()}`;

  const slotsUsed = num(p.open_positions_count) || 0;
  const slotsMax = num(p.max_open_positions) || 1;
  const dd = num(st.current_drawdown_pct);
  const us = s.market_session || {}, uk = s.uk_market_session || {};
  const anyOpen = us.is_open || uk.is_open;
  const dayPnl = num(si.day_pnl) || 0;
  const marketLine = (m) => (m.is_open ? 'Open' : m.next_open_str ? `Opens ${m.next_open_str}` : m.state || '');

  $('#home-tiles').innerHTML = [
    `<div class="tile" data-go="results"><div class="t-label">Equity</div>
      <div class="big">${esc(money(p.total_equity, false))}</div>
      <div class="sub ${tone(dayPnl)}">${esc(money(dayPnl))} today</div>
      <div class="t-foot">Cash ${esc(money(p.free_cash, false))}</div></div>`,
    `<div class="tile" data-go="positions">${ring((slotsUsed / slotsMax) * 100, css('--s1'))}<div class="t-label">Positions</div>
      <div class="big">${slotsUsed}<small>of ${slotsMax}</small></div>
      <div class="sub ${tone(openPnl)}">${positions.length ? `${esc(money(openPnl))} open` : 'All cash'}</div>
      <div class="t-foot">${esc(positions.map((x) => cleanSym(x.symbol)).join(', ') || 'Waiting for a setup')}</div></div>`,
    `<div class="tile" data-go="results"><div class="t-label">All time</div>
      <div class="big ${tone(j.net_pnl)}">${j.trades ? esc(money(j.net_pnl)) : '–'}</div>
      <div class="sub">${j.trades ? `${trades(j.trades)} · ${esc(rMult(j.avg_r))} avg` : 'No trades yet'}</div>
      <div class="t-foot">${j.profit_factor != null ? `Profit factor ${Number(j.profit_factor).toFixed(2)}` : ''}</div></div>`,
    `<div class="tile" data-go="results">${dd != null ? ring(Math.min(100, (dd / 20) * 100), dd >= 5 ? css('--critical') : css('--s3')) : ''}<div class="t-label">From peak</div>
      <div class="big">${dd == null ? '–' : dd < 0.05 ? 'At high' : `−${dd.toFixed(1)}%`}</div>
      <div class="sub">${st.peak_equity ? `Peak ${esc(money(st.peak_equity, false))}` : ''}</div>
      <div class="t-foot">${st.max_drawdown_pct != null ? `Worst −${Number(st.max_drawdown_pct).toFixed(1)}%` : ''}</div></div>`,
    `<div class="tile wide" data-go="screener"><div class="t-label"><span class="dot ${anyOpen ? 'good' : ''}"></span>Markets</div>
      <ul class="list keep-label"><li><span class="l">🇺🇸 US</span><span class="v">${esc(marketLine(us))}</span></li>
      <li><span class="l">🇬🇧 UK</span><span class="v">${esc(marketLine(uk))}</span></li></ul></div>`,
  ].join('');

  const alerts = [];
  if (health.level === 'critical') alerts.push(alertRow('critical', health.label === 'Offline' ? "Can't reach the bot" : 'The bot has stopped updating', health.detail));
  if (p.circuit_breaker_tripped) alerts.push(alertRow('serious', 'Circuit breaker tripped', 'New trades are paused for 24 hours after a 5% drop.'));
  if (dd != null && dd >= 10) alerts.push(alertRow('warning', `Equity ${dd.toFixed(1)}% below its peak`, 'Worth reviewing the Results tab.'));
  (s.cooldowns || []).forEach((c) => alerts.push(alertRow('warning', `${cleanSym(c.symbol)} on cooldown`, 'Paused after a losing trade.')));
  $('#home-attn').innerHTML = alerts.length ? `<h2>Attention</h2>${alerts.join('')}`
    : okMsg('All good', `${health.detail} · ${(s.activity || {}).detail || ''}`);
}

// Equity trajectory: session (09:30–16:00 ET) or rolling 24h, with the session-open baseline
function renderEquityToday(s) {
  const el = $('#home-equity');
  if (state.scrubbing && el.dataset.drawn) return; // don't redraw under a finger
  const et = s.equity_today || {}, si = s.session_info || {}, p = s.portfolio || {};
  const is1D = state.eqView === '1D';
  const cur = num(p.total_equity) || 0;
  const total = num(si.total_session_minutes) || 390;
  const fmt = (v) => `${ACCT}${Number(v).toFixed(2)}`;
  let pts, start, ticks, projectTo = null;
  if (is1D) {
    pts = (et.session || []).map((q, i, a) => ({
      v: Number(q.e), label: q.t || '',
      x: q.m != null ? Math.min(1, Math.max(0, q.m / total)) : i / Math.max(1, a.length - 1),
    }));
    start = num(si.start_equity) ?? (pts[0] ? pts[0].v : cur);
    if (pts.length < 2) pts = [{ v: start, x: 0, label: 'Open' }, { v: cur, x: 1, label: 'Now' }];
    const closeLabel = total <= 210 ? '13:00' : '16:00';
    ticks = [[0, '09:30'], [90, '11:00'], [180, '12:30'], [270, '14:00'], [360, '15:30'], [total, closeLabel]]
      .filter((t, k, a) => t[0] <= total && (k === a.length - 1 || t[0] < total - 40)).map((t) => ({ x: t[0] / total, label: t[1] }));
    if (pts[pts.length - 1].x < 0.97) projectTo = 1;
  } else {
    pts = (et.h24 || []).map((q) => ({ v: Number(q.e), label: fmtShort(q.ts) }));
    start = pts.length ? pts[0].v : cur;
    if (pts.length < 2) pts = [{ v: start, label: '24h ago' }, { v: cur, label: 'Now' }];
    ticks = [[0, '−24h'], [0.25, '−18h'], [0.5, '−12h'], [0.75, '−6h'], [1, 'Now']].map((t) => ({ x: t[0], label: t[1] }));
  }
  const dayPnl = cur - start;
  const dayPct = start > 0 ? (dayPnl / start) * 100 : 0;
  const chart = areaChart({
    id: 'eq', pts, ticks, projectTo, fmt, minPad: 0.45, up: cur >= start, label: 'Equity trajectory',
    lines: [{ v: start, label: `${is1D ? 'Open' : '24h ago'} ${fmt(start)}`, color: css('--muted'), side: 'left', include: true }],
  });
  const dflt = is1D && num(si.day_high) != null
    ? `High <b>${esc(fmt(si.day_high))}</b> · Low <b>${esc(fmt(si.day_low))}</b> · Open <b>${esc(fmt(start))}</b>`
    : 'Drag across the chart to read values';
  el.dataset.drawn = '1';
  el.innerHTML = `
    <div class="row"><h2>Equity</h2><span class="badge-pill ${dayPnl >= 0 ? 'good' : 'bad'}">${esc(money(dayPnl))} (${esc(pct(dayPct, 2))}) ${is1D ? 'session' : '24h'}</span></div>
    <div class="seg"><button data-eq="1D" class="${is1D ? 'on' : ''}">1D session</button><button data-eq="24H" class="${is1D ? '' : 'on'}">24H</button></div>
    <div class="scrub" id="eq-scrub">${dflt}</div>
    <div class="plot" id="eq-plot">${chart.svg}</div>`;
  attachScrub($('#eq-plot'), chart.coords, (c) => {
    const d = c.v - start;
    $('#eq-scrub').innerHTML = `${esc(c.label)} · <b>${esc(fmt(c.v))}</b> · <span class="${tone(d)}">${esc(signed(d, `${ACCT}${Math.abs(d).toFixed(2)}`))}</span> vs ${is1D ? 'open' : '24h ago'}`;
  });
}

// ------------------------------------------------------------ positions
function gauge(p) {
  const stop = num(p.stop_loss), tp = num(p.take_profit), entry = num(p.entry_price), cur = num(p.current_price);
  if ([stop, tp, entry, cur].some((v) => v === null) || tp <= stop) return '';
  const lo = Math.min(stop, cur, entry), hi = Math.max(tp, cur);
  const span = hi - lo || 1;
  const at = (v) => Math.max(1, Math.min(99, ((v - lo + span * 0.02) / (span * 1.04)) * 100));
  const locked = stop >= entry ? ((stop / entry - 1) * 100) : null;
  const toTarget = cur < tp ? ((tp / cur - 1) * 100) : null;
  const status = stop >= entry
    ? `<div class="gstatus good">Risk eliminated · stop trailed above entry${p.trailing_active ? ' · trailing engaged' : ''}</div>`
    : `<div class="gstatus warn">At risk: ${esc(pct((stop / cur - 1) * 100, 1))} to stop</div>`;
  const ccy = priceCcy(p.symbol);
  return `<div class="gauge">
      <div class="gtrack"></div>
      <div class="gmark" style="left:${at(stop)}%"></div><div class="gmark" style="left:${at(entry)}%;opacity:.5"></div><div class="gmark" style="left:${at(tp)}%"></div>
      <div class="gnow" style="left:${at(cur)}%"></div>
      <div class="gbubble" style="left:${Math.max(16, Math.min(84, at(cur)))}%">${esc(ccy)}${cur.toFixed(2)}</div>
      <div class="gcap l"><b>Stop ${esc(ccy)}${stop.toFixed(2)}</b>${locked != null ? `🔒 ${esc(pct(locked, 1))} locked` : 'initial stop'}</div>
      <div class="gcap r"><b>Target ${esc(ccy)}${tp.toFixed(2)}</b>${toTarget != null ? `${esc(pct(toTarget, 1))} to go` : 'target passed'}</div>
    </div>${status}`;
}

function renderPositions(s) {
  const list = s.positions || [];
  const openPnl = list.reduce((a, x) => a + (num(x.unrealized_pnl) || 0), 0);
  const pill = $('#pos-pill');
  pill.className = `pill ${list.length ? (openPnl >= 0 ? 'good' : 'critical') : ''}`;
  pill.querySelector('span').textContent = list.length ? `${list.length} open · ${money(openPnl)}` : 'All cash';

  if (state.scrubbing && $('#pos-list').dataset.drawn) return;
  if (!list.length) {
    const us = s.market_session || {};
    $('#pos-list').innerHTML = `<section class="card">${okMsg('No open positions', us.is_open ? 'The bot is watching for a setup.' : `Markets closed.${us.next_open_str ? ` US opens ${us.next_open_str}.` : ''}`)}</section>`;
    $('#pos-list').dataset.drawn = '1';
    return;
  }
  const journeys = [];
  $('#pos-list').innerHTML = list.map((p, idx) => {
    const pnl = num(p.unrealized_pnl) || 0;
    const entry = num(p.entry_price) || 0, cur = num(p.current_price) ?? entry;
    const stop = num(p.stop_loss);
    const heldMin = p.opened_at ? (Date.now() - new Date(p.opened_at).getTime()) / 60000 : null;
    const ccy = priceCcy(p.symbol);
    const f = (v) => `${ccy}${Number(v).toFixed(2)}`;
    let hist = (p.price_history || []).filter((q) => q && q.price != null).map((q) => ({ v: Number(q.price), label: fmtShort(q.ts) }));
    if (hist.length < 2) hist = [{ v: entry, label: fmtShort(p.opened_at) || 'Entry' }, { v: cur, label: 'Now' }];
    const allV = hist.map((q) => q.v).concat(entry);
    const rawSpan = Math.max(Math.max(...allV) - Math.min(...allV), entry * 0.004, 0.04);
    const stopNear = stop != null && Math.abs(entry - stop) <= rawSpan * 1.8;
    const chart = areaChart({
      id: `pj${idx}`, pts: hist, fmt: f, anchor: true, peakAbove: entry, up: cur >= entry, minPad: Math.max(entry * 0.0025, 0.02),
      margin: 0.22, H: 150, label: `${cleanSym(p.symbol)} trade journey`,
      lines: [
        { v: entry, label: `Entry ${f(entry)}`, color: css('--muted'), side: 'left', include: true },
        stop != null ? { v: stop, label: `${stop >= entry ? 'Trail stop' : 'Stop'} ${f(stop)}`, color: stop >= entry ? css('--good') : css('--critical'), side: 'right', include: stopNear } : { v: null },
      ],
    });
    journeys.push({ idx, chart, f });
    return `<section class="card">
        <div class="row tap" data-chart="${esc(p.symbol)}"><div class="id">${logo(p.symbol, 36)}<div><h2>${esc(cleanSym(p.symbol))}${p.trailing_active ? '<span class="tag good">Trailing</span>' : ''}</h2>
          <div class="sub">${heldMin != null ? `Held ${esc(duration(heldMin))}` : ''}${(stockMeta(p.symbol) || [])[0] ? ` · ${esc(stockMeta(p.symbol)[0])}` : ''}</div></div></div><span class="chev">›</span></div>
        <div class="big ${tone(pnl)}">${esc(money(pnl))}<small>${esc(pct(p.pnl_pct, 2))} · ${esc(rMult(p.r_multiple))}</small></div>
        ${gauge(p)}
        <div class="scrub" id="pj-scrub-${idx}">Trade journey · bought ${esc(fmtShort(p.opened_at) || '–')}</div>
        <div class="plot" id="pj-plot-${idx}">${chart.svg}</div>
        <div class="chips"><span class="chip">Entry<b>${esc(f(entry))}</b></span><span class="chip">Peak<b class="pos">${esc(f(num(p.highest_price) ?? Math.max(entry, cur)))}</b></span><span class="chip">Low<b>${esc(f(num(p.lowest_price) ?? Math.min(entry, cur)))}</b></span></div>
        <ul class="list">
          <li><span class="l">Bought</span><span class="v">${esc((num(p.quantity) || 0).toFixed(4))} @ ${esc(f(entry))}</span></li>
          <li><span class="l">Position value</span><span class="v">${esc(money(p.notional, false))}</span></li>
        </ul></section>`;
  }).join('');
  $('#pos-list').dataset.drawn = '1';
  journeys.forEach(({ idx, chart, f }) => attachScrub($(`#pj-plot-${idx}`), chart.coords, (c) => {
    $(`#pj-scrub-${idx}`).innerHTML = `${esc(c.label)} · <b>${esc(f(c.v))}</b>`;
  }));
}

// Sector donut (same grouping as the desktop allocation card)
function renderAllocation(s) {
  const a = s.allocation || { slices: [], total: 0 };
  const el = $('#alloc-card');
  if (!a.slices.length) { el.hidden = true; return; }
  el.hidden = false;
  const p = s.portfolio || {};
  const R = 46, circ = 2 * Math.PI * R;
  let offset = 0;
  const arcs = a.slices.map((sl) => {
    const len = (sl.value / a.total) * circ;
    const c = `<circle cx="60" cy="60" r="${R}" fill="none" stroke="${sl.color}" stroke-width="12" stroke-dasharray="${len.toFixed(1)} ${(circ - len).toFixed(1)}" stroke-dashoffset="${(-offset).toFixed(1)}"/>`;
    offset += len;
    return c;
  }).join('');
  const legend = a.slices.map((sl) => `<div class="ar"><span><i style="background:${sl.color}"></i><div>${esc(sl.name)}${sl.items.length ? `<em>${esc(sl.items.join(', '))}</em>` : ''}</div></span>
      <b>${esc(`${ACCT}${sl.value.toFixed(0)}`)} <em>${((sl.value / a.total) * 100).toFixed(0)}%</em></b></div>`).join('');
  const bar = a.slices.map((sl) => `<i style="width:${((sl.value / a.total) * 100).toFixed(1)}%;background:${sl.color}"></i>`).join('');
  el.innerHTML = `
    <div class="row"><h2>Allocation</h2><span class="badge-pill ${a.clustered ? 'bad' : 'good'}">${a.clustered ? `⚠ ${esc(a.clustered)}` : '✓ Diversified'}</span></div>
    <div class="alloc"><div class="donut"><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="${R}" fill="none" stroke="${css('--fill')}" stroke-width="12"/>
      <g transform="rotate(-90 60 60)">${arcs}</g></svg>
      <div class="ctr"><small>Active</small><b>${num(p.open_positions_count) || 0}/${num(p.max_open_positions) || 4}</b></div></div>
      <div class="alloc-legend">${legend}</div></div>
    <div class="segbar">${bar}</div>`;
}

// ------------------------------------------------------------ trades
function renderTrades(s) {
  const list = s.closed_trades || [];
  const todayIso = new Date().toISOString().slice(0, 10);
  const today = list.filter((t) => String(t.closed_at || '').startsWith(todayIso));
  const sum = (arr) => arr.reduce((a, t) => a + (num(t.net_pnl) || 0), 0);
  const wins = list.filter((t) => (num(t.net_pnl) || 0) > 0).length;
  $('#trades-summary').innerHTML = `<ul class="list">
      <li><span class="l">Today</span><span class="v ${tone(sum(today))}">${today.length ? `${today.length} · ${esc(money(sum(today)))}` : 'No trades'}</span></li>
      <li><span class="l">Last ${list.length}</span><span class="v ${tone(sum(list))}">${list.length ? `${wins} won · ${esc(money(sum(list)))}` : '–'}</span></li>
    </ul>`;
  $('#trades-list').innerHTML = list.length ? `<h2>Recent</h2><ul class="list">${list.map((t) => {
    const pnl = num(t.net_pnl) || 0;
    return `<li><span class="l">${esc(cleanSym(t.symbol))}<small>${esc(tradeReason(t.reason))} · ${esc(ago(t.closed_at))}</small></span>
      ${miniJourney(t)}<span class="v"><b class="${tone(pnl)}">${esc(money(pnl))}</b>${esc(rMult(t.r_multiple))}</span></li>`;
  }).join('')}</ul>` : '<div class="empty">No closed trades yet</div>';
}

// ------------------------------------------------------------ results
function renderRings(s) {
  const j = (s.long_term || {}).journal || {};
  const p = s.portfolio || {};
  const el = $('#res-rings');
  const winRate = num(j.win_rate_pct) || 0;
  const pf = num(j.profit_factor);
  const pfPct = pf == null ? (j.trades ? 100 : 0) : Math.min(3, pf) / 3 * 100;
  const used = num(p.open_positions_count) || 0, max = num(p.max_open_positions) || 4;
  const rings = [
    { r: 46, color: '#ff2d55', pct: j.trades ? winRate : 0, label: 'Win rate', val: j.trades ? `${winRate.toFixed(0)}%` : '–' },
    { r: 34, color: '#ff9500', pct: pfPct, label: 'Profit factor', val: pf == null ? (j.trades ? '∞' : '–') : `${pf.toFixed(2)}x` },
    { r: 22, color: '#0071e3', pct: (used / max) * 100, label: 'Slots in use', val: `${used} / ${max}` },
  ];
  el.innerHTML = `
    <div class="row"><h2>Health rings</h2><span class="muted small">full journal</span></div>
    <div class="rings"><svg viewBox="0 0 110 110" role="img" aria-label="Win rate, profit factor and slot usage rings">
      ${rings.map((g) => `<circle class="bg" cx="55" cy="55" r="${g.r}" stroke="${g.color}"/><circle class="fg" cx="55" cy="55" r="${g.r}" pathLength="100" stroke="${g.color}" stroke-dasharray="${Math.max(0.01, g.pct).toFixed(1)} 100"/>`).join('')}</svg>
      <div class="legend-rows">${rings.map((g) => `<div class="lr"><span><i style="background:${g.color}"></i>${g.label}</span><b>${esc(g.val)}</b></div>`).join('')}
        <div class="sub">Profit factor ring is scaled 0–3x</div></div></div>`;
}

function histogram(bins) {
  const W = 330, H = 190, padL = 6, padR = 6, padT = 30, padB = 42;
  const pw = W - padL - padR, ph = H - padT - padB;
  const colW = pw / bins.length, barW = Math.min(38, colW * 0.7);
  const maxC = Math.max(1, ...bins.map((b) => b.count));
  const colors = [css('--critical'), '#ff6961', '#ff9500', '#8e8e93', '#34c759', css('--good')];
  const names = ['< −1R', '−1 to −½', '−½ to 0', '0 to ½', '½ to 1½', '≥ 1½'];
  const zeroX = padL + colW * 3;
  const out = [`<line x1="${padL}" x2="${W - padR}" y1="${padT + ph}" y2="${padT + ph}" stroke="${css('--axis')}"/>`,
    `<line x1="${zeroX}" x2="${zeroX}" y1="${padT - 8}" y2="${padT + ph}" stroke="${css('--s1')}" stroke-dasharray="3,3" opacity="0.6"/>`,
    `<text x="${zeroX}" y="${padT - 12}" text-anchor="middle" style="fill:${css('--s1')};font-weight:700">0R breakeven</text>`];
  bins.forEach((b, i) => {
    const bx = padL + i * colW + (colW - barW) / 2;
    const bh = b.count > 0 ? Math.max(5, (b.count / maxC) * ph) : 0;
    out.push(`<rect x="${bx.toFixed(1)}" y="${padT}" width="${barW.toFixed(1)}" height="${ph}" rx="5" fill="${css('--fill')}" opacity="0.5"/>`);
    if (bh) out.push(`<rect x="${bx.toFixed(1)}" y="${(padT + ph - bh).toFixed(1)}" width="${barW.toFixed(1)}" height="${bh.toFixed(1)}" rx="5" fill="${colors[i]}" opacity="0.9"/>`);
    out.push(`<text class="cnt" x="${(bx + barW / 2).toFixed(1)}" y="${(bh ? padT + ph - bh - 4 : padT + ph - 4).toFixed(1)}" text-anchor="middle">${b.count}</text>`);
    out.push(`<text class="lb" x="${(bx + barW / 2).toFixed(1)}" y="${H - padB + 14}" text-anchor="middle">${esc(names[i])}</text>`);
    out.push(`<text x="${(bx + barW / 2).toFixed(1)}" y="${H - padB + 26}" text-anchor="middle">${esc(b.sub)}</text>`);
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Distribution of trade results in R multiples">${out.join('')}</svg>`;
}

function renderResults(s) {
  const lt = s.long_term || {};
  const j = lt.journal || {};
  const eq = lt.equity || {};
  const st = eq.stats || {};
  const fmtA = (v) => `${ACCT}${Number(v).toFixed(2)}`;
  if (!j.trades) {
    $('#res-tiles').innerHTML = `<div class="tile wide">${okMsg('No trades yet', 'Results appear after the first closed trade.')}</div>`;
  } else {
    const pf = num(j.profit_factor);
    $('#res-tiles').innerHTML = [
      `<div class="tile"><div class="t-label">Net P&amp;L</div><div class="big ${tone(j.net_pnl)}">${esc(money(j.net_pnl))}</div>
        <div class="sub">after ${esc(money(j.fees, false))} fees</div><div class="t-foot">${trades(j.trades)}</div></div>`,
      `<div class="tile"><div class="t-label">Average trade</div><div class="big ${tone(j.avg_r)}">${esc(rMult(j.avg_r))}</div>
        <div class="sub">${esc(money(j.expectancy))} each</div><div class="t-foot">${esc(money(j.avg_win))} / ${esc(money(j.avg_loss))}</div></div>`,
      `<div class="tile">${ring(j.win_rate_pct, css('--s1'))}<div class="t-label">Win rate</div><div class="big">${Number(j.win_rate_pct).toFixed(0)}<small>%</small></div>
        <div class="t-foot">${Math.round((j.win_rate_pct / 100) * j.trades)} of ${j.trades} won</div></div>`,
      `<div class="tile"><div class="t-label">Profit factor</div><div class="big ${pf != null && pf >= 1 ? 'pos' : 'neg'}">${pf == null ? '–' : pf.toFixed(2)}</div>
        <div class="sub">£ won per £ lost</div><div class="t-foot">Above 1.00 = profitable</div></div>`,
    ].join('');
  }
  renderRings(s);

  // Equity over the whole life of the account
  const series = (eq.series || []).map((q) => ({ v: Number(q.equity), label: fmtShort(q.ts) }));
  if (series.length >= 2) {
    const ch = areaChart({ id: 'eqall', pts: series, fmt: fmtA, up: series[series.length - 1].v >= series[0].v, xLabels: [fmtDay(eq.series[0].ts), fmtDay(eq.series[eq.series.length - 1].ts)], H: 170, label: 'Account equity, all time' });
    $('#res-equity').innerHTML = `<div class="row"><h2>Account equity</h2><span class="small ${tone(st.change_pct)}">${st.change_pct != null ? `${esc(pct(st.change_pct))} since start` : ''}</span></div>
      <div class="scrub" id="eqall-scrub">${st.peak_equity ? `Peak <b>${esc(money(st.peak_equity, false))}</b> · worst drop <b>−${Number(st.max_drawdown_pct).toFixed(1)}%</b>` : 'Drag across the chart'}</div>
      <div class="plot" id="eqall-plot">${ch.svg}</div>`;
    attachScrub($('#eqall-plot'), ch.coords, (c) => { $('#eqall-scrub').innerHTML = `${esc(c.label)} · <b>${esc(fmtA(c.v))}</b>`; });
  } else {
    $('#res-equity').innerHTML = `<h2>Account equity</h2><div class="empty">Builds up as the bot runs</div>`;
  }

  // Cumulative net P&L trade by trade
  const cum = (j.cumulative || []).map((q) => ({ v: Number(q.cum_pnl), label: fmtShort(q.ts) }));
  $('#res-cum').hidden = cum.length < 2;
  if (cum.length >= 2) {
    const ch = areaChart({ id: 'cum', pts: cum, fmt: (v) => money(v), zero: true, up: cum[cum.length - 1].v >= 0, xLabels: [fmtDay(j.cumulative[0].ts), fmtDay(j.cumulative[j.cumulative.length - 1].ts)], H: 160, label: 'Cumulative profit and loss' });
    $('#res-cum').innerHTML = `<div class="row"><h2>Cumulative P&amp;L</h2><span class="small ${tone(j.net_pnl)}">${esc(money(j.net_pnl))}</span></div>
      <div class="scrub" id="cum-scrub">After each closed trade</div><div class="plot" id="cum-plot">${ch.svg}</div>`;
    attachScrub($('#cum-plot'), ch.coords, (c) => { $('#cum-scrub').innerHTML = `${esc(c.label)} · <b class="${tone(c.v)}">${esc(money(c.v))}</b>`; });
  }

  // Edge matrix: KPIs plus the R-multiple distribution
  const hist = j.r_histogram || [];
  $('#res-edge').hidden = !j.trades;
  if (j.trades) {
    const exp = num(j.avg_r) || 0;
    $('#res-edge').innerHTML = `
      <div class="row"><h2>Edge</h2><span class="badge-pill ${exp >= 0 ? 'good' : 'bad'}">${esc(rMult(exp))} expectancy</span></div>
      <ul class="list">
        <li><span class="l">Payoff ratio<small>${esc(money(j.avg_win, false))} win vs ${esc(money(Math.abs(num(j.avg_loss) || 0), false))} loss</small></span><span class="v">${j.payoff_ratio != null ? `${Number(j.payoff_ratio).toFixed(2)}x` : '–'}</span></li>
        <li><span class="l">Breakeven win rate<small>actual ${Number(j.win_rate_pct).toFixed(0)}%</small></span><span class="v">${j.breakeven_win_rate_pct != null ? `${Number(j.breakeven_win_rate_pct).toFixed(1)}%` : '–'}</span></li>
        <li><span class="l">Holding time<small>winners / losers</small></span><span class="v">${j.avg_hold_win_min != null ? esc(duration(j.avg_hold_win_min)) : '–'} / ${j.avg_hold_loss_min != null ? esc(duration(j.avg_hold_loss_min)) : '–'}</span></li>
      </ul>
      <div class="row" style="margin-top:12px"><span class="muted small">Result of each trade in R (1R = amount risked)</span></div>
      <div class="hist">${hist.length ? histogram(hist) : ''}</div>`;
  }

  const weeks = j.weekly || [];
  $('#res-weeks').hidden = !weeks.length;
  $('#res-weeks').innerHTML = weeks.length ? `<h2>By week</h2><ul class="list">${weeks.map((w) => `
      <li><span class="l">w/c ${esc(fmtDay(w.week_start))}<small>${trades(w.trades)} · ${Number(w.win_rate_pct).toFixed(0)}% won</small></span>
      <span class="v"><b class="${tone(w.net_pnl)}">${esc(money(w.net_pnl))}</b>${esc(rMult(w.avg_r))}</span></li>`).join('')}</ul>` : '';
  const markets = Object.entries(j.by_market || {});
  $('#res-markets').hidden = !markets.length;
  $('#res-markets').innerHTML = markets.length ? `<h2>By market</h2><ul class="list">${markets.map(([m, ms]) => `
      <li><span class="l">${m === 'UK' ? 'UK ETPs' : 'US shares'}<small>${trades(ms.trades)} · ${Number(ms.win_rate_pct).toFixed(0)}% won</small></span>
      <span class="v"><b class="${tone(ms.net_pnl)}">${esc(money(ms.net_pnl))}</b>${esc(rMult(ms.avg_r))}</span></li>`).join('')}</ul>` : '';
}

// ------------------------------------------------------------ screener
function heatStyle(roc) {
  const g = '52, 199, 89', r = '255, 59, 48';
  if (roc >= 3) return `background:linear-gradient(145deg, rgba(${g},.35), rgba(${g},.16));border-color:rgba(${g},.55)`;
  if (roc >= 0.5) return `background:linear-gradient(145deg, rgba(${g},.2), rgba(${g},.08));border-color:rgba(${g},.35)`;
  if (roc <= -3) return `background:linear-gradient(145deg, rgba(${r},.35), rgba(${r},.16));border-color:rgba(${r},.55)`;
  if (roc <= -0.5) return `background:linear-gradient(145deg, rgba(${r},.2), rgba(${r},.08));border-color:rgba(${r},.35)`;
  return 'background:var(--card)';
}

function renderScreener(s) {
  const all = s.picks || [];
  const key = `${s.screener_generated_at}|${state.scrView}|${state.showAll}|${all.length}`;
  const listEl = $('#scr-list');
  document.querySelectorAll('#scr-view button').forEach((b) => b.classList.toggle('on', b.dataset.view === state.scrView));
  $('#version').textContent = `v${s.version || ''} · read-only`;
  const closed = !((s.market_session || {}).is_open || (s.uk_market_session || {}).is_open);
  const stale = $('#scr-stale');
  stale.hidden = !closed;
  if (closed) {
    stale.textContent = `Markets are closed. These ratings are from the last scan${s.screener_generated_at ? ` (${ago(s.screener_generated_at)})` : ''} and do not include pre-market or after-hours moves. Open a stock to see its extended-hours price.`;
  }
  if (listEl.dataset.key === key) return; // nothing new since the last scan: keep the DOM (and loaded logos)
  listEl.dataset.key = key;

  const heat = state.scrView === 'heat';
  $('#scr-note').textContent = `${all.length} symbols${s.screener_generated_at ? ` · scanned ${ago(s.screener_generated_at)}` : ''}. ${heat ? 'Tiles are coloured by the last 10 bars of momentum.' : 'Scores run 0–100; the bot only buys BUY-rated picks while their market is open.'} Tap a stock for its chart.`;
  listEl.hidden = heat;
  $('#scr-heat').hidden = !heat;
  const more = $('#scr-more');
  more.hidden = heat || state.showAll || all.length <= FIRST_PAGE;
  more.textContent = `Show all ${all.length}`;

  if (heat) {
    $('#scr-heat').innerHTML = `<div class="heat">${[...all].sort((a, b) => (num(b.roc_10_pct) || 0) - (num(a.roc_10_pct) || 0)).map((r) => {
      const roc = num(r.roc_10_pct) || 0;
      return `<div class="ht" data-chart="${esc(r.symbol)}" style="${heatStyle(roc)}">${logo(r.symbol, 26)}<strong>${esc(cleanSym(r.symbol))}</strong>
        <span class="px">${esc(price(r.symbol, r.close_price))}</span><span class="rc ${tone(roc)}">${esc(pct(roc, 1))}</span></div>`;
    }).join('')}</div>`;
    return;
  }
  const shown = state.showAll ? all : all.slice(0, FIRST_PAGE);
  listEl.innerHTML = shown.length ? `<ul class="list">${shown.map((r) => {
    const rating = String(r.rating || '');
    const tag = rating.includes('BUY') ? 'good' : rating === 'WATCH' ? 'warning' : 'blue';
    const meta = stockMeta(r.symbol);
    return `<li class="srow tap" data-chart="${esc(r.symbol)}">${logo(r.symbol, 34)}
      <div class="mid"><div class="tk">${esc(cleanSym(r.symbol))}<span class="tag ${tag}">${esc(rating)}</span></div><small>${esc(r.blocker || (meta ? meta[0] : ''))}</small></div>
      <div class="spk">${spark(r.spark, r.roc_10_pct)}<span>${esc(price(r.symbol, r.close_price))}</span></div>${dial(r.score)}<span class="chev">›</span></li>`;
  }).join('')}</ul>` : '<div class="empty">No scan results yet</div>';
}

// ------------------------------------------------------------ candle chart sheet
const chart = { symbol: null, data: null, bars: 30 };

function fmtPx(v) {
  const n = num(v);
  if (n === null) return '–';
  return n >= 1000 ? n.toFixed(0) : n >= 100 ? n.toFixed(2) : n.toFixed(n >= 10 ? 2 : 3);
}
function fmtVol(v) {
  const n = num(v) || 0;
  return n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(0)}k` : `${n.toFixed(0)}`;
}
const barTime = (iso) => new Date(iso).toLocaleString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit' });

function candleSvg(bars, lines) {
  const W = 360, padR = 46, topPad = 8, priceH = 170, gap = 10, volH = 40, axisH = 14;
  const H = topPad + priceH + gap + volH + axisH;
  const n = bars.length;
  const step = (W - padR) / n;
  const bodyW = Math.max(1.5, Math.min(8, step * 0.62));
  const vals = [];
  bars.forEach((b) => { vals.push(b.h, b.l); if (b.e1) vals.push(b.e1); if (b.e2) vals.push(b.e2); });
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const span0 = hi - lo || 1;
  const shown = lines.filter((ln) => ln.v != null && ln.v > lo - span0 * 0.6 && ln.v < hi + span0 * 0.6);
  shown.forEach((ln) => { lo = Math.min(lo, ln.v); hi = Math.max(hi, ln.v); });
  const pad = (hi - lo) * 0.06 || 1;
  lo -= pad; hi += pad;
  const y = (v) => topPad + ((hi - v) / (hi - lo)) * priceH;
  const x = (i) => i * step + step / 2;
  const vMax = Math.max(...bars.map((b) => b.v || 0)) || 1;
  const up = css('--good'), down = css('--critical');

  const parts = [];
  for (let k = 0; k <= 3; k++) {
    const v = lo + ((hi - lo) * k) / 3;
    parts.push(`<line x1="0" x2="${W - padR}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${css('--grid')}"/>`);
    parts.push(`<text x="${W - padR + 4}" y="${(y(v) + 3).toFixed(1)}">${esc(fmtPx(v))}</text>`);
  }
  let lastDay = null;
  bars.forEach((b, i) => {
    const day = new Date(b.t).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' });
    if (day !== lastDay) {
      if (lastDay !== null) parts.push(`<line x1="${(i * step).toFixed(1)}" x2="${(i * step).toFixed(1)}" y1="0" y2="${topPad + priceH + gap + volH}" stroke="${css('--axis')}" stroke-dasharray="2,3"/>`);
      if (n - i > 3) parts.push(`<text x="${(i * step + 2).toFixed(1)}" y="${H - 2}">${esc(day)}</text>`);
      lastDay = day;
    }
  });
  shown.forEach((ln) => {
    const yy = y(ln.v).toFixed(1);
    parts.push(`<line x1="0" x2="${W - padR}" y1="${yy}" y2="${yy}" stroke="${ln.color}" stroke-width="1.2" stroke-dasharray="5,4"/>`);
  });
  bars.forEach((b, i) => {
    const h = ((b.v || 0) / vMax) * volH;
    parts.push(`<rect x="${(x(i) - bodyW / 2).toFixed(1)}" y="${(topPad + priceH + gap + volH - h).toFixed(1)}" width="${bodyW.toFixed(1)}" height="${h.toFixed(1)}" fill="${b.c >= b.o ? up : down}" opacity="0.35"/>`);
  });
  bars.forEach((b, i) => {
    const col = b.c >= b.o ? up : down;
    const top = y(Math.max(b.o, b.c)), bot = y(Math.min(b.o, b.c));
    parts.push(`<line x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${y(b.h).toFixed(1)}" y2="${y(b.l).toFixed(1)}" stroke="${col}" stroke-width="1"/>`);
    parts.push(`<rect x="${(x(i) - bodyW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bodyW.toFixed(1)}" height="${Math.max(1, bot - top).toFixed(1)}" fill="${col}" rx="0.6"/>`);
  });
  const poly = (key) => bars.map((b, i) => (b[key] ? `${x(i).toFixed(1)},${y(b[key]).toFixed(1)}` : null)).filter(Boolean).join(' ');
  parts.push(`<polyline points="${poly('e1')}" fill="none" stroke="${css('--s1')}" stroke-width="1.6"/>`);
  parts.push(`<polyline points="${poly('e2')}" fill="none" stroke="${css('--s4')}" stroke-width="1.6"/>`);
  const last = bars[n - 1];
  const ly = Math.min(topPad + priceH - 8, Math.max(topPad + 8, y(last.c)));
  parts.push(`<rect x="${W - padR + 1}" y="${(ly - 8).toFixed(1)}" width="${padR - 2}" height="16" rx="4" fill="${last.c >= bars[0].o ? up : down}"/>`);
  parts.push(`<text x="${W - padR + 4}" y="${(ly + 3.5).toFixed(1)}" style="fill:#fff;font-weight:600">${esc(fmtPx(last.c))}</text>`);
  parts.push(`<line id="xhair" x1="0" x2="0" y1="0" y2="${topPad + priceH + gap + volH}" stroke="${css('--text')}" stroke-width="1" opacity="0"/>`);
  return { svg: `<svg viewBox="0 0 ${W} ${H}" aria-label="Candle chart">${parts.join('')}</svg>`, step, W, padR, x };
}

function setReadout(bars, i) {
  const b = bars[i];
  if (!b) return;
  const chg = ((b.c - b.o) / b.o) * 100;
  $('#sheet-readout').innerHTML = `${esc(barTime(b.t))} · O <b>${esc(fmtPx(b.o))}</b> H <b>${esc(fmtPx(b.h))}</b> L <b>${esc(fmtPx(b.l))}</b> C <b class="${tone(chg)}">${esc(fmtPx(b.c))}</b> · Vol ${esc(fmtVol(b.v))}`;
}

function drawChart() {
  const d = chart.data;
  if (!d || !d.bars || !d.bars.length) return;
  const bars = d.bars.slice(-chart.bars);
  const rec = d.screener || {}, pos = d.position;
  const lines = [];
  if (pos) {
    lines.push({ v: num(pos.entry_price), color: css('--muted'), label: 'Entry' });
    lines.push({ v: num(pos.stop_loss), color: css('--critical'), label: 'Stop' });
    lines.push({ v: num(pos.take_profit), color: css('--good'), label: 'Target' });
  } else {
    lines.push({ v: num(rec.suggested_stop_loss), color: css('--critical'), label: 'Suggested stop' });
    lines.push({ v: num(rec.suggested_take_profit), color: css('--good'), label: 'Suggested target' });
  }
  const c = candleSvg(bars, lines);
  const el = $('#sheet-chart');
  el.innerHTML = c.svg;

  const first = bars[0], last = bars[bars.length - 1];
  const chg = ((last.c - first.o) / first.o) * 100;
  const ccy = d.price_currency || '$';
  $('#sheet-sub').innerHTML = `<b>${esc(ccy)}${esc(fmtPx(last.c))}</b> <span class="${tone(chg)}">${esc(pct(chg, 2))}</span> over ${chart.bars === 30 ? 'the last day' : chart.bars === 80 ? '3 days' : 'the week'}`
    + (d.extended ? `<br><b class="${tone(d.extended.change_pct)}">${esc(d.extended.label)} ${esc(ccy)}${esc(fmtPx(d.extended.price))} (${esc(pct(d.extended.change_pct, 1))})</b> <span class="muted">not shown on the chart</span>` : '');
  $('#sheet-legend').innerHTML = `<span><i style="background:${css('--s1')}"></i>EMA 20</span><span><i style="background:${css('--s4')}"></i>EMA 50</span>` +
    lines.filter((l) => l.v != null).map((l) => `<span style="color:${l.color}"><i class="dash"></i><span style="color:var(--text-2)">${esc(l.label)} ${esc(ccy)}${esc(fmtPx(l.v))}</span></span>`).join('');
  setReadout(bars, bars.length - 1);

  const svg = el.querySelector('svg');
  const hair = svg.querySelector('#xhair');
  const pick = (ev) => {
    const rect = svg.getBoundingClientRect();
    const px = ((ev.clientX - rect.left) / rect.width) * c.W;
    const i = Math.max(0, Math.min(bars.length - 1, Math.floor(px / c.step)));
    hair.setAttribute('x1', c.x(i)); hair.setAttribute('x2', c.x(i)); hair.setAttribute('opacity', '0.5');
    setReadout(bars, i);
  };
  svg.addEventListener('pointerdown', pick);
  svg.addEventListener('pointermove', (ev) => { if (ev.pointerType === 'mouse' || ev.buttons || ev.pressure > 0) pick(ev); });
}

function renderSheetStats() {
  const d = chart.data || {};
  const r = d.screener || {};
  const ccy = d.price_currency || '$';
  const row = (l, v, cls = '') => `<li><span class="l">${esc(l)}</span><span class="v ${cls}">${esc(v)}</span></li>`;
  const items = [];
  if (r.score != null) items.push(row('Score', `${Number(r.score).toFixed(0)} / 100 · #${r.rank}`));
  if (r.rating) items.push(row('Rating', r.rating));
  const rsi = num(r.rsi) ?? num(d.rsi);
  if (rsi != null) items.push(row('RSI (14)', rsi.toFixed(1)));
  if (r.rvol != null) items.push(row('Volume vs average', `${Number(r.rvol).toFixed(2)}x`));
  if (r.roc_10_pct != null) items.push(row('Last 10 bars', pct(r.roc_10_pct, 2), tone(r.roc_10_pct)));
  if (d.position) items.push(row('Holding', `entry ${ccy}${fmtPx(d.position.entry_price)}`));
  if (r.blocker || r.thesis) {
    items.push(`<li><span class="l" style="white-space:normal">${r.blocker ? 'Why not buying' : 'Thesis'}<small style="white-space:normal">${esc(r.blocker || r.thesis)}</small></span></li>`);
  }
  $('#sheet-stats').innerHTML = items.join('') || '<li><span class="l muted">No screener data for this symbol yet</span></li>';
}

async function openChart(symbol) {
  chart.symbol = symbol;
  chart.data = null;
  $('#sheet-logo').innerHTML = logo(symbol, 42);
  $('#sheet-title').textContent = cleanSym(symbol);
  $('#sheet-sub').textContent = 'Loading…';
  $('#sheet-readout').textContent = '';
  $('#sheet-legend').innerHTML = '';
  $('#sheet-stats').innerHTML = '';
  $('#sheet-chart').innerHTML = '<div class="empty">Loading chart…</div>';
  $('#sheet').hidden = false;
  document.body.style.overflow = 'hidden';
  try {
    const res = await fetch(`/api/mobile/chart?symbol=${encodeURIComponent(symbol)}&bars=130`, { cache: 'no-store' });
    const body = await res.json();
    if (chart.symbol !== symbol) return; // closed or switched while loading
    if (!res.ok) throw new Error(body.error || `Server replied ${res.status}`);
    chart.data = body;
    drawChart();
    renderSheetStats();
  } catch (e) {
    if (chart.symbol !== symbol) return;
    $('#sheet-sub').textContent = '';
    $('#sheet-chart').innerHTML = `<div class="empty">${esc(e.message || 'Chart unavailable')}</div>`;
  }
}
function closeChart() {
  chart.symbol = null;
  $('#sheet').hidden = true;
  document.body.style.overflow = '';
}

// ------------------------------------------------------------ tabs, events, data loading
function render() {
  const s = state.snap;
  if (!s) return;
  ACCT = s.account_currency_symbol || '£';
  renderHome(s);
  if (state.tab === 'home') renderEquityToday(s);
  if (state.tab === 'positions') { renderPositions(s); renderAllocation(s); }
  if (state.tab === 'trades') renderTrades(s);
  if (state.tab === 'results') renderResults(s);
  if (state.tab === 'screener') renderScreener(s);
}

function setTab(t, remember = true) {
  if (!TABS.includes(t)) t = 'home';
  state.tab = t;
  for (const x of TABS) $(`#tab-${x}`).hidden = x !== t;
  document.querySelectorAll('#tabbar button').forEach((b) => b.classList.toggle('on', b.dataset.tab === t));
  if (remember) {
    try { localStorage.setItem('t212-mtab', t); } catch (e) { /* private mode */ }
    history.replaceState(null, '', `#${t}`);
  }
  scrollTo(0, 0);
  $('#pos-list').dataset.drawn = '';
  render();
}
$('#tabbar').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b) setTab(b.dataset.tab);
});
document.addEventListener('click', (e) => {
  const row = e.target.closest('[data-chart]');
  if (row) { openChart(row.dataset.chart); return; }
  if (e.target.closest('[data-close]')) { closeChart(); return; }
  const seg = e.target.closest('#sheet-range button');
  if (seg) {
    chart.bars = Number(seg.dataset.bars);
    document.querySelectorAll('#sheet-range button').forEach((b) => b.classList.toggle('on', b === seg));
    drawChart();
    return;
  }
  const eqBtn = e.target.closest('[data-eq]');
  if (eqBtn) { state.eqView = eqBtn.dataset.eq; $('#home-equity').dataset.drawn = ''; renderEquityToday(state.snap); return; }
  const viewBtn = e.target.closest('#scr-view button');
  if (viewBtn) { state.scrView = viewBtn.dataset.view; $('#scr-list').dataset.key = ''; renderScreener(state.snap); return; }
  if (e.target.closest('#scr-more')) { state.showAll = true; $('#scr-list').dataset.key = ''; renderScreener(state.snap); return; }
  const go = e.target.closest('[data-go]');
  if (go) setTab(go.dataset.go);
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#sheet').hidden) closeChart(); });

async function refresh() {
  try {
    const res = await fetch('/api/mobile', { cache: 'no-store' });
    if (!res.ok) throw new Error(`Server replied ${res.status}`);
    state.snap = await res.json();
    state.error = null;
  } catch (e) {
    state.error = state.snap ? 'Showing the last data received' : 'Are you on your home network?';
    if (!state.snap) {
      $('#status').className = 'pill critical';
      $('#status').querySelector('span').textContent = 'Offline';
      $('#home-attn').innerHTML = alertRow('critical', "Can't reach the bot", state.error);
      return;
    }
  }
  render();
}

let timer = null;
function startTimers() {
  clearInterval(timer);
  timer = setInterval(refresh, REFRESH_MS);
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) clearInterval(timer);
  else { refresh(); startTimers(); }
});

let saved = null;
try { saved = localStorage.getItem('t212-mtab'); } catch (e) { /* private mode */ }
const hashTab = location.hash.slice(1);
state.tab = TABS.includes(hashTab) ? hashTab : saved || 'home';
if (hashTab === 'heatmap') { state.tab = 'screener'; state.scrView = 'heat'; } // /m#heatmap opens the screener heatmap
const chartLink = location.hash.match(/^#chart=([A-Za-z0-9_.]+)$/); // e.g. /m#chart=NVDA_US_EQ
if (chartLink) state.tab = 'screener';
setTab(state.tab, false);
refresh();
startTimers();
if (chartLink) openChart(chartLink[1]);
