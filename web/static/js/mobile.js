// iPhone page for the trading bot (/m). Read-only: polls /api/mobile and renders five tabs.
// Tab behaviour mirrors the Earlswood Road home dashboard: bottom tab bar, last tab remembered,
// #tab in the address, and home tiles that jump to their tab.
'use strict';

const REFRESH_MS = 15000;
const STALE_AFTER_SEC = 120; // the bot refreshes its status every poll (~15 s)
const TABS = ['home', 'positions', 'trades', 'results', 'screener'];
const state = { tab: 'home', snap: null, error: null };
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
const trades = (n) => `${n} trade${Number(n) === 1 ? '' : 's'}`;
const tradeReason = (r) => String(r || '').split(' (')[0].split(':')[0].replace(/\s+hit at .*$/i, '');

function botHealth(s) {
  const updated = s.activity && s.activity.updated_at;
  const age = updated ? (Date.now() - new Date(updated).getTime()) / 1000 : Infinity;
  if (state.error) return { level: 'critical', label: 'Offline', detail: state.error };
  if (age > STALE_AFTER_SEC) return { level: 'critical', label: 'Stopped', detail: `No update since ${ago(updated)}` };
  if (s.portfolio && s.portfolio.circuit_breaker_tripped) return { level: 'serious', label: 'Paused', detail: 'Circuit breaker tripped' };
  return { level: 'good', label: 'Running', detail: `Updated ${ago(updated)}` };
}

function sparkline(series, key) {
  if (!series || series.length < 2) return '<div class="empty">Builds up as the bot runs</div>';
  const W = 340, H = 140, padB = 16, padR = 44; // right margin keeps the price labels clear of the line
  const vals = series.map((p) => Number(p[key]));
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const x = (i) => (i / (vals.length - 1)) * (W - padR);
  const y = (v) => 4 + (1 - (v - min) / span) * (H - padB - 8);
  const pts = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const col = vals[vals.length - 1] >= vals[0] ? css('--good') : css('--critical');
  const d0 = new Date(series[0].ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  const d1 = new Date(series[series.length - 1].ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="Equity history">
      <defs><linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${col}" stop-opacity="0.25"/><stop offset="100%" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
      <polygon points="${pts} ${W - padR},${H - padB} 0,${H - padB}" fill="url(#eq-grad)"/>
      <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
      <text x="0" y="${H - 2}">${esc(d0)}</text><text x="${W - padR}" y="${H - 2}" text-anchor="end">${esc(d1)}</text>
      <text x="${W}" y="12" text-anchor="end">${esc(ACCT)}${max.toFixed(0)}</text><text x="${W}" y="${H - padB - 4}" text-anchor="end">${esc(ACCT)}${min.toFixed(0)}</text>
    </svg>`;
}

// ------------------------------------------------------------ tabs
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

function runway(p) {
  const stop = num(p.stop_loss), tp = num(p.take_profit), entry = num(p.entry_price), cur = num(p.current_price);
  if ([stop, tp, entry, cur].some((v) => v === null) || tp <= stop) return '';
  const lo = Math.min(stop, cur), hi = Math.max(tp, cur);
  const at = (v) => ((v - lo) / (hi - lo)) * 100;
  const col = cur >= entry ? css('--good') : css('--critical');
  return `<div class="runway"><div class="track"></div>
      <div class="mark" style="left:${at(stop)}%"></div><div class="mark entry" style="left:${at(entry)}%"></div><div class="mark" style="left:${at(tp)}%"></div>
      <div class="now" style="left:${at(cur)}%;background:${col}"></div>
      <div class="lbl" style="left:0">Stop ${esc(price(p.symbol, stop))}</div>
      <div class="lbl right" style="left:100%">Target ${esc(price(p.symbol, tp))}</div></div>`;
}

function renderPositions(s) {
  const list = s.positions || [];
  const openPnl = list.reduce((a, x) => a + (num(x.unrealized_pnl) || 0), 0);
  const pill = $('#pos-pill');
  pill.className = `pill ${list.length ? (openPnl >= 0 ? 'good' : 'critical') : ''}`;
  pill.querySelector('span').textContent = list.length ? `${list.length} open · ${money(openPnl)}` : 'All cash';

  if (!list.length) {
    const us = s.market_session || {};
    $('#pos-list').innerHTML = `<section class="card">${okMsg('No open positions', us.is_open ? 'The bot is watching for a setup.' : `Markets closed.${us.next_open_str ? ` US opens ${us.next_open_str}.` : ''}`)}</section>`;
    return;
  }
  $('#pos-list').innerHTML = list.map((p) => {
    const pnl = num(p.unrealized_pnl) || 0;
    const held = p.opened_at ? duration((Date.now() - new Date(p.opened_at).getTime()) / 60000) : '–';
    return `<section class="card tap" data-chart="${esc(p.symbol)}">
        <div class="row"><h2>${esc(cleanSym(p.symbol))}${p.trailing_active ? '<span class="tag good">Trailing</span>' : ''}</h2><span class="muted small">Held ${esc(held)}<span class="chev">›</span></span></div>
        <div class="big ${tone(pnl)}">${esc(money(pnl))}<small>${esc(pct(p.pnl_pct, 2))} · ${esc(rMult(p.r_multiple))}</small></div>
        ${runway(p)}
        <ul class="list">
          <li><span class="l">Bought</span><span class="v">${esc((num(p.quantity) || 0).toFixed(4))} @ ${esc(price(p.symbol, p.entry_price))}</span></li>
          <li><span class="l">Now</span><span class="v">${esc(price(p.symbol, p.current_price))}</span></li>
          <li><span class="l">Value</span><span class="v">${esc(money(p.notional, false))}</span></li>
        </ul></section>`;
  }).join('');
}

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
    return `<li><span class="l">${esc(cleanSym(t.symbol))}<small>${esc(tradeReason(t.reason))} · ${esc(ago(t.closed_at))}${t.held_minutes != null ? ` · held ${esc(duration(t.held_minutes))}` : ''}</small></span>
      <span class="v"><b class="${tone(pnl)}">${esc(money(pnl))}</b>${esc(rMult(t.r_multiple))}</span></li>`;
  }).join('')}</ul>` : '<div class="empty">No closed trades yet</div>';
}

function renderResults(s) {
  const lt = s.long_term || {};
  const j = lt.journal || {};
  const eq = lt.equity || {};
  const st = eq.stats || {};
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
  $('#res-equity').innerHTML = `<div class="row"><h2>Equity</h2><span class="small ${tone(st.change_pct)}">${st.change_pct != null ? `${esc(pct(st.change_pct))} since start` : ''}</span></div>
    <div class="chart">${sparkline(eq.series, 'equity')}</div>
    ${st.peak_equity ? `<ul class="list"><li><span class="l">Peak</span><span class="v">${esc(money(st.peak_equity, false))}</span></li>
      <li><span class="l">Worst drop</span><span class="v">−${Number(st.max_drawdown_pct).toFixed(1)}%</span></li></ul>` : ''}`;
  const weeks = j.weekly || [];
  $('#res-weeks').hidden = !weeks.length;
  $('#res-weeks').innerHTML = weeks.length ? `<h2>By week</h2><ul class="list">${weeks.map((w) => `
      <li><span class="l">w/c ${esc(new Date(w.week_start).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }))}<small>${trades(w.trades)} · ${Number(w.win_rate_pct).toFixed(0)}% won</small></span>
      <span class="v"><b class="${tone(w.net_pnl)}">${esc(money(w.net_pnl))}</b>${esc(rMult(w.avg_r))}</span></li>`).join('')}</ul>` : '';
  const markets = Object.entries(j.by_market || {});
  $('#res-markets').hidden = !markets.length;
  $('#res-markets').innerHTML = markets.length ? `<h2>By market</h2><ul class="list">${markets.map(([m, ms]) => `
      <li><span class="l">${m === 'UK' ? 'UK ETPs' : 'US shares'}<small>${trades(ms.trades)} · ${Number(ms.win_rate_pct).toFixed(0)}% won</small></span>
      <span class="v"><b class="${tone(ms.net_pnl)}">${esc(money(ms.net_pnl))}</b>${esc(rMult(ms.avg_r))}</span></li>`).join('')}</ul>` : '';
}

function renderScreener(s) {
  const list = s.top_picks || [];
  $('#scr-note').textContent = `Top ${list.length} from the latest scan${s.screener_generated_at ? `, ${ago(s.screener_generated_at)}` : ''}. Scores run 0–100; the bot only buys BUY-rated picks while their market is open. Tap a stock for its chart.`;
  $('#scr-list').innerHTML = list.length ? `<ul class="list">${list.map((r) => {
    const rating = String(r.rating || '');
    const tag = rating.includes('BUY') ? 'good' : rating === 'WATCH' ? 'warning' : 'blue';
    const why = r.blocker || (r.actionable ? 'Meets the entry rules' : `RSI ${(num(r.rsi) || 0).toFixed(0)} · volume ${(num(r.rvol) || 0).toFixed(1)}x`);
    return `<li class="tap" data-chart="${esc(r.symbol)}"><span class="l">#${esc(r.rank)} ${esc(cleanSym(r.symbol))}<span class="tag ${tag}">${esc(rating)}</span><small>${esc(why)}</small></span>
      <span class="v"><b>${(num(r.score) || 0).toFixed(0)}</b>${esc(price(r.symbol, r.close_price))}</span><span class="chev">›</span></li>`;
  }).join('')}</ul>` : '<div class="empty">No scan results yet</div>';
  $('#version').textContent = `v${s.version || ''} · read-only`;
}


// ------------------------------------------------------------ candle chart sheet
const chart = { symbol: null, data: null, bars: 30, sel: null };

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
  // Only draw reference lines that sit near the visible range, so they don't squash the candles
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
  // grid + price labels
  for (let k = 0; k <= 3; k++) {
    const v = lo + ((hi - lo) * k) / 3;
    parts.push(`<line x1="0" x2="${W - padR}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${css('--grid')}"/>`);
    parts.push(`<text x="${W - padR + 4}" y="${(y(v) + 3).toFixed(1)}">${esc(fmtPx(v))}</text>`);
  }
  // day separators and labels
  let lastDay = null;
  bars.forEach((b, i) => {
    const day = new Date(b.t).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' });
    if (day !== lastDay) {
      if (lastDay !== null) parts.push(`<line x1="${(i * step).toFixed(1)}" x2="${(i * step).toFixed(1)}" y1="0" y2="${topPad + priceH + gap + volH}" stroke="${css('--axis')}" stroke-dasharray="2,3"/>`);
      if (n - i > 3) parts.push(`<text x="${(i * step + 2).toFixed(1)}" y="${H - 2}">${esc(day)}</text>`);
      lastDay = day;
    }
  });
  // reference lines (stop / target / entry)
  shown.forEach((ln) => {
    const yy = y(ln.v).toFixed(1);
    parts.push(`<line x1="0" x2="${W - padR}" y1="${yy}" y2="${yy}" stroke="${ln.color}" stroke-width="1.2" stroke-dasharray="5,4"/>`);
  });
  // volume
  bars.forEach((b, i) => {
    const h = ((b.v || 0) / vMax) * volH;
    parts.push(`<rect x="${(x(i) - bodyW / 2).toFixed(1)}" y="${(topPad + priceH + gap + volH - h).toFixed(1)}" width="${bodyW.toFixed(1)}" height="${h.toFixed(1)}" fill="${b.c >= b.o ? up : down}" opacity="0.35"/>`);
  });
  // candles
  bars.forEach((b, i) => {
    const col = b.c >= b.o ? up : down;
    const top = y(Math.max(b.o, b.c)), bot = y(Math.min(b.o, b.c));
    parts.push(`<line x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${y(b.h).toFixed(1)}" y2="${y(b.l).toFixed(1)}" stroke="${col}" stroke-width="1"/>`);
    parts.push(`<rect x="${(x(i) - bodyW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bodyW.toFixed(1)}" height="${Math.max(1, bot - top).toFixed(1)}" fill="${col}" rx="0.6"/>`);
  });
  // EMAs
  const poly = (key) => bars.map((b, i) => (b[key] ? `${x(i).toFixed(1)},${y(b[key]).toFixed(1)}` : null)).filter(Boolean).join(' ');
  parts.push(`<polyline points="${poly('e1')}" fill="none" stroke="${css('--s1')}" stroke-width="1.6"/>`);
  parts.push(`<polyline points="${poly('e2')}" fill="none" stroke="${css('--s4')}" stroke-width="1.6"/>`);
  // last price tag
  const last = bars[n - 1];
  const ly = Math.min(topPad + priceH - 8, Math.max(topPad + 8, y(last.c)));
  parts.push(`<rect x="${W - padR + 1}" y="${(ly - 8).toFixed(1)}" width="${padR - 2}" height="16" rx="4" fill="${last.c >= bars[0].o ? up : down}"/>`);
  parts.push(`<text x="${W - padR + 4}" y="${(ly + 3.5).toFixed(1)}" style="fill:#fff;font-weight:600">${esc(fmtPx(last.c))}</text>`);
  // crosshair (moved by touch)
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
  $('#sheet-sub').innerHTML = `<b>${esc(ccy)}${esc(fmtPx(last.c))}</b> <span class="${tone(chg)}">${esc(pct(chg, 2))}</span> over ${chart.bars === 30 ? 'the last day' : chart.bars === 80 ? '3 days' : 'the week'}`;
  $('#sheet-legend').innerHTML = `<span><i style="background:${css('--s1')}"></i>EMA 20</span><span><i style="background:${css('--s4')}"></i>EMA 50</span>` +
    lines.filter((l) => l.v != null).map((l) => `<span style="color:${l.color}"><i class="dash"></i><span style="color:var(--text-2)">${esc(l.label)} ${esc(ccy)}${esc(fmtPx(l.v))}</span></span>`).join('');
  setReadout(bars, bars.length - 1);

  // Tap / drag to inspect a candle (phones have no hover)
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
document.addEventListener('click', (e) => {
  const row = e.target.closest('[data-chart]');
  if (row) { openChart(row.dataset.chart); return; }
  if (e.target.closest('[data-close]')) closeChart();
  const seg = e.target.closest('#sheet-range button');
  if (seg) {
    chart.bars = Number(seg.dataset.bars);
    document.querySelectorAll('#sheet-range button').forEach((b) => b.classList.toggle('on', b === seg));
    drawChart();
  }
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#sheet').hidden) closeChart(); });

function render() {
  const s = state.snap;
  if (!s) return;
  ACCT = s.account_currency_symbol || '£';
  renderHome(s);
  if (state.tab === 'positions') renderPositions(s);
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
  render();
}
$('#tabbar').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b) setTab(b.dataset.tab);
});
document.addEventListener('click', (e) => {
  const go = e.target.closest('[data-go]');
  if (go) setTab(go.dataset.go);
});

// ------------------------------------------------------------ data loading
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
const chartLink = location.hash.match(/^#chart=([A-Za-z0-9_.]+)$/); // e.g. /m#chart=NVDA_US_EQ
if (chartLink) state.tab = 'screener';
setTab(state.tab, false);
refresh();
startTimers();
if (chartLink) openChart(chartLink[1]);
