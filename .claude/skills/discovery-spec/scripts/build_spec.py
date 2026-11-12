#!/usr/bin/env python3
"""content.json + spec-theme.json -> spec.html (the client document) + sources.md (the internal check)
+ internal-gaps.md (questions to send before the price quote - for the freelancer only, never in the PDF).

The template is the design; this script only fills it. Claude never writes the HTML by hand.

Usage: python3 build_spec.py <content.json> <spec-theme.json | -> <out_dir>
Prints a short report: blocks, items, items without a source, and rule warnings.
"""
import base64, html, json, mimetypes, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
TPL = HERE / "templates" / "spec-template.html"

DEFAULT_THEME = {
    "brand": "העסק שלך", "logo": "",
    "primary": "#1F3A5F", "primary_ink": "#FFFFFF", "accent": "#E7EEF6",
    "ink": "#1B1D21", "muted": "#6A6F78", "line": "#E2E4E8", "paper": "#F5F6F8",
    "font": "'Heebo', 'Arial', sans-serif", "font_head": "'Heebo', 'Arial', sans-serif",
    "font_query": "Heebo:wght@400;500;700;800", "radius": "3mm",
}

# block type -> does every item need a source from the transcript?
NEEDS_SRC = {"list": True, "stages": True, "checklist": True, "table": True, "out": True, "ideas": True, "open": False, "text": True, "problem": True, "limits": True}

# Hebrew number words, so a number in the document can be checked against what was actually said
_UNITS = {"אחת": 1, "אחד": 1, "שתיים": 2, "שתים": 2, "שניים": 2, "שתי": 2, "שני": 2, "פעמיים": 2, "שלוש": 3, "שלושה": 3,
          "ארבע": 4, "ארבעה": 4, "חמש": 5, "חמישה": 5, "שש": 6, "שישה": 6, "שבע": 7, "שבעה": 7, "שמונה": 8,
          "תשע": 9, "תשעה": 9, "עשר": 10, "עשרה": 10}
_TENS = {"עשרים": 20, "שלושים": 30, "ארבעים": 40, "חמישים": 50, "שישים": 60, "שבעים": 70, "שמונים": 80, "תשעים": 90}
_BIG = {"מאה": 100, "מאות": 100, "מאתיים": 200, "אלף": 1000, "אלפיים": 2000}


def _numword(w):
    for cand in (w, w[1:] if len(w) > 2 and w[0] in "בולמהשכ" else None):
        if cand and cand in _UNITS:
            return _UNITS[cand]
        if cand and cand in _TENS:
            return _TENS[cand]
        if cand and cand in _BIG:
            return _BIG[cand]
    return None


def said_numbers(quotes):
    """Every number that appears in the quotes - as digits or as Hebrew words (שתים עשרה -> 12, ארבעים ואחת -> 41)."""
    found = set()
    for q in quotes:
        found.update(float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", q))
        words = re.findall(r"[א-ת]+", q)
        vals = [_numword(w) for w in words]
        for i, v in enumerate(vals):
            if v is None:
                continue
            found.add(float(v))
            nxt = vals[i + 1] if i + 1 < len(vals) else None
            if v < 10 and nxt == 10 and words[i + 1] in ("עשר", "עשרה"):
                found.add(float(v + 10))                     # שתים עשרה
            if v in _TENS.values() and nxt is not None and nxt < 10:
                found.add(float(v + nxt))                     # ארבעים ואחת
            if v >= 100 and nxt is not None:
                found.add(float(v + nxt))
            if i > 0 and vals[i - 1] is not None and vals[i - 1] < 10 and v in (100, 1000):
                found.add(float(vals[i - 1] * v))             # שלושה אלף
    return found


def check_numbers(where, text, src_list):
    """A number in the document that nobody said = an invented number."""
    said = said_numbers([s.get("q", "") for s in src_list])
    for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        if float(n.replace(",", "")) not in said:
            warnings.append(f"מספר שלא נמצא בציטוט ({where}): {n} - \"{text[:60]}\". רק מספרים שנאמרו בפגישה")


def _norm(s):
    return re.sub(r"[^\wא-ת ]", "", str(s)).split()


def quote_in_src(quote, src_list):
    qn = " ".join(_norm(quote))
    return any(qn and qn in " ".join(_norm(s.get("q", ""))) for s in src_list)
# (?<![א-ת]) = a whole word only, so "משקל" (weight) is not read as "שקל" (shekel)
PRICE_RE = re.compile(r"(₪|(?<![א-ת])ש[\"״]ח|(?<![א-ת])שקל(ים)?(?![א-ת])|\bNIS\b|(?<![א-ת])מע[\"״]מ|\$\s?\d|\d[\d,.]*\s*(אלף|אלפים|דולר)(?![א-ת]))")
DATE_RE = re.compile(r"\b\d{1,2}[./]\d{1,2}([./]\d{2,4})?\b|(ינואר|פברואר|מרץ|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)")

warnings = []


def esc(s):
    return html.escape(str(s or ""), quote=False)


def mark(s):
    """[חסר: ...] stays visible and yellow inside the text."""
    return re.sub(r"\[חסר:([^\]]*)\]", r'<mark class="missing">[חסר:\1]</mark>', esc(s))


def txt(item):
    return item if isinstance(item, str) else item.get("text", "")


def srcs(item):
    return [] if isinstance(item, str) else (item.get("src") or [])


def contact_item(x):
    x = str(x).strip()
    if re.match(r"^[\w.+-]+@[\w-]+\.[\w.]+$", x) or re.match(r"^(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", x) or re.match(r"^[+\d][\d\s()-]{6,}$", x):
        return f'<span dir="ltr">{esc(x)}</span>'
    return f"<span>{esc(x)}</span>"


def logo_tag(path, base):
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = (base / p).resolve()
    if not p.exists():
        warnings.append(f"הלוגו לא נמצא: {path} - המסמך נבנה בלי לוגו")
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    data = base64.b64encode(p.read_bytes()).decode()
    return f'<img src="data:{mime};base64,{data}" alt="">'


def check_rules(where, text, block_type):
    if block_type not in ("ideas", "open", "out") and PRICE_RE.search(text):
        warnings.append(f"מחיר/תשלום במסמך ({where}): \"{text[:60]}\" - מחירים שייכים להצעת המחיר, לא לאפיון")
    if block_type in ("stages", "next") and DATE_RE.search(text):
        warnings.append(f"תאריך בלוח הזמנים ({where}): \"{text[:60]}\" - בלי תאריך ביומן לפני שסוכם מועד התחלה")


def render_problem(p):
    """The opening: the client's problem in HER words and HER numbers, before 'בקצרה'."""
    items = p.get("items", [])
    lis = []
    for x in items:
        q = x.get("quote")
        if q and not quote_in_src(q, srcs(x)):
            warnings.append(f"ציטוט בפתיחה שלא מופיע מילה במילה ב-src: \"{q[:50]}\" - ציטוט חייב להיות מדויק")
        check_numbers(p.get("title", "הפתיחה"), txt(x), srcs(x))
        quote = f'<span class="said">"{esc(q.strip().strip(chr(34)))}"</span>' if q else ""
        lis.append(f"<li><span>{mark(txt(x))}</span>{quote}</li>")
    if len(items) > 3:
        warnings.append(f"בפתיחה {len(items)} שורות - עד 3. הפתיחה היא הבעיה, לא כל הפגישה")
    return (f'<section class="problem"><b class="label">{esc(p.get("title", "מה שמעתי ממך"))}</b>'
            f'<ul>{"".join(lis)}</ul></section>')


def render_approval(b, titles=()):
    """Ready-to-send confirmation the client copies and sends back. Copy button = screen only."""
    text = b.get("text", "")
    for name in re.findall(r'["״“”]([^"״“”]{2,40})["״“”]', text):
        if titles and name.strip() not in titles:
            warnings.append(f'האישור מפנה לסעיף "{name}" שאין במסמך. סעיפים: {" · ".join(titles)}')
    check_rules("אישור", text, "next")
    check_numbers("אישור", text, b.get("src", []))
    if len(text.split()) > 70:
        warnings.append(f"טקסט האישור ארוך ({len(text.split())} מילים) - עד 70, שיהיה קל לשלוח מהטלפון")
    note = f'<p class="note">{mark(b["note"])}</p>' if b.get("note") else ""
    return (f'<section class="section approval-wrap"><div class="approval">'
            f'<div class="approval-head"><h2>{esc(b.get("title", "אישור האפיון"))}</h2>'
            f'<button type="button" class="copy-btn" contenteditable="false" onclick="copyApproval(this)">העתקה</button></div>'
            f'{note}<p class="approval-text" id="approval-text">{mark(text)}</p></div></section>')


def render_block(i, b):
    t = b.get("type", "list")
    title = esc(b.get("title", ""))
    head = f'<div class="section-head"><span class="num">{i:02d}</span><h2>{title}</h2></div>'
    intro = f'<p class="intro">{mark(b["intro"])}</p>' if b.get("intro") else ""
    items = b.get("items", [])
    if t == "text":
        body = "".join(f"<p>{mark(txt(x))}</p>" for x in items)
    elif t == "list":
        body = '<ul class="items">' + "".join(f"<li>{mark(txt(x))}</li>" for x in items) + "</ul>"
    elif t == "stages":
        lis = []
        for x in items:
            out = f'<div class="out"><b>{esc(b.get("output_label", "מה יוצא מהשלב:"))}</b> {mark(x.get("output"))}</div>' if x.get("output") else ""
            lis.append(f'<li><h3>{mark(x.get("title"))}</h3><p>{mark(x.get("text"))}</p>{out}</li>')
        body = '<ol class="stages">' + "".join(lis) + "</ol>"
    elif t == "checklist":
        body = '<ul class="check">' + "".join(
            f'<li><span>{mark(txt(x))}</span>' + (f'<span class="status">{mark(x.get("status"))}</span>' if isinstance(x, dict) and x.get("status") else "") + "</li>"
            for x in items) + "</ul>"
    elif t == "table":
        cols = "".join(f"<th>{esc(c)}</th>" for c in b.get("columns", []))
        rows = "".join("<tr>" + "".join(f"<td>{mark(c)}</td>" for c in r.get("cells", [])) + "</tr>" for r in b.get("rows", []))
        body = f'<table class="grid"><thead><tr>{cols}</tr></thead><tbody>{rows}</tbody></table>'
        items = b.get("rows", [])
    elif t == "out":
        limits = b.get("limits") or []
        tiles = ""
        if limits:
            tiles = '<div class="limits">' + "".join(
                f'<div class="limit"><b>{mark(x.get("value"))}</b><span>{mark(x.get("label"))}</span></div>' for x in limits) + "</div>"
            for x in limits:
                check_numbers("גבולות", f'{x.get("value", "")} {x.get("label", "")}', srcs(x))
        note = f'<p class="note">{mark(b["note"])}</p>' if b.get("note") else ""
        ul = '<ul class="out">' + "".join(f"<li>{mark(txt(x))}</li>" for x in items) + "</ul>" if items else ""
        if limits:  # two labels, so a tile is never read as "not included"
            tiles = f'<p class="sub">{esc(b.get("limits_label", "מה שסיכמנו, בדיוק"))}</p>' + tiles
            if ul:
                ul = f'<p class="sub">{esc(b.get("items_label", "לא כלול"))}</p>' + ul
        body = f'<div class="scope">{tiles}{note}{ul}</div>'
    elif t in ("ideas", "open"):
        note = f'<p class="note">{mark(b["note"])}</p>' if b.get("note") else ""
        body = f'<div class="box {t}">{note}<ul>' + "".join(f"<li>{mark(txt(x))}</li>" for x in items) + "</ul></div>"
    elif t == "next":
        timing = f'<p class="timing">{mark(b["timing"])}</p>' if b.get("timing") else ""
        contact = b.get("contact") or []
        contact_html = f'<div class="contact">{"".join(contact_item(c) for c in contact)}</div>' if contact else ""
        check_rules("הצעד הבא", b.get("text", "") + " " + b.get("timing", ""), "next")
        return f'<section class="section next-wrap"><div class="next"><h2>{title}</h2><p>{mark(b.get("text"))}</p>{timing}{contact_html}</div></section>'
    else:
        warnings.append(f"סוג סעיף לא מוכר: {t} - דולג")
        return ""
    for x in items:
        tx = txt(x) if t != "table" else " ".join(x.get("cells", []))
        if t == "stages":
            tx = " ".join([x.get("title", ""), x.get("text", ""), x.get("output", "")])
        check_rules(b.get("title", t), tx, t)
    # a short section (up to 5 short items) moves to the next page whole, instead of splitting 2+2
    keep = " keep" if t != "stages" and len(items) <= 5 else ""
    return f'<section class="section{keep}">{head}{intro}{body}</section>'


def sources_md(c):
    out = [f"# בדיקה פנימית - {c.get('title', '')}", "",
           "> המסמך הזה **לא נשלח ללקוח**. כל שורה במסמך האפיון, ומאיפה בפגישה היא הגיעה.",
           "> שורה בלי מקור = לבדוק לפני ששולחים.", ""]
    total = with_src = 0
    no_src = []

    def rows_for(label, items, t):
        nonlocal total, with_src
        lines = [f"## {label}", "", "| מה כתוב במסמך | מי | דקה | מה נאמר |", "|---|---|---|---|"]
        for x in items:
            if t == "table":
                text = " · ".join(x.get("cells", []))
            elif t == "stages":
                text = x.get("title", "")
            else:
                text = txt(x)
            ss = srcs(x) if not isinstance(x, str) else []
            total += 1
            if ss:
                with_src += 1
                for k, s in enumerate(ss):
                    lines.append(f"| {text if k == 0 else '〃'} | {s.get('who', '')} | {s.get('t', '')} | \"{s.get('q', '')}\" |")
            else:
                reason = x.get("reason", "") if isinstance(x, dict) else ""
                lines.append(f"| {text} | - | - | {'⚠️ ללא מקור' if NEEDS_SRC.get(t, True) else (reason or 'לא עלה בפגישה')} |")
                if NEEDS_SRC.get(t, True):
                    no_src.append(text)
        return lines + [""]

    if c.get("problem"):
        out += rows_for(c["problem"].get("title", "מה שמעתי ממך") + " (הפתיחה)", c["problem"].get("items", []), "problem")
    if c.get("summary"):
        out += rows_for("בקצרה", [c["summary"]], "text")
    for b in c.get("blocks", []):
        t = b.get("type")
        if t == "out" and b.get("limits"):
            out += rows_for("גבולות העבודה", [{"text": f'{x.get("label", "")}: {x.get("value", "")}', "src": x.get("src", [])} for x in b["limits"]], "limits")
        if t == "approval":
            ss = b.get("src", [])
            out += [f"## {b.get('title', 'אישור האפיון')}", "",
                    "> טקסט האישור לא מוסיף עובדות: הוא מפנה לסעיפים שכבר במסמך. כל מספר בו מגיע מהציטוט כאן.", ""]
            out += [f"| {b.get('text', '')} | " + (" · ".join(f"{s.get('who', '')} {s.get('t', '')}: \"{s.get('q', '')}\"" for s in ss) or "מפנה לסעיפי המסמך") + " |", ""]
            continue
        if t == "next":
            out += rows_for(b.get("title", "הצעד הבא"), [{"text": b.get("text", ""), "src": b.get("src", [])}] + ([{"text": b["timing"], "src": b.get("timing_src", [])}] if b.get("timing") else []), "list")
        else:
            out += rows_for(b.get("title", t), b.get("rows", []) if t == "table" else b.get("items", []), t)
    head = [f"**{with_src} מתוך {total} שורות עם מקור בתמלול.**" + (f" ⚠️ {len(no_src)} בלי מקור - לבדוק." if no_src else " ✅"), ""]
    return "\n".join(out[:5] + head + out[5:]), total, with_src, no_src


def gaps_md(c):
    g = c.get("internal_gaps") or {}
    qs = g.get("questions") or []
    if not qs:
        warnings.append("אין internal_gaps - חסר הקובץ הפנימי 'מה לא נשאל בפגישה' (3 שאלות לפני הצעת המחיר)")
        return None
    if len(qs) != 3:
        warnings.append(f"ב-internal_gaps יש {len(qs)} שאלות - צריך בדיוק 3")
    out = [f"# מה לא נשאל בפגישה - {c.get('footer_note', '') or c.get('title', '')}", "",
           "> **פנימי. לא נכנס ל-PDF ולא נשלח ללקוח כמו שהוא.**",
           "> 3 שאלות לשלוח לפני הצעת המחיר. כל אחת נשענת על רגע בפגישה שבו הנושא עלה ולא נסגר, או נסגר בלי פרט שחסר כדי לתמחר.", ""]
    for i, x in enumerate(qs, 1):
        ss = x.get("src") or []
        if not ss or not all(s.get("t") for s in ss):
            warnings.append(f"שאלה {i} ב-internal_gaps בלי דקה בפגישה - כל שאלה נשענת על רגע בתמלול")
        out += [f"## {i}. {x.get('q', '')}", ""]
        if x.get("gap"):
            out.append(f"- **מה חסר:** {x['gap']}")
        for s in ss:
            out.append(f"- **בפגישה, {s.get('t', '')}:** {s.get('who', '')}: \"{s.get('q', '')}\"")
        if x.get("affects"):
            out.append(f"- **מה זה משנה בהצעת המחיר:** {x['affects']}")
        out.append("")
    if g.get("message"):
        out += ["## הודעה מוכנה לשליחה", "", "```", g["message"], "```", ""]
    return "\n".join(out)


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: build_spec.py <content.json> <spec-theme.json|-> <out_dir>")
    cpath = Path(sys.argv[1]).resolve()
    c = json.loads(cpath.read_text(encoding="utf-8"))
    th = dict(DEFAULT_THEME)
    theme_base = cpath.parent
    if sys.argv[2] != "-" and Path(sys.argv[2]).exists():
        tp = Path(sys.argv[2]).resolve()
        th.update({k: v for k, v in json.loads(tp.read_text(encoding="utf-8")).items() if v not in (None, "")})
        theme_base = tp.parent
    out_dir = Path(sys.argv[3]); out_dir.mkdir(parents=True, exist_ok=True)

    meta = "".join(f"<div><b>{esc(k)}</b>{esc(v)}</div>" for k, v in (c.get("meta") or {}).items() if v)
    summary = ""
    if c.get("summary"):
        summary = f'<section class="summary"><b>{esc(c.get("summary_title", "בקצרה"))}</b>{mark(txt(c["summary"]))}</section>'
        check_rules("בקצרה", txt(c["summary"]), "text")
    problem = render_problem(c["problem"]) if c.get("problem") else ""
    if not c.get("problem"):
        warnings.append("אין פתיחה (problem) - המסמך צריך להיפתח בבעיה של הלקוח, במילים ובמספרים שלו")
    body_blocks = [b for b in c.get("blocks", []) if b.get("type") not in ("next", "approval")]
    blocks = "\n".join(render_block(i + 1, b) for i, b in enumerate(body_blocks))
    nxt = [b for b in c.get("blocks", []) if b.get("type") == "next"]
    if nxt:
        blocks += "\n" + render_block(0, nxt[0])
    appr = [b for b in c.get("blocks", []) if b.get("type") == "approval"]
    if appr:
        titles = [b.get("title", "") for b in c.get("blocks", [])]
        for b in c.get("blocks", []):
            if b.get("type") == "out" and b.get("limits"):
                titles += [b.get("limits_label", "מה שסיכמנו, בדיוק"), b.get("items_label", "לא כלול")]
        blocks += "\n" + render_approval(appr[0], titles)
    else:
        warnings.append("אין בלוק אישור (approval) בסוף המסמך")

    brand = th.get("brand") or "העסק שלך"
    doc_type = c.get("doc_type", "מסמך אפיון")
    fill = {**{k: str(th.get(k, "")) for k in DEFAULT_THEME},
            "brand": esc(brand), "logo": logo_tag(th.get("logo"), theme_base),
            "doc_type": esc(doc_type), "title": esc(c.get("title", "")), "subtitle": mark(c.get("subtitle", "")),
            "meta": meta, "problem": problem, "summary": summary, "blocks": blocks,
            "footer_text": f"{brand} · {doc_type} · {c.get('footer_note', '')}".rstrip(" ·").replace('"', "'")}
    s = TPL.read_text(encoding="utf-8")
    for k, v in fill.items():
        s = s.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{\w+\}\}", s)
    (out_dir / "spec.html").write_text(s, encoding="utf-8")

    md, total, with_src, no_src = sources_md(c)
    (out_dir / "sources.md").write_text(md, encoding="utf-8")
    gm = gaps_md(c)
    if gm:
        (out_dir / "internal-gaps.md").write_text(gm, encoding="utf-8")

    words = len(re.sub(r"<[^>]+>", " ", s[s.index("<main"):]).split())
    n_ideas = sum(len(b.get("items", [])) for b in c.get("blocks", []) if b.get("type") == "ideas")
    n_open = sum(len(b.get("items", [])) for b in c.get("blocks", []) if b.get("type") == "open")
    print(f"OK {out_dir / 'spec.html'} · {words} מילים · {len(c.get('blocks', []))} סעיפים")
    print(f"מקורות: {with_src}/{total} שורות עם ציטוט מהפגישה · רעיונות להמשך: {n_ideas} · פתוח לבירור: {n_open}")
    if gm:
        print(f"פנימי: {out_dir / 'internal-gaps.md'} · {len(c['internal_gaps'].get('questions', []))} שאלות לפני הצעת המחיר (לא ב-PDF)")
    for x in no_src:
        print(f"⚠️ בלי מקור: {x}")
    for w in warnings:
        print(f"⚠️ {w}")
    if left:
        print(f"⚠️ לא מולאו: {left}")


if __name__ == "__main__":
    main()
