// Reader page: aligned cuneiform / translation grid with a sign inspector.

const params = new URLSearchParams(location.search);
const slug = params.get('text') || 'dumuzids-dream';

const $ = (sel) => document.querySelector(sel);
const grid = $('#text');
const inspector = $('#inspector');

const state = {
  data: null,
  chunkOfLine: new Map(),
  rowOfLine: new Map(),
  lineById: new Map(),
  pinned: null,       // pinned .sg element
  allSigns: [],       // document-order list of .sg elements (for keyboard navigation)
};

function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function signText(s) {
  if (s.u) return s.u;
  if (s.k === 'gap') return '…';
  if (s.k === 'x') return '';
  return s.v;
}

function readingLabel(s) {
  let v = s.v;
  if (s.k === 'x') v = 'x';
  if (s.det) v = '{' + v + '}';
  if (s.q) v += s.q;
  return v;
}

function signEl(s, lineId, wi, si) {
  const e = h('span', 'sg');
  e.dataset.line = lineId;
  e.dataset.w = wi;
  e.dataset.s = si;
  if (s.det) e.classList.add('det');
  if (s.dmg === 'r') e.classList.add('dmg-r');
  if (s.dmg === 'd') e.classList.add('dmg-d');
  if (s.k) e.classList.add('k-' + s.k);
  if (s.ins) e.classList.add('ins');
  if (s.extra) e.classList.add('extra');
  const rd = h('span', 'rd', readingLabel(s));
  const gl = h('span', 'gl', signText(s));
  if (!s.u && !s.k) gl.classList.add('nogl');
  e.append(rd, gl);
  return e;
}

function render(data) {
  data.chunks.forEach((c, ci) => c.lines.forEach((id) => state.chunkOfLine.set(id, ci)));
  data.lines.forEach((ln, i) => { state.rowOfLine.set(ln.id, i + 1); state.lineById.set(ln.id, ln); });

  const frag = document.createDocumentFragment();
  data.lines.forEach((ln, i) => {
    const row = i + 1;
    const ci = state.chunkOfLine.get(ln.id);

    const num = h('div', 'ln', ln.label);
    num.style.gridRow = row;
    num.dataset.line = ln.id;
    num.dataset.chunk = ci;
    num.id = 'L' + ln.id;
    num.title = 'Line ' + ln.label + ' (click to link here)';

    const cu = h('div', 'cu');
    cu.style.gridRow = row;
    cu.dataset.line = ln.id;
    cu.dataset.chunk = ci;
    if (ln.indent) cu.classList.add('indent');

    ln.words.forEach((w, wi) => {
      const ws = h('span', 'w');
      ws.dataset.w = wi;
      if (w.proper) ws.classList.add('proper');
      w.signs.forEach((s, si) => ws.appendChild(signEl(s, ln.id, wi, si)));
      cu.appendChild(ws);
      cu.appendChild(document.createTextNode(' '));
    });
    if (ln.variants || ln.notes) {
      const m = h('span', 'mark', ln.variants ? 'var.' : 'note');
      m.title = (ln.variants || []).map((v) => v.note + ' ' + v.t).concat(ln.notes || []).join('\n');
      cu.appendChild(m);
    }
    cu.appendChild(h('div', 'tl', ln.words.map((w) => w.t).join(' ')));

    frag.append(num, cu);
  });

  data.chunks.forEach((c, ci) => {
    const rows = c.lines.map((id) => state.rowOfLine.get(id)).filter((r) => r != null);
    const start = Math.min(...rows);
    const end = Math.max(...rows);
    const en = h('div', 'en');
    en.style.gridRow = start + ' / ' + (end + 1);
    en.dataset.chunk = ci;
    en.dataset.start = start;
    en.dataset.end = end;
    if (c.fallback) en.classList.add('fallback');
    const first = state.lineById.get(c.lines[0]).label;
    const last = state.lineById.get(c.lines[c.lines.length - 1]).label;
    en.appendChild(h('span', 'en-lines', c.lines.length > 1 ? first + '–' + last : first));
    en.appendChild(h('p', null, c.text));
    frag.appendChild(en);
  });

  grid.innerHTML = '';
  grid.appendChild(frag);
  state.allSigns = Array.from(grid.querySelectorAll('.sg'));
}

// ---------------------------------------------------------------------------
// Highlighting
// ---------------------------------------------------------------------------

function clearHighlights() {
  grid.querySelectorAll('.is-line, .in-chunk, .is-chunk, .sg.hover, .w.hover').forEach((e) => {
    e.classList.remove('is-line', 'in-chunk', 'is-chunk', 'hover');
  });
}

function highlightChunk(ci) {
  if (ci == null) return;
  grid.querySelectorAll('.en[data-chunk="' + ci + '"]').forEach((e) => e.classList.add('is-chunk'));
  grid.querySelectorAll('.ln[data-chunk="' + ci + '"], .cu[data-chunk="' + ci + '"]').forEach((e) => e.classList.add('in-chunk'));
}

function highlightLine(lineId) {
  grid.querySelectorAll('.ln[data-line="' + CSS.escape(lineId) + '"], .cu[data-line="' + CSS.escape(lineId) + '"]')
    .forEach((e) => e.classList.add('is-line'));
  highlightChunk(state.chunkOfLine.get(lineId));
}

function focusSign(sg) {
  clearHighlights();
  sg.classList.add('hover');
  const w = sg.closest('.w');
  if (w) w.classList.add('hover');
  highlightLine(sg.dataset.line);
  showSign(sg);
}

function focusLine(lineId) {
  clearHighlights();
  highlightLine(lineId);
  showLine(lineId);
}

function focusChunk(ci) {
  clearHighlights();
  highlightChunk(ci);
  showChunk(ci);
}

function restoreFocus() {
  if (state.pinned) focusSign(state.pinned);
  else { clearHighlights(); showIdle(); }
}

// ---------------------------------------------------------------------------
// Inspector
// ---------------------------------------------------------------------------

function kv(pairs) {
  const dl = h('dl', 'kv');
  for (const [k, v] of pairs) {
    if (v == null || v === '') continue;
    dl.appendChild(h('dt', null, k));
    const dd = h('dd');
    if (v instanceof Node) dd.appendChild(v); else dd.textContent = v;
    dl.appendChild(dd);
  }
  return dl;
}

function signFlags(s) {
  const flags = [];
  if (s.det) flags.push('determinative (unpronounced classifier)');
  if (s.dmg === 'r') flags.push('restored — broken on every manuscript, supplied by the editors');
  if (s.dmg === 'd') flags.push('partly damaged on the tablet');
  if (s.ins) flags.push('omitted by the scribe, added by the editors');
  if (s.extra) flags.push('superfluous sign written by the scribe');
  if (s.q === '?') flags.push('reading uncertain');
  if (s.q === '!') flags.push('sign emended by the editors');
  if (s.k === 'x') flags.push('illegible sign');
  if (s.k === 'gap') flags.push('gap of unknown length');
  if (s.k === 'num') flags.push('numeral');
  if (s.grp) flags.push('part of the compound read ' + s.grp);
  return flags;
}

function wordSection(w) {
  const box = h('div');
  box.appendChild(h('h3', null, 'Word'));
  const wd = h('div', 'insp-word');
  wd.appendChild(h('span', 'lemma', w.t));
  box.appendChild(wd);
  if (w.lemma || w.gloss) {
    const g = h('div', 'insp-gloss');
    g.appendChild(h('span', 'lemma', w.lemma));
    if (w.pos) g.appendChild(h('span', 'pos', ' (' + w.pos + ') '));
    g.appendChild(document.createTextNode((w.pos ? '' : ' ') + w.gloss));
    box.appendChild(g);
  }
  if (w.q) box.appendChild(h('p', 'insp-note', 'Translation of this word is uncertain (?).'));
  return box;
}

function lineSection(ln) {
  const box = h('div');
  box.appendChild(h('h3', null, 'Line ' + ln.label));
  const ci = state.chunkOfLine.get(ln.id);
  const chunk = state.data.chunks[ci];
  if (chunk) {
    const t = h('p', 'insp-line-text', chunk.text);
    box.appendChild(t);
    if (chunk.lines.length > 1) {
      const a = state.lineById.get(chunk.lines[0]).label;
      const b = state.lineById.get(chunk.lines[chunk.lines.length - 1]).label;
      box.appendChild(h('p', 'insp-note', 'Translation covers lines ' + a + '–' + b + '.'));
    }
  }
  (ln.notes || []).forEach((n) => box.appendChild(h('p', 'insp-note', n)));
  (ln.variants || []).forEach((v) => {
    const d = h('div', 'insp-var');
    const label = v.note + (v.replaces ? ' (for “' + v.replaces + '”)' : '');
    d.appendChild(h('div', 'vnote', label));
    d.appendChild(h('span', 'cu-text', v.words.map((w) => w.signs.map(signText).join('')).join(' ')));
    d.appendChild(h('div', 'insp-sub', v.t));
    (v.notes || []).forEach((n) => d.appendChild(h('div', 'insp-note', n)));
    box.appendChild(d);
  });
  const link = h('a', null, 'ETCSL line ' + ln.label + ' ↗');
  link.href = state.data.source.transliteration + '&lineid=c' + state.data.source.etcsl.replace(/\./g, '') + '.' + ln.id;
  link.target = '_blank';
  link.rel = 'noopener';
  const p = h('p', 'insp-note');
  p.appendChild(link);
  box.appendChild(p);
  return box;
}

function showSign(sg) {
  const ln = state.lineById.get(sg.dataset.line);
  const w = ln.words[+sg.dataset.w];
  const s = w.signs[+sg.dataset.s];
  const info = s.n ? state.data.signs[s.n] : null;

  inspector.innerHTML = '';
  inspector.appendChild(h('h3', null, 'Sign'));
  const g = h('div', 'insp-glyph', signText(s) || '▯');
  if (s.det) g.classList.add('det');
  inspector.appendChild(g);
  inspector.appendChild(h('div', 'insp-reading', readingLabel(s)));

  const pairs = [];
  if (s.n) pairs.push(['Sign name', s.n]);
  if (info && info.uname) pairs.push(['Unicode', info.uname + (s.u ? ' (' + Array.from(s.u).map((c) => 'U+' + c.codePointAt(0).toString(16).toUpperCase()).join(' ') + ')' : '')]);
  if (!s.n && !s.k) pairs.push(['Sign name', 'not found in the sign list']);
  inspector.appendChild(kv(pairs));

  if (info && info.values && info.values.length > 1) {
    inspector.appendChild(h('h3', null, 'Other readings of this sign'));
    const chips = h('div', 'chips');
    info.values.filter((v) => v !== s.v && v !== s.v.replace(/ĝ/g, 'ŋ').replace(/ḫ/g, 'h')).slice(0, 12)
      .forEach((v) => chips.appendChild(h('span', 'chip', v)));
    inspector.appendChild(chips);
  }
  const flags = signFlags(s);
  if (flags.length) {
    const chips = h('div', 'chips');
    flags.forEach((f) => chips.appendChild(h('span', 'chip flag', f)));
    inspector.appendChild(chips);
  }

  inspector.appendChild(wordSection(w));
  inspector.appendChild(lineSection(ln));
  if (state.pinned === sg) {
    inspector.appendChild(keysHelp());
  }
}

function showLine(lineId) {
  const ln = state.lineById.get(lineId);
  inspector.innerHTML = '';
  inspector.appendChild(lineSection(ln));
  inspector.appendChild(h('p', 'insp-note', 'Hover a sign for its reading and meaning.'));
}

function showChunk(ci) {
  const chunk = state.data.chunks[ci];
  inspector.innerHTML = '';
  const a = state.lineById.get(chunk.lines[0]).label;
  const b = state.lineById.get(chunk.lines[chunk.lines.length - 1]).label;
  inspector.appendChild(h('h3', null, chunk.lines.length > 1 ? 'Lines ' + a + '–' + b : 'Line ' + a));
  inspector.appendChild(h('p', 'insp-line-text', chunk.text));
  const tl = h('p', 'insp-note');
  tl.textContent = chunk.lines.map((id) => state.lineById.get(id).words.map((w) => w.t).join(' ')).join(' / ');
  inspector.appendChild(tl);
}

function keysHelp() {
  const p = h('p', 'insp-note');
  p.innerHTML = 'Pinned. <span class="kbd">←</span> <span class="kbd">→</span> next sign, '
    + '<span class="kbd">↑</span> <span class="kbd">↓</span> next line, <span class="kbd">Esc</span> unpin.';
  return p;
}

function showIdle() {
  inspector.innerHTML = '';
}

function renderSources(d) {
  const f = $('#sources');
  f.innerHTML = '';
  const p1 = h('p');
  p1.append('Sumerian text and translation: ');
  const a1 = h('a', null, 'ETCSL c.' + d.source.etcsl);
  a1.href = d.source.transliteration; a1.target = '_blank'; a1.rel = 'noopener';
  const a2 = h('a', null, 't.' + d.source.etcsl);
  a2.href = d.source.translation; a2.target = '_blank'; a2.rel = 'noopener';
  p1.append(a1, ' and ', a2, ', The Electronic Text Corpus of Sumerian Literature, University of Oxford (© ETCSL project, non-commercial use). ');
  p1.append(d.source.alignment === 'per-line'
    ? 'The paragraph translation was divided line by line without changing its wording. '
    : 'The translation is shown by ETCSL paragraph. ');
  p1.append('The Sumerian is ETCSL\'s composite text, reconstructed from many Old Babylonian manuscripts.');
  const p2 = h('p');
  p2.append('Sign readings and Unicode mapping: ');
  const a3 = h('a', null, 'ORACC Global Sign List');
  a3.href = 'https://oracc.museum.upenn.edu/osl/'; a3.target = '_blank'; a3.rel = 'noopener';
  p2.append(a3, ' (CC BY-SA). Glyphs: Noto Sans Cuneiform. ', d.stats.lines + ' lines, ' + d.stats.signs + ' signs, ' + d.stats.distinct_signs + ' distinct signs.');
  f.append(p1, p2);
}

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

function pin(sg) {
  if (state.pinned) state.pinned.classList.remove('pinned');
  state.pinned = sg;
  sg.classList.add('pinned');
  focusSign(sg);
}

function unpin() {
  if (!state.pinned) return;
  state.pinned.classList.remove('pinned');
  state.pinned = null;
  restoreFocus();
}

function moveSign(delta) {
  if (!state.pinned) return;
  const i = state.allSigns.indexOf(state.pinned);
  const j = Math.min(state.allSigns.length - 1, Math.max(0, i + delta));
  const next = state.allSigns[j];
  pin(next);
  next.scrollIntoView({ block: 'nearest' });
}

function moveLine(delta) {
  if (!state.pinned) return;
  const ids = state.data.lines.map((l) => l.id);
  const i = ids.indexOf(state.pinned.dataset.line);
  const j = Math.min(ids.length - 1, Math.max(0, i + delta));
  if (j === i) return;
  const first = grid.querySelector('.cu[data-line="' + CSS.escape(ids[j]) + '"] .sg');
  if (first) { pin(first); first.scrollIntoView({ block: 'nearest' }); }
}

function wire() {
  grid.addEventListener('mouseover', (e) => {
    const sg = e.target.closest('.sg');
    if (sg) { focusSign(sg); return; }
    const en = e.target.closest('.en');
    if (en) { focusChunk(+en.dataset.chunk); return; }
    const cell = e.target.closest('[data-line]');
    if (cell) { focusLine(cell.dataset.line); return; }
  });
  grid.addEventListener('mouseleave', restoreFocus);

  grid.addEventListener('click', (e) => {
    const sg = e.target.closest('.sg');
    if (sg) { if (state.pinned === sg) unpin(); else pin(sg); return; }
    const ln = e.target.closest('.ln');
    if (ln) { history.replaceState(null, '', '#L' + ln.dataset.line); return; }
    unpin();
  });

  document.addEventListener('keydown', (e) => {
    if (e.target && e.target.matches && e.target.matches('input, textarea')) return;
    if (e.key === 'Escape') { unpin(); return; }
    if (!state.pinned) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); moveSign(1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); moveSign(-1); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); moveLine(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); moveLine(-1); }
  });

  // Preferences
  const prefs = loadPrefs();
  const readings = $('#opt-readings');
  const translit = $('#opt-translit');
  const size = $('#opt-size');
  readings.checked = !!prefs.readings;
  translit.checked = !!prefs.translit;
  size.value = prefs.size || 26;
  applyPrefs();
  readings.addEventListener('change', applyPrefs);
  translit.addEventListener('change', applyPrefs);
  size.addEventListener('input', applyPrefs);

  function applyPrefs() {
    document.body.classList.toggle('readings', readings.checked);
    document.body.classList.toggle('translit', translit.checked);
    document.documentElement.style.setProperty('--cu-size', size.value + 'px');
    savePrefs({ readings: readings.checked, translit: translit.checked, size: +size.value });
  }

  // Narrow screens: English can't share grid rows with the cuneiform, so place each
  // chunk after its last line instead of spanning.
  const mq = window.matchMedia('(max-width: 980px)');
  const relayout = () => {
    document.body.classList.toggle('stacked', mq.matches);
    grid.querySelectorAll('.en').forEach((en) => {
      en.style.gridRow = mq.matches ? '' : en.dataset.start + ' / ' + (+en.dataset.end + 1);
    });
    if (mq.matches) stackRows(); else unstackRows();
  };
  mq.addEventListener('change', relayout);
  relayout();
}

// On narrow screens we rely on DOM order: move each .en right after the .cu of its last line.
function stackRows() {
  grid.querySelectorAll('.en').forEach((en) => {
    const lastRow = +en.dataset.end;
    const cu = grid.querySelector('.cu[style*="grid-row: ' + lastRow + ';"]') || grid.querySelectorAll('.cu')[lastRow - 1];
    if (cu && cu.nextSibling !== en) cu.after(en);
    en.style.gridRow = '';
  });
  grid.querySelectorAll('.ln, .cu').forEach((e) => { e.style.gridRow = ''; });
}

function unstackRows() {
  const ens = Array.from(grid.querySelectorAll('.en'));
  ens.forEach((en) => grid.appendChild(en));
  grid.querySelectorAll('.ln, .cu').forEach((e) => {
    e.style.gridRow = state.rowOfLine.get(e.dataset.line);
  });
}

function loadPrefs() {
  try { return JSON.parse(localStorage.getItem('cuneiform-reader-prefs') || '{}'); } catch (e) { return {}; }
}

function savePrefs(p) {
  try { localStorage.setItem('cuneiform-reader-prefs', JSON.stringify(p)); } catch (e) { /* ignore */ }
}

function scrollToHash() {
  const m = /^#L(.+)$/.exec(location.hash);
  if (!m) return;
  const id = decodeURIComponent(m[1]);
  const cells = grid.querySelectorAll('[data-line="' + CSS.escape(id) + '"]');
  if (!cells.length) return;
  cells[0].scrollIntoView({ block: 'center' });
  cells.forEach((c) => c.classList.add('flash'));
}

// ---------------------------------------------------------------------------

async function main() {
  let data;
  try {
    const res = await fetch('data/texts/' + encodeURIComponent(slug) + '.json');
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    data = await res.json();
  } catch (err) {
    grid.innerHTML = '';
    grid.appendChild(h('p', 'error', 'Could not load text “' + slug + '” (' + err.message + '). '
      + 'Serve the folder over HTTP (scripts/serve.sh) rather than opening the file directly.'));
    return;
  }
  state.data = data;
  document.title = data.title + ' · Cuneiform Reader';
  $('#title').textContent = data.title;
  $('#meta').textContent = 'ETCSL ' + data.source.etcsl + ' · ' + data.stats.lines + ' lines';
  render(data);
  renderSources(data);
  wire();
  showIdle();
  if (location.hash) scrollToHash();
}

main();
