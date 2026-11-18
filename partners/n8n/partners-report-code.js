const DASH = 'https://n8n.lifeonwalls.co.uk/webhook/partner-dashboard/<private-token>'; // real token is set in the n8n workflow only
const PARTNERS = {'evergreen-exterior-services': 'Evergreen Exterior Services', 'ilo-bloom': 'Ilo Bloom'};
const LINKS = {website: 'Website', shop: 'Online shop', instagram: 'Instagram', directions: 'Directions', other: 'Other'};

const all = $input.all().map(function (i) { return i.json; }).filter(function (c) {
  if (!c || !c.partner) return false;
  const isTest = c.placement === 'test' || String(c.sessionId || '').indexOf('test-') === 0 || c.utmSource === 'setup-test';
  return !isTest;
});

const DAY = 86400000;
const end = Date.now();
const start = end - 7 * DAY;
const prevStart = start - 7 * DAY;
const t = function (c) { return Date.parse(c.clickedAt || c.createdAt); };
const week = all.filter(function (c) { return t(c) > start && t(c) <= end; });
const prev = all.filter(function (c) { return t(c) > prevStart && t(c) <= start; });

const count = function (list, key) {
  const m = {};
  list.forEach(function (c) { const k = key(c); m[k] = (m[k] || 0) + 1; });
  return Object.keys(m).map(function (k) { return [k, m[k]]; }).sort(function (a, b) { return b[1] - a[1]; });
};
const esc = function (s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
const signed = function (d) { return d > 0 ? '+' + d : (d < 0 ? '−' + Math.abs(d) : '±0'); };
const colour = function (d) { return d > 0 ? '#3F7A1E' : (d < 0 ? '#B3261E' : '#5A6055'); };
const dateFmt = new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/London', day: 'numeric', month: 'short', year: 'numeric'});
const periodLabel = dateFmt.format(new Date(start + 1000)) + ' – ' + dateFmt.format(new Date(end));

const visitors = new Set(week.map(function (c) { return c.sessionId; }).filter(Boolean)).size;
const byPartner = Object.keys(PARTNERS).map(function (p) {
  const now = week.filter(function (c) { return c.partner === p; }).length;
  const before = prev.filter(function (c) { return c.partner === p; }).length;
  return {name: PARTNERS[p], now: now, before: before, allTime: all.filter(function (c) { return c.partner === p; }).length};
});

const row = function (cells, head) {
  const tag = head ? 'th' : 'td';
  const style = head
    ? 'text-align:left;padding:8px 10px;border-bottom:1px solid #D9E3C2;font-size:12px;color:#5A6055;font-weight:600'
    : 'padding:8px 10px;border-bottom:1px solid #EDF1E3;font-size:14px;color:#12160F';
  return '<tr>' + cells.map(function (c, i) {
    return '<' + tag + ' style="' + style + (i > 0 ? ';text-align:right' : '') + '">' + c + '</' + tag + '>';
  }).join('') + '</tr>';
};
const table = function (head, rows) {
  return '<table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;margin:0 0 24px">' + row(head, true) + rows.join('') + '</table>';
};
const section = function (title) { return '<h2 style="font-size:16px;font-weight:600;color:#12160F;margin:28px 0 8px">' + title + '</h2>'; };
const list = function (pairs) {
  if (!pairs.length) return '<p style="font-size:14px;color:#5A6055;margin:0 0 16px">No clicks this week.</p>';
  return table(['', 'Clicks'], pairs.slice(0, 8).map(function (p) { return row([esc(p[0]), String(p[1])]); }));
};

const totalDiff = week.length - prev.length;
let headline;
if (week.length === 0) {
  headline = 'No one clicked through to a partner site this week.';
} else {
  const lead = byPartner.slice().sort(function (a, b) { return b.now - a.now; })[0];
  headline = week.length + (week.length === 1 ? ' click' : ' clicks') + ' to partner sites from ' + visitors + (visitors === 1 ? ' visitor' : ' visitors') +
    (byPartner[0].now === byPartner[1].now ? ', split evenly between the two partners.' : '. ' + lead.name + ' received ' + Math.round(100 * lead.now / week.length) + '% of them.');
}

let html = '<div style="font-family:Arial,Helvetica,sans-serif;max-width:620px;margin:0 auto;padding:24px;color:#12160F;background:#FFFFFF">';
html += '<p style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#3F4E0A;margin:0 0 6px">Life on Walls · Weekly partner report</p>';
html += '<h1 style="font-size:24px;font-weight:400;margin:0 0 6px">Partner clicks</h1>';
html += '<p style="font-size:13px;color:#5A6055;margin:0 0 18px">' + periodLabel + '</p>';
html += '<p style="font-size:16px;line-height:1.5;margin:0 0 20px">' + esc(headline) + '</p>';
html += '<table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;margin:0 0 8px"><tr>';
[['Total clicks', week.length, totalDiff]].concat(byPartner.map(function (p) { return [p.name, p.now, p.now - p.before]; })).forEach(function (k) {
  html += '<td style="background:#EDF1E3;padding:14px;border:4px solid #FFFFFF;vertical-align:top;width:33%">' +
    '<div style="font-size:12px;color:#5A6055">' + esc(k[0]) + '</div>' +
    '<div style="font-size:28px;margin:4px 0">' + k[1] + '</div>' +
    '<div style="font-size:12px;color:' + colour(k[2]) + '">' + signed(k[2]) + ' vs previous week</div></td>';
});
html += '</tr></table>';

html += section('Which links were clicked');
html += list(count(week, function (c) { return (PARTNERS[c.partner] || c.partner) + ' · ' + (LINKS[c.linkType] || c.linkType); }));
html += section('Where on the page');
html += list(count(week, function (c) { return c.placement || 'Unknown'; }));
html += section('Where clickers came from');
html += list(count(week, function (c) {
  if (c.utmSource) return c.utmSource + (c.utmMedium ? ' / ' + c.utmMedium : '');
  return c.referrer === 'internal' ? 'lifeonwalls.co.uk (internal)' : (c.referrer || 'direct');
}));
html += section('Device');
html += list(count(week, function (c) { return ({mobile: 'Mobile', tablet: 'Tablet', desktop: 'Desktop'})[c.device] || 'Unknown'; }));
html += section('All time');
html += table(['Partner', 'Clicks'], byPartner.map(function (p) { return row([esc(p.name), String(p.allTime)]); }));

html += '<p style="margin:28px 0 8px"><a href="' + DASH + '" style="display:inline-block;background:#9BB222;color:#0B0F0B;text-decoration:none;padding:12px 22px;border-radius:999px;font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase">Open the dashboard</a></p>';
html += '<p style="font-size:12px;color:#5A6055;line-height:1.5;margin:18px 0 0">Counts clicks on partner website, shop, Instagram and directions links on lifeonwalls.co.uk/partners. Bot traffic and test clicks are excluded. "Visitors" counts browser sessions. Sent every Monday by the n8n workflow partners.report.</p>';
html += '</div>';

const subject = 'Partner clicks this week: ' + week.length + ' (' + signed(totalDiff) + ' vs last week)';
return [{json: {subject: subject, html: html, clicksThisWeek: week.length, clicksLastWeek: prev.length}}];
