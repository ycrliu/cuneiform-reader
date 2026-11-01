// Library page: list every text in data/library.json.

const grid = document.getElementById('library');

function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

async function main() {
  let lib;
  try {
    const res = await fetch('data/library.json');
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    lib = await res.json();
  } catch (err) {
    grid.innerHTML = '';
    const e = h('p', 'error', 'Could not load data/library.json (' + err.message + '). '
      + 'Serve the folder over HTTP, e.g. scripts/serve.sh, rather than opening the file directly.');
    grid.appendChild(e);
    return;
  }
  grid.innerHTML = '';
  for (const t of lib.texts) {
    const a = h('a', 'card');
    a.href = 'read.html?text=' + encodeURIComponent(t.slug);
    a.appendChild(h('div', 'card-cu', t.incipit || ''));
    a.appendChild(h('h2', null, t.title));
    if (t.incipit_translit) a.appendChild(h('p', 'card-tr', t.incipit_translit));
    if (t.period) a.appendChild(h('p', 'card-meta', t.period));
    grid.appendChild(a);
  }
}

main();
