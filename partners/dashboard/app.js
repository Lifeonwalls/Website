/* Partner Clicks dashboard. Reads window.PC_DATA = {generatedAt, rows:[...]} embedded by the n8n partners.dashboard workflow. */
(function () {
  'use strict';
  var DATA = window.PC_DATA || {rows: [], generatedAt: null};
  var PARTNERS = [
    {key: 'evergreen-exterior-services', name: 'Evergreen Exterior Services', short: 'Evergreen', color: 'var(--ever)'},
    {key: 'ilo-bloom', name: 'Ilo Bloom', short: 'Ilo Bloom', color: 'var(--ilo)'}
  ];
  var PNAME = {}; PARTNERS.forEach(function (p) { PNAME[p.key] = p; });
  var LINKS = {website: 'Website', shop: 'Online shop', instagram: 'Instagram', directions: 'Directions', other: 'Other'};
  var DEVICES = {mobile: 'Mobile', tablet: 'Tablet', desktop: 'Desktop'};
  var PERIOD_WORDS = {'7': 'the last 7 days', '30': 'the last 30 days', '90': 'the last 90 days', '365': 'the last 12 months', 'all': 'all time'};
  var PREV_WORDS = {'7': 'previous 7 days', '30': 'previous 30 days', '90': 'previous 90 days', '365': 'previous 12 months'};
  var DAY = 86400000;
  var nf = new Intl.NumberFormat('en-GB');
  var rows = (DATA.rows || []).map(function (r) { r.ts = Date.parse(r.clickedAt); return r; }).filter(function (r) { return !isNaN(r.ts); });

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function dayOf(ts) { return new Date(ts).toLocaleDateString('en-CA', {timeZone: 'Europe/London'}); }
  function countBy(list, key) {
    var m = {};
    list.forEach(function (r) { var k = key(r); m[k] = (m[k] || 0) + 1; });
    return Object.keys(m).map(function (k) { return {label: k, n: m[k]}; }).sort(function (a, b) { return b.n - a.n; });
  }
  function sourceOf(r) {
    if (r.utmSource) return r.utmSource + (r.utmMedium ? ' / ' + r.utmMedium : '');
    return r.referrer === 'internal' ? 'lifeonwalls.co.uk (internal)' : (r.referrer || 'direct');
  }

  function render() {
    var range = $('range').value;
    var now = Date.now();
    var days = range === 'all' ? null : Number(range);
    var cur = days ? rows.filter(function (r) { return r.ts > now - days * DAY && r.ts <= now; }) : rows;
    var prev = days ? rows.filter(function (r) { return r.ts > now - 2 * days * DAY && r.ts <= now - days * DAY; }) : null;
    var by = function (list, key) { return list.filter(function (r) { return r.partner === key; }).length; };
    var visitors = {}; cur.forEach(function (r) { if (r.sessionId) visitors[r.sessionId] = 1; });
    var nVisitors = Object.keys(visitors).length;

    tile('k-total', cur.length, prev ? prev.length : null, range);
    tile('k-ever', by(cur, PARTNERS[0].key), prev ? by(prev, PARTNERS[0].key) : null, range);
    tile('k-ilo', by(cur, PARTNERS[1].key), prev ? by(prev, PARTNERS[1].key) : null, range);
    $('k-vis').textContent = nf.format(nVisitors);

    var lede;
    if (!cur.length) {
      lede = 'No clicks to partner sites in ' + PERIOD_WORDS[range] + ' yet. Clicks appear here as soon as visitors use the links on the Partners pages.';
    } else {
      var e = by(cur, PARTNERS[0].key), i = by(cur, PARTNERS[1].key);
      lede = nf.format(cur.length) + (cur.length === 1 ? ' click' : ' clicks') + ' to partner sites in ' + PERIOD_WORDS[range] + ' from ' + nf.format(nVisitors) +
        (nVisitors === 1 ? ' visitor. ' : ' visitors. ') +
        (e === i ? 'Both partners received the same number.' : (e > i ? PARTNERS[0].name : PARTNERS[1].name) + ' received ' + Math.round(100 * Math.max(e, i) / cur.length) + '% of them.');
    }
    $('lede').textContent = lede;

    daily(cur, range, now);
    bars('b-link', countBy(cur, function (r) { return (PNAME[r.partner] ? PNAME[r.partner].short : r.partner) + ' · ' + (LINKS[r.linkType] || r.linkType); }), true);
    bars('b-place', countBy(cur, function (r) { return r.placement || 'Unknown'; }));
    bars('b-source', countBy(cur, sourceOf).slice(0, 8));
    bars('b-device', countBy(cur, function (r) { return DEVICES[r.device] || 'Unknown'; }));
    recent(cur);
  }

  function tile(id, n, before, range) {
    $(id).textContent = nf.format(n);
    var d = $(id + '-d');
    d.replaceChildren();
    if (before === null) { d.textContent = 'Since tracking began'; return; }
    var diff = n - before;
    var s = el('span', diff > 0 ? 'up' : (diff < 0 ? 'down' : ''), (diff > 0 ? '+' : diff < 0 ? '−' : '±') + nf.format(Math.abs(diff)));
    d.append(s, document.createTextNode(' vs ' + PREV_WORDS[range] + ' (' + nf.format(before) + ')'));
  }

  function bars(id, data, byPartner) {
    var box = $(id);
    box.replaceChildren();
    if (!data.length) { box.append(el('p', 'empty', 'No clicks in this period yet.')); return; }
    var max = data[0].n;
    data.forEach(function (d) {
      var row = el('div', 'bar');
      row.append(el('span', 'bar-name', d.label), el('span', 'bar-n', nf.format(d.n)));
      var track = el('div', 'bar-track'), fill = el('div', 'bar-fill');
      fill.style.width = Math.max(2, 100 * d.n / max) + '%';
      if (byPartner) fill.style.background = d.label.indexOf('Ilo') === 0 ? 'var(--ilo)' : 'var(--ever)';
      track.append(fill); row.append(track); box.append(row);
    });
  }

  function daily(cur, range, now) {
    var box = $('daily');
    box.replaceChildren();
    var today = dayOf(now);
    var start = range === 'all'
      ? (cur.length ? dayOf(Math.min.apply(null, cur.map(function (r) { return r.ts; }))) : dayOf(now - 6 * DAY))
      : dayOf(now - (Number(range) - 1) * DAY);
    var daysList = [];
    for (var d = new Date(start + 'T12:00:00Z'); daysList.length < 2000; d = new Date(d.getTime() + DAY)) {
      var key = d.toISOString().slice(0, 10); daysList.push(key); if (key >= today) break;
    }
    var counts = {};
    cur.forEach(function (r) { var k = dayOf(r.ts) + '|' + r.partner; counts[k] = (counts[k] || 0) + 1; });
    var series = PARTNERS.map(function (p) { return daysList.map(function (k) { return counts[k + '|' + p.key] || 0; }); });
    var maxY = Math.max(3, Math.max.apply(null, series[0].concat(series[1])));
    var step = maxY <= 5 ? 1 : Math.ceil(maxY / 4);
    var top = Math.ceil(maxY / step) * step;
    var W = Math.max(300, box.clientWidth || 700), H = 220, m = {t: 10, r: 12, b: 26, l: 30};
    var x = function (i) { return m.l + (daysList.length < 2 ? 0 : i * (W - m.l - m.r) / (daysList.length - 1)); };
    var y = function (v) { return H - m.b - v * (H - m.t - m.b) / top; };
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Clicks per day by partner');
    function add(tag, attrs, text) { var n = document.createElementNS(NS, tag); for (var k in attrs) n.setAttribute(k, attrs[k]); if (text !== undefined) n.textContent = text; svg.appendChild(n); return n; }
    for (var v = 0; v <= top; v += step) {
      add('line', {x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: 'var(--grid)'});
      add('text', {x: m.l - 6, y: y(v), 'text-anchor': 'end', 'dominant-baseline': 'middle'}, String(v));
    }
    var nTicks = Math.max(2, Math.min(daysList.length, Math.floor((W - m.l - m.r) / 80)));
    var fmt = new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'short', timeZone: 'UTC'});
    for (var t = 0; t < nTicks; t++) {
      var idx = Math.round(t * (daysList.length - 1) / Math.max(1, nTicks - 1));
      add('text', {x: x(idx), y: H - 6, 'text-anchor': t === 0 ? 'start' : (t === nTicks - 1 ? 'end' : 'middle')}, fmt.format(new Date(daysList[idx] + 'T12:00:00Z')));
    }
    series.forEach(function (s, si) {
      add('polyline', {fill: 'none', stroke: PARTNERS[si].color, 'stroke-width': 2, 'stroke-linejoin': 'round',
        points: s.map(function (v, i) { return x(i) + ',' + y(v); }).join(' ')});
      if (daysList.length <= 31) s.forEach(function (v, i) { if (v) add('circle', {cx: x(i), cy: y(v), r: 3, fill: PARTNERS[si].color}); });
    });
    var guide = add('line', {y1: m.t, y2: H - m.b, stroke: 'var(--muted)', 'stroke-dasharray': '2 3', opacity: 0});
    var hit = add('rect', {x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent'});
    box.append(svg);
    var tip = el('div', 'tip'); tip.hidden = true; box.append(tip);
    var long = new Intl.DateTimeFormat('en-GB', {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
    function move(ev) {
      var r = svg.getBoundingClientRect();
      var px = (ev.clientX - r.left) * W / r.width;
      var i = Math.round((px - m.l) / ((W - m.l - m.r) / Math.max(1, daysList.length - 1)));
      i = Math.max(0, Math.min(daysList.length - 1, i));
      guide.setAttribute('x1', x(i)); guide.setAttribute('x2', x(i)); guide.setAttribute('opacity', 1);
      tip.replaceChildren(el('b', '', long.format(new Date(daysList[i] + 'T12:00:00Z'))));
      PARTNERS.forEach(function (p, si) { tip.append(el('div', '', p.short + ': ' + series[si][i])); });
      tip.hidden = false;
      var left = x(i) * r.width / W + 10;
      tip.style.left = Math.min(left, box.clientWidth - tip.offsetWidth - 4) + 'px';
    }
    hit.addEventListener('pointermove', move);
    hit.addEventListener('pointerleave', function () { tip.hidden = true; guide.setAttribute('opacity', 0); });
  }

  function recent(cur) {
    var tb = $('recent');
    tb.replaceChildren();
    var list = cur.slice().sort(function (a, b) { return b.ts - a.ts; }).slice(0, 25);
    $('recent-empty').hidden = list.length > 0;
    var fmt = new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/London', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});
    list.forEach(function (r) {
      var tr = el('tr');
      [fmt.format(new Date(r.ts)), PNAME[r.partner] ? PNAME[r.partner].name : r.partner, LINKS[r.linkType] || r.linkType,
        r.placement || '', sourceOf(r), DEVICES[r.device] || r.device || ''].forEach(function (c) { tr.append(el('td', '', c)); });
      tb.append(tr);
    });
  }

  var LAYOUT =
    '<main class="pc">' +
    '<header class="pc-top"><div><p class="pc-eyebrow">Life on Walls · Partners</p><h1>Partner Clicks</h1><p class="pc-lede" id="lede">Loading…</p></div>' +
    '<div class="pc-controls"><label for="range" class="sub" style="margin:0">Period</label><select id="range">' +
    '<option value="7">Last 7 days</option><option value="30" selected>Last 30 days</option><option value="90">Last 90 days</option><option value="365">Last 12 months</option><option value="all">All time</option>' +
    '</select><button type="button" id="reload">Refresh</button></div></header>' +
    '<section class="pc-tiles" aria-label="Totals">' +
    '<div class="card"><div class="tile-label">Clicks to partner sites</div><div class="big" id="k-total">—</div><div class="delta" id="k-total-d"></div></div>' +
    '<div class="card"><div class="tile-label"><i class="sw" id="sw-ever"></i>Evergreen Exterior Services</div><div class="big" id="k-ever">—</div><div class="delta" id="k-ever-d"></div></div>' +
    '<div class="card"><div class="tile-label"><i class="sw" id="sw-ilo"></i>Ilo Bloom</div><div class="big" id="k-ilo">—</div><div class="delta" id="k-ilo-d"></div></div>' +
    '<div class="card"><div class="tile-label">Visitors who clicked</div><div class="big" id="k-vis">—</div><div class="delta">Browser sessions with at least one partner click</div></div>' +
    '</section>' +
    '<section class="card"><h2>Clicks per day</h2><p class="sub">Outbound clicks from the Partners pages, by partner</p>' +
    '<div class="legend"><span><i class="sw" id="lg-ever"></i>Evergreen Exterior Services</span><span><i class="sw" id="lg-ilo"></i>Ilo Bloom</span></div>' +
    '<div class="chart" id="daily"></div></section>' +
    '<div class="grid2">' +
    '<section class="card"><h2>Which links get clicked</h2><p class="sub">Website, online shop, Instagram and directions links</p><div class="bars" id="b-link"></div></section>' +
    '<section class="card"><h2>Where on the page</h2><p class="sub">The page section the link was clicked from</p><div class="bars" id="b-place"></div></section>' +
    '<section class="card"><h2>Where clickers came from</h2><p class="sub">Campaign source if the visit had UTM tags, otherwise the referring site</p><div class="bars" id="b-source"></div></section>' +
    '<section class="card"><h2>Device</h2><p class="sub">Mobile under 700px wide, tablet under 1000px, desktop above</p><div class="bars" id="b-device"></div></section>' +
    '</div>' +
    '<section class="card"><h2>Latest clicks</h2><p class="sub">The 25 most recent clicks in the period</p><div class="tablewrap"><table>' +
    '<thead><tr><th>When (UK time)</th><th>Partner</th><th>Link</th><th>Page section</th><th>Came from</th><th>Device</th></tr></thead><tbody id="recent"></tbody></table></div>' +
    '<p class="empty" id="recent-empty" hidden>No clicks in this period yet.</p></section>' +
    '<footer class="foot"><p id="updated"></p><details><summary>How clicks are counted</summary><p>A click is counted when a visitor clicks a partner’s website, online shop, Instagram or directions link on lifeonwalls.co.uk/partners. Clicks from bots and from other websites are rejected, and setup test clicks are left out. “Visitors who clicked” counts browser sessions, so one person on two visits counts twice. Changes compare with the period of the same length just before.</p></details></footer>' +
    '</main>';

  function init() {
    var root = document.getElementById('app') || document.body;
    root.innerHTML = LAYOUT;
    $('sw-ever').style.background = PARTNERS[0].color;
    $('sw-ilo').style.background = PARTNERS[1].color;
    $('lg-ever').style.background = PARTNERS[0].color;
    $('lg-ilo').style.background = PARTNERS[1].color;
    if (DATA.generatedAt) {
      $('updated').textContent = 'Data as of ' + new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/London', dateStyle: 'medium', timeStyle: 'short'}).format(new Date(DATA.generatedAt)) + ' (UK time).';
    }
    $('range').addEventListener('change', render);
    $('reload').addEventListener('click', function () { location.reload(); });
    var t;
    window.addEventListener('resize', function () { clearTimeout(t); t = setTimeout(render, 150); });
    render();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
