#!/usr/bin/env python3
"""Build a reader text (data/texts/<slug>.json) from an ETCSL composition.

    scripts/build_text.py <slug> <etcsl-number> [--title "Dumuzid's dream"]

Inputs (fetch them with scripts/fetch_sources.sh <etcsl-number>):
    data/sources/etcsl/c.<num>.html   ETCSL composite transliteration, with per-word glosses
    data/sources/etcsl/t.<num>.html   ETCSL translation (paragraphs keyed to line ranges)
    data/sources/osl/osl.asl          ORACC/OSL sign list source (reading -> sign -> Unicode)
    data/sources/osl/ogsl-sl.json     older published OGSL JSON, used as a fallback
Optional:
    data/alignments/<slug>.json       hand-made per-line segmentation of the ETCSL translation

ETCSL transliterations are composite texts: every hyphen-separated element is one
sign, so a reading like "šag₄" can be turned into the sign ŠA₃ (𒊮) through the OSL
value index. ETCSL spells ŋ as ĝ and ḫ with a dot; OSL spells them ŋ and h.
"""
import argparse
import collections
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUB = str.maketrans("0123456789x", "₀₁₂₃₄₅₆₇₈₉ₓ")

# ----------------------------------------------------------------------------
# Sign list
# ----------------------------------------------------------------------------


class SignList:
    """reading -> sign name -> glyph, built from osl.asl with ogsl-sl.json as fallback."""

    def __init__(self, asl_path, json_path):
        self.signs = {}  # name -> {"u": glyph|None, "uname": str|None, "values": [...]}
        self.index = {}  # value -> name
        self._load_asl(asl_path)
        self._load_json(json_path)

    def _load_asl(self, path):
        txt = path.read_text(encoding="utf-8")
        for name, body in re.findall(r"^@sign\s+(\S+)\n(.*?)^@end sign", txt, flags=re.S | re.M):
            top = re.split(r"^@form\b", body, flags=re.M)[0]  # ignore @form variants
            uc = re.search(r"^@ucun\s+(\S+)", top, flags=re.M)
            un = re.search(r"^@uname\s+(.+)$", top, flags=re.M)
            values = [re.sub(r"[?\[\]]", "", v) for v in re.findall(r"^@v\s+(\S+)", top, flags=re.M)]
            self.signs[name] = {"u": uc.group(1) if uc else None,
                                "uname": un.group(1).strip() if un else None,
                                "values": values}
            for v in values:
                # Prefer a sign that actually has a glyph when a value is listed twice.
                if v not in self.index or (not self.signs[self.index[v]]["u"] and uc):
                    self.index[v] = name

    def _load_json(self, path):
        if not path.exists():
            return
        d = json.loads(path.read_text(encoding="utf-8"))
        for name, s in d.get("signs", {}).items():
            rec = self.signs.setdefault(name, {"u": None, "uname": None, "values": []})
            if not rec["u"] and s.get("utf8"):
                rec["u"] = s["utf8"]
            if not rec["uname"] and s.get("uname"):
                rec["uname"] = s["uname"]
            for v in s.get("values", []):
                if v not in rec["values"]:
                    rec["values"].append(v)
        for v, name in d.get("index", {}).items():
            if v not in self.index and name in self.signs:
                self.index[v] = name

    @staticmethod
    def normalize(value):
        return (value.replace("ĝ", "ŋ").replace("Ĝ", "Ŋ")
                .replace("ḫ", "h").replace("Ḫ", "H"))

    def by_value(self, value):
        v = self.normalize(value)
        name = self.index.get(v)
        if name is None and v != v.lower():
            name = self.index.get(v.lower())
        return name

    def by_name(self, name):
        n = self.normalize(name)
        if n in self.signs:
            return n
        if n.upper() in self.signs:
            return n.upper()
        return None

    def glyph(self, name):
        return self.signs.get(name, {}).get("u") if name else None


# ----------------------------------------------------------------------------
# ETCSL transliteration: HTML cell -> token stream
# ----------------------------------------------------------------------------


class CellTokenizer(HTMLParser):
    """Turn the body cell of one ETCSL line into a flat list of tokens.

    ('text', str)                 text between words: brackets, braces, spaces, parens
    ('word', dict)                one glossed word: parts, lemma, pos, gloss, proper
    ('note', str)                 editorial note (variant headers, citations)
    ('akk', str)                  Akkadian gloss
    Inside a word, parts are ('t', text) | ('det', text) | ('unc',) tokens.
    """

    TOOLTIP = re.compile(r"doTooltip\(event, '(.*)'\)$", re.S)

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self.word = None
        self.note = None
        self.akk = None
        self.proper = 0
        self.sub = False
        self.sup = False
        self.sup_text = ""
        self.stack = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        kind = None
        if tag == "span":
            if a.get("class") == "note":
                kind = "note"
                self.note = ""
            elif a.get("class") == "glossakk":
                kind = "akk"
                self.akk = ""
            elif a.get("class") == "proper":
                kind = "proper"
                self.proper += 1
            elif a.get("onmouseover"):
                kind = "word"
                tip = self.TOOLTIP.search(a["onmouseover"])
                lemma, pos, gloss = self._parse_tip(tip.group(1) if tip else "")
                self.word = {"parts": [], "lemma": lemma, "pos": pos, "gloss": gloss,
                             "proper": self.proper > 0}
        elif tag == "sub":
            self.sub = True
            kind = "sub"
        elif tag == "sup":
            self.sup = True
            self.sup_text = ""
            kind = "sup"
        self.stack.append((tag, kind))

    def handle_endtag(self, tag):
        while self.stack:
            t, kind = self.stack.pop()
            if t == tag:
                break
        else:
            kind = None
        if kind == "word":
            self.tokens.append(("word", self.word))
            self.word = None
        elif kind == "note":
            self.tokens.append(("note", re.sub(r"\s+", " ", self.note).strip()))
            self.note = None
        elif kind == "akk":
            self.tokens.append(("akk", self.akk.strip()))
            self.akk = None
        elif kind == "proper":
            self.proper -= 1
        elif kind == "sub":
            self.sub = False
        elif kind == "sup":
            self.sup = False
            txt = self.sup_text.strip()
            if self.word is not None:
                if txt in ("?", "!"):
                    self.word["parts"].append(("q", txt))
                else:
                    self.word["parts"].append(("det", txt))
            elif self.note is not None:
                self.note += txt
            else:
                self.tokens.append(("text", "{" + txt + "}"))

    def handle_data(self, data):
        if self.sub:
            data = data.translate(SUB)
        if self.sup:
            self.sup_text += data
            return
        if self.note is not None:
            self.note += data
        elif self.akk is not None:
            self.akk += data
        elif self.word is not None:
            parts = self.word["parts"]
            if parts and parts[-1][0] == "t":  # <sub> splits a reading into several data chunks
                parts[-1] = ("t", parts[-1][1] + data)
            else:
                parts.append(("t", data))
        else:
            self.tokens.append(("text", data.replace("\xa0", " ")))

    @staticmethod
    def _parse_tip(tip):
        tip = re.sub(r"<sub>(\w+)</sub>", lambda m: m.group(1).translate(SUB), tip)
        tip = re.sub(r"<[^>]+>", "", tip)
        m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*(.*)$", tip, re.S)
        if not m:
            return tip.strip(), "", ""
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()


# ----------------------------------------------------------------------------
# Words -> signs
# ----------------------------------------------------------------------------

NUMERAL_NAMES = {1: "1(diš)", 2: "2(diš)", 3: "3(diš)", 4: "4(diš)", 5: "5(diš)",
                 6: "6(diš)", 7: "7(diš)", 8: "8(diš)", 9: "9(diš)",
                 10: "1(u)", 20: "2(u)", 30: "3(u)", 40: "4(u)", 50: "5(u)", 60: "1(diš)"}


class SignBuilder:
    def __init__(self, signlist):
        self.sl = signlist
        self.unresolved = collections.Counter()
        self.used = {}

    def _record(self, name):
        if name and name not in self.used:
            s = self.sl.signs[name]
            self.used[name] = {"u": s["u"], "uname": s["uname"], "values": s["values"][:12]}

    def resolve_value(self, value):
        name = self.sl.by_value(value)
        if name is None and value == value.upper() and value != value.lower():
            name = self.sl.by_name(value)  # capitalised sign name, reading unknown
        self._record(name)
        return name

    def resolve_name(self, name):
        candidates = [self.sl.by_name(name), self.sl.by_value(name.lower())]
        candidates = [c for c in candidates if c]
        # Prefer whichever route lands on a sign that has a glyph (e.g. 2(diš) -> MIN, not 2(DIŠ)).
        n = next((c for c in candidates if self.sl.glyph(c)), candidates[0] if candidates else None)
        self._record(n)
        return n

    @staticmethod
    def split_dashes(text):
        """Split on '-' and '.', but not inside parentheses."""
        out, buf, depth = [], "", 0
        for ch in text:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch in "-." and depth == 0:
                out.append(buf)
                buf = ""
            else:
                buf += ch
        out.append(buf)
        return out

    def word_signs(self, parts, state):
        """parts: [('t', text) | ('det', text) | ('q', '?')]; state: dict of bracket flags."""
        signs = []
        for kind, text in parts:
            if kind == "det":
                signs.extend(self.piece_signs(text, state, det=True))
            elif kind == "q":
                if signs:
                    signs[-1]["q"] = text
            else:
                for piece in self.split_dashes(text):
                    signs.extend(self.piece_signs(piece, state))
        return signs

    def piece_signs(self, piece, state, det=False):
        """One hyphen-delimited element -> zero or more sign records, updating bracket state."""
        out = []
        core = ""
        pre = {}
        quals = ""
        # Walk characters: brackets toggle state, letters accumulate.
        i = 0
        while i < len(piece):
            ch = piece[i]
            if ch == "[":
                state["r"] = True
            elif ch == "]":
                state["r"] = False
            elif ch == "/":
                state["d"] = True
            elif ch == "\\":
                state["d"] = False
            elif ch == "<":
                state["i"] = True
            elif ch == ">":
                state["i"] = False
            elif ch == "«":
                state["s"] = True
            elif ch == "»":
                state["s"] = False
            elif ch in "?!":
                quals += ch
            else:
                if not core:
                    pre = {k: v for k, v in state.items() if v}
                core += ch
            i += 1
        core = core.strip()
        if not core:
            return out

        def rec(v, name, kind=None):
            r = {"v": v, "n": name, "u": self.sl.glyph(name)}
            if det:
                r["det"] = True
            if pre.get("r"):
                r["dmg"] = "r"
            elif pre.get("d"):
                r["dmg"] = "d"
            if pre.get("i"):
                r["ins"] = True
            if pre.get("s"):
                r["extra"] = True  # scribal error: sign is superfluous («...» in ETCSL)
            if quals:
                r["q"] = quals
            if kind:
                r["k"] = kind
            if name is None and kind is None:
                self.unresolved[v] += 1
            return r

        if core in ("X", "x"):
            out.append(rec("x", None, "x"))
        elif core in ("…", "...", "...."):
            out.append(rec("…", None, "gap"))
        elif re.fullmatch(r"\d+", core):
            n = int(core)
            name = self.resolve_name(NUMERAL_NAMES.get(n, "")) if n in NUMERAL_NAMES else None
            out.append(rec(core, name, "num"))
        else:
            m = re.fullmatch(r"(.+?)\((.+)\)", core)
            if m:
                base, qual = m.group(1), m.group(2)
                if "-" in qual or "." in qual:
                    # e.g. mussa(mi₂-us₂-sa₂): render the component signs, remember the reading
                    for comp in re.split(r"[-.]", qual):
                        r = rec(comp, self.resolve_value(comp))
                        r["grp"] = base
                        out.append(r)
                else:
                    out.append(rec(base, self.resolve_name(qual)))
            else:
                out.append(rec(core, self.resolve_value(core)))
        return out


# ----------------------------------------------------------------------------
# Line assembly
# ----------------------------------------------------------------------------

VARIANT_NOTE = re.compile(r"\bmss?\.", re.I)


def word_text(parts):
    s = ""
    for kind, text in parts:
        if kind == "det":
            s += "{" + text + "}"
        elif kind == "q":
            s += text
        else:
            s += text
    return s.strip()


def split_text_token(text):
    """Break a between-words text token into atomic pieces so braces/brackets are visible."""
    return [p for p in re.findall(r"\s+|[\[\]/\\{}()<>«»]|[^\s\[\]/\\{}()<>«»]+", text) if p]


def assemble_line(tokens, builder, stats):
    """Turn a token stream into words/notes/variants; braces delimit manuscript variants."""
    atoms = []
    for kind, val in tokens:
        if kind == "text":
            atoms.extend(("text", p) for p in split_text_token(val))
        else:
            atoms.append((kind, val))

    def process(seq, state):
        """Process atoms (no variant handling); returns words, notes, akk."""
        words, notes = [], []
        i = 0
        while i < len(seq):
            kind, val = seq[i]
            if kind == "word":
                w = {"t": word_text(val["parts"]), "lemma": val["lemma"], "pos": val["pos"],
                     "gloss": val["gloss"], "signs": builder.word_signs(val["parts"], state)}
                if val["proper"]:
                    w["proper"] = True
                words.append(w)
            elif kind == "note":
                notes.append(val)
            elif kind == "akk":
                notes.append("Akkadian gloss: " + val)
            elif kind == "text":
                if val == "[":
                    state["r"] = True
                elif val == "]":
                    state["r"] = False
                elif val == "/":
                    state["d"] = True
                elif val == "\\":
                    state["d"] = False
                elif val == "<":
                    state["i"] = True
                elif val == ">":
                    state["i"] = False
                elif val == "«":
                    state["s"] = True
                elif val == "»":
                    state["s"] = False
                elif val == "?" and words:
                    words[-1]["q"] = True
                elif val.strip() and val not in "()":
                    # Stray text such as "X" outside a word span, or "…"
                    if val in ("X", "x", "…", "..."):
                        st = dict(state)
                        words.append({"t": val, "lemma": "", "pos": "", "gloss": "",
                                      "signs": builder.piece_signs(val, st)})
                    else:
                        stats["stray"].append(val)
            i += 1
        return words, notes

    # Group by braces at the top level.
    line = {"words": [], "notes": [], "variants": []}
    state = {"r": False, "d": False, "i": False, "s": False}
    i = 0
    pending_main = None
    while i < len(atoms):
        kind, val = atoms[i]
        if kind == "text" and val == "{":
            depth, j = 1, i + 1
            while j < len(atoms) and depth:
                if atoms[j] == ("text", "{"):
                    depth += 1
                elif atoms[j] == ("text", "}"):
                    depth -= 1
                j += 1
            group = atoms[i + 1:j - 1]
            first_note = next((v for k, v in group if k == "note"), None)
            leading = [k for k, v in group if not (k == "text" and not v.strip()) and not (k == "text" and v in "()")]
            if first_note and VARIANT_NOTE.search(first_note) and leading and leading[0] == "note":
                vstate = dict(state)
                rest = [a for a in group if a[1] != first_note]
                vwords, vnotes = process(rest, vstate)
                var = {"note": first_note, "words": vwords,
                       "t": " ".join(w["t"] for w in vwords)}
                if vnotes:
                    var["notes"] = vnotes
                if pending_main is not None:
                    var["replaces"] = pending_main
                line["variants"].append(var)
            else:
                words, notes = process(group, state)
                line["words"].extend(words)
                line["notes"].extend(notes)
                pending_main = " ".join(w["t"] for w in words)
            i = j
            continue
        words, notes = process([atoms[i]], state)
        if words:
            pending_main = None
        line["words"].extend(words)
        line["notes"].extend(notes)
        i += 1
    return line


def parse_translit(path, num, builder, stats):
    html = path.read_text(encoding="utf-8")
    cid = "c" + num.replace(".", "")
    tid = "t" + num.replace(".", "")
    title = re.search(r"<h2>(.*?)</h2>", html).group(1)
    row_re = re.compile(
        r"<td align='right' valign='top'><a href='[^']*lineid=" + tid + r"\.(p\d+)'>([^<]*)</a>"
        r"<a name='" + cid + r"\.([^']*)'></a></td><td>(.*?)</td>", re.S)
    lines = []
    for para, label, lid, body in row_re.findall(html):
        tok = CellTokenizer()
        tok.feed(body)
        tok.close()
        line = assemble_line(tok.tokens, builder, stats)
        line.update({"id": lid, "label": label.rstrip("."), "para": para})
        if body.lstrip().startswith("&nbsp;"):
            line["indent"] = True
        for k in ("notes", "variants"):
            if not line[k]:
                del line[k]
        lines.append(line)
    return title, lines


# ----------------------------------------------------------------------------
# ETCSL translation
# ----------------------------------------------------------------------------


class TranslTokenizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.note = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "span" and a.get("class") == "note":
            self.note = ""

    def handle_endtag(self, tag):
        if tag == "span" and self.note is not None:
            self.out.append(("note", self.note.strip()))
            self.note = None

    def handle_data(self, data):
        if self.note is not None:
            self.note += data
        else:
            self.out.append(("text", data))


def parse_translation(path, num):
    html = path.read_text(encoding="utf-8")
    cid = "c" + num.replace(".", "")
    tid = "t" + num.replace(".", "")
    p_re = re.compile(r"<p>\s*(?:&nbsp;)*\s*<a href='[^']*lineid=" + cid + r"\.([^']*)'>([^<]*)</a>"
                      r"<a name='" + tid + r"\.(p\d+)'></a>(.*?)</p>", re.S)
    paras = []
    for first, rng, pid, body in p_re.findall(html):
        tok = TranslTokenizer()
        tok.feed(body)
        tok.close()
        # Resolve {main} {(note) alt} groups: keep main in text, record alternatives.
        text, variants = "", []
        toks = tok.out
        flat = ""
        for kind, val in toks:
            flat += val if kind == "text" else "\x00" + val + "\x01"
        # Split braces groups
        pos = 0
        pieces = re.split(r"(\{[^{}]*\})", flat)
        groups = []
        for pc in pieces:
            if pc.startswith("{") and pc.endswith("}"):
                inner = pc[1:-1]
                m = re.match(r"\s*\(?\x00(.*?)\x01\)?\s*(.*)$", inner, re.S)
                if m:
                    groups.append(("var", m.group(1).strip(), m.group(2).strip()))
                else:
                    groups.append(("main", None, inner.strip()))
            elif pc:
                groups.append(("text", None, pc))
        last_main = None
        for kind, note, val in groups:
            if kind == "text":
                text += val
            elif kind == "main":
                text += val
                last_main = val
            else:
                variants.append({"note": note, "replaces": last_main, "text": val})
        notes = [n.strip() for n in re.findall(r"\x00(.*?)\x01", text)]
        text = re.sub(r"\x00.*?\x01", "", text)
        text = re.sub(r"\(\s*\)", "", text)  # parentheses that only held a note
        text = re.sub(r"\s+", " ", text).replace(" ,", ",").replace(" .", ".").strip()
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        para = {"id": pid, "range": rng.rstrip("."), "first": first, "text": text,
                "variants": variants}
        if notes:
            para["notes"] = notes
        paras.append(para)
    return paras


# ----------------------------------------------------------------------------
# Alignment (per-line translation chunks)
# ----------------------------------------------------------------------------


def norm_words(s):
    s = re.sub(r"\[[^\]]*\]", " ", s)  # drop editorial brackets in chunk text
    s = s.lower().replace("’", "'")
    return re.findall(r"[a-z0-9']+", s)


def build_chunks(lines, paras, alignment, warn):
    para_by_id = {p["id"]: p for p in paras}
    line_para = {ln["id"]: ln["para"] for ln in lines}
    covered = {}
    chunks = []
    if alignment:
        for ch in alignment["chunks"]:
            ids = ch["lines"] if isinstance(ch["lines"], list) else [ch["lines"]]
            ids = [str(x) for x in ids]
            unknown = [i for i in ids if i not in line_para]
            if unknown:
                warn(f"alignment: unknown line id(s) {unknown}")
                continue
            if ch.get("para"):
                # ETCSL sometimes translates a line in the neighbouring paragraph.
                for i in ids:
                    line_para[i] = ch["para"]
            paras_hit = {line_para[i] for i in ids}
            if len(paras_hit) > 1:
                warn(f"alignment: chunk {ids} crosses paragraphs {paras_hit}")
            for i in ids:
                if i in covered:
                    warn(f"alignment: line {i} covered twice")
                covered[i] = True
            chunks.append({"lines": ids, "para": paras_hit.pop(), "text": ch["text"]})
    for ln in lines:
        ln["para"] = line_para[ln["id"]]
    by_para = collections.OrderedDict()
    for ln in lines:
        by_para.setdefault(ln["para"], []).append(ln["id"])
    # Paragraph fallback for anything not covered.
    for pid, ids in by_para.items():
        missing = [i for i in ids if i not in covered]
        if not missing:
            continue
        if len(missing) != len(ids):
            warn(f"alignment: paragraph {pid} only partly covered; missing lines {missing}")
        p = para_by_id.get(pid)
        chunks.append({"lines": missing, "para": pid,
                       "text": p["text"] if p else "", "fallback": True})
    # Keep document order.
    order = {ln["id"]: n for n, ln in enumerate(lines)}
    chunks.sort(key=lambda c: order[c["lines"][0]])
    # Check that chunk texts reproduce the paragraph text.
    if alignment:
        for pid, p in para_by_id.items():
            mine = [c for c in chunks if c["para"] == pid and not c.get("fallback")]
            if not mine:
                continue
            got = norm_words(" ".join(c["text"] for c in mine))
            want = norm_words(p["text"])
            if got != want:
                import difflib
                diff = [d for d in difflib.ndiff(want, got) if d[0] in "+-"]
                warn(f"alignment: paragraph {pid} ({p['range']}) text differs from ETCSL: "
                     + " ".join(diff[:30]))
    return chunks


# ----------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("num", help="ETCSL composition number, e.g. 1.4.3")
    ap.add_argument("--title")
    args = ap.parse_args()

    warnings = []
    warn = warnings.append
    stats = {"stray": []}
    sl = SignList(ROOT / "data/sources/osl/osl.asl", ROOT / "data/sources/osl/ogsl-sl.json")
    builder = SignBuilder(sl)
    title, lines = parse_translit(ROOT / f"data/sources/etcsl/c.{args.num}.html", args.num, builder, stats)
    paras = parse_translation(ROOT / f"data/sources/etcsl/t.{args.num}.html", args.num)
    align_path = ROOT / f"data/alignments/{args.slug}.json"
    alignment = json.loads(align_path.read_text(encoding="utf-8")) if align_path.exists() else None
    chunks = build_chunks(lines, paras, alignment, warn)

    nsigns = sum(len(w["signs"]) for ln in lines for w in ln["words"])
    nglyph = sum(1 for ln in lines for w in ln["words"] for s in w["signs"] if s["u"])
    out = {
        "slug": args.slug,
        "title": args.title or title,
        "source": {
            "etcsl": args.num,
            "transliteration": f"https://etcsl.orinst.ox.ac.uk/cgi-bin/etcsl.cgi?text=c.{args.num}&display=Crit&charenc=gcirc",
            "translation": f"https://etcsl.orinst.ox.ac.uk/cgi-bin/etcsl.cgi?text=t.{args.num}",
            "signlist": "ORACC Global Sign List (OSL), CC BY-SA",
            "alignment": "per-line" if alignment else "paragraph",
        },
        "stats": {"lines": len(lines), "signs": nsigns, "signs_with_glyph": nglyph,
                  "distinct_signs": len(builder.used)},
        "signs": builder.used,
        "lines": lines,
        "paragraphs": paras,
        "chunks": chunks,
    }
    dest = ROOT / f"data/texts/{args.slug}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Library index entry
    lib_path = ROOT / "data/library.json"
    lib = json.loads(lib_path.read_text(encoding="utf-8")) if lib_path.exists() else {"texts": []}
    entry = next((t for t in lib["texts"] if t["slug"] == args.slug), None)
    if entry is None:
        entry = {"slug": args.slug}
        lib["texts"].append(entry)
    first = lines[0]
    entry.update({
        "title": out["title"],
        "etcsl": args.num,
        "lines": len(lines),
        "incipit": " ".join("".join(s["u"] or "" for s in w["signs"]) for w in first["words"]),
        "incipit_translit": " ".join(w["t"] for w in first["words"]),
        "incipit_translation": next((c["text"] for c in chunks if first["id"] in c["lines"]), ""),
    })
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{dest.relative_to(ROOT)}: {len(lines)} lines, {nsigns} signs, "
          f"{nglyph} with glyphs ({nglyph / max(nsigns, 1):.1%}), {len(builder.used)} distinct signs, "
          f"{len(chunks)} translation chunks")
    if builder.unresolved:
        print("unresolved readings:", dict(builder.unresolved.most_common()))
    if stats["stray"]:
        print("stray text ignored:", collections.Counter(stats["stray"]).most_common(20))
    for w in warnings:
        print("WARNING:", w)
    return 1 if (builder.unresolved and "--strict" in sys.argv) else 0


if __name__ == "__main__":
    sys.exit(main())
