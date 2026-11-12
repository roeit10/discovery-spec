#!/usr/bin/env python3
"""Convert spec.html into an editable version with a PDF-export button and autosave.

Injects:
- * { print-color-adjust: exact !important } - forces Chrome to print colors
- <main contenteditable> - every text in the document is editable in the browser
- Floating "📄 הפק PDF" button (awaits document.fonts.ready, then window.print())
- Tip overlay with edit + PDF-color instructions
- Print CSS that hides the editor UI when the user hits Cmd+P / button

Usage:
  python3 make_editable.py <spec.html> <spec.editable.html>
"""
import re
import shutil
import sys
from pathlib import Path


EDITOR_CSS = """
/* ============== EDITOR UI (screen only) ============== */
[contenteditable="true"]:focus{outline:2px dashed var(--primary);outline-offset:2px}
[contenteditable="true"] li:hover,[contenteditable="true"] p:hover{background:rgba(255,224,138,.25)}
[contenteditable="true"]:focus:hover{background:transparent}

.editor-toolbar{
  position:fixed;top:14px;left:14px;z-index:9999;
  display:flex;gap:10px;align-items:stretch;
  font-family:var(--font-head);
}
.tip{
  background:var(--ink);color:#fff;
  padding:10px 14px;font-weight:700;font-size:12px;
  border:3px solid var(--ink);box-shadow:0 2px 10px rgba(0,0,0,.2);border-radius:6px;
  max-width:260px;line-height:1.4;
}
.tip b{color:#FFE08A;font-weight:800}
.export-btn{
  background:var(--primary);color:var(--primary-ink);
  border:0;border-radius:6px;box-shadow:0 2px 10px rgba(0,0,0,.2);
  padding:14px 20px;font-weight:900;font-size:15px;
  cursor:pointer;font-family:var(--font-head);
  display:flex;align-items:center;gap:8px;
}
.export-btn:hover{filter:brightness(1.1)}


@media print{
  .editor-toolbar{display:none!important}
  [contenteditable="true"]:focus,[contenteditable="true"]:hover{outline:none!important;background:transparent!important}
}
"""

EDITOR_TOOLBAR = """
<div class="editor-toolbar" contenteditable="false">
  <div class="tip">
    <b>עריכה:</b> קליק על כל טקסט וערוך.<br>
    <b>שמירה כ-PDF:</b> לחץ על הכפתור ←<br>
    <b>אישור:</b> כפתור "העתקה" בסוף המסמך מעתיק את טקסט האישור.<br>
    אם הצבעים נעלמו: ב-Chrome <b>More settings → Color: Color</b>.
  </div>
  <button class="export-btn" onclick="(async()=>{await document.fonts.ready;window.print();})()">📄 הפק PDF</button>
</div>
"""

# Autosave block - saves contenteditable edits to localStorage on every change,
# adds a "הורד HTML מלא" button to export the filled HTML, hides in print.
# Source of truth: roei-proposal/references/aios-discovery.example.html L551-647
AUTOSAVE_BLOCK = """
<!-- AUTOSAVE-INJECT-START v1 -->
<style>
  .__autosave-bar{position:fixed;top:14px;right:14px;z-index:99999;display:flex;gap:8px;align-items:center;font-family:var(--font);font-weight:500;font-size:13px;direction:rtl;background:rgba(255,255,255,.95);border:1px solid #ddd;border-radius:8px;padding:6px 10px;box-shadow:0 2px 8px rgba(0,0,0,.08);user-select:none}
  .__autosave-bar button{cursor:pointer;border:1px solid #333;background:#fff;border-radius:6px;padding:4px 10px;font-size:12px;font-family:var(--font);font-weight:500}
  .__autosave-bar button:hover{background:#f3f3f3}
  .__autosave-status{color:#666;min-width:90px}
  .__autosave-status.saved{color:#0a7d32}
  .__autosave-status.dirty{color:#b85c00}
  @media print{.__autosave-bar{display:none!important}}
</style>
<div class="__autosave-bar" id="__autosaveBar" contenteditable="false">
  <span class="__autosave-status saved" id="__autosaveStatus">נשמר ✓</span>
  <button type="button" onclick="window.__autosaveDownload()">הורד HTML מלא</button>
  <button type="button" onclick="window.__autosaveClear()" title="מחק את התוכן השמור בדפדפן">איפוס</button>
</div>
<script>
(function(){
  if(window.__autosaveLoaded) return;
  window.__autosaveLoaded = true;
  var KEY = '__autosave::' + (document.title || 'untitled') + '::' + (location.pathname || '');
  var statusEl = document.getElementById('__autosaveStatus');
  var dirty = false, saveTimer = null;
  function setStatus(text, cls){ statusEl.textContent = text; statusEl.className = '__autosave-status ' + cls; }
  function editables(){ return document.querySelectorAll('[contenteditable="true"], [contenteditable=""]'); }
  function snapshot(){
    var data = {};
    editables().forEach(function(el, i){
      var k = el.id || el.getAttribute('data-key') || ('__ce_' + i);
      data[k] = el.innerHTML;
    });
    return data;
  }
  function save(){
    try { localStorage.setItem(KEY, JSON.stringify({ts: Date.now(), data: snapshot()})); setStatus('נשמר ✓', 'saved'); dirty = false; }
    catch(e){ setStatus('שגיאה בשמירה', 'dirty'); }
  }
  function restore(){
    try {
      var raw = localStorage.getItem(KEY); if(!raw) return;
      var obj = JSON.parse(raw); if(!obj || !obj.data) return;
      editables().forEach(function(el, i){
        var k = el.id || el.getAttribute('data-key') || ('__ce_' + i);
        if(obj.data[k] !== undefined && obj.data[k] !== '') el.innerHTML = obj.data[k];
      });
      var d = new Date(obj.ts); setStatus('שוחזר ' + d.toLocaleTimeString('he-IL'), 'saved');
    } catch(e){}
  }
  function markDirty(){ dirty = true; setStatus('עורך…', 'dirty'); clearTimeout(saveTimer); saveTimer = setTimeout(save, 600); }
  window.__autosaveDownload = function(){
    var doc = document.documentElement.cloneNode(true);
    var bar = doc.querySelector('#__autosaveBar'); if(bar) bar.remove();
    var html = '<!doctype html>\\n<html lang="he" dir="rtl">\\n' + doc.innerHTML + '\\n</html>';
    var blob = new Blob([html], {type:'text/html;charset=utf-8'});
    var a = document.createElement('a');
    var stamp = new Date().toISOString().slice(0,16).replace('T','_').replace(':','-');
    var base = (document.title || 'document').replace(/[\\/\\\\?%*:|\"<>]/g,'-');
    a.href = URL.createObjectURL(blob);
    a.download = base + ' · ' + stamp + '.html';
    document.body.appendChild(a); a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 500);
  };
  window.__autosaveClear = function(){
    if(!confirm('למחוק את התוכן השמור בדפדפן? (לא ימחק את הקובץ עצמו)')) return;
    localStorage.removeItem(KEY); setStatus('נמחק', 'dirty');
  };
  document.addEventListener('DOMContentLoaded', function(){
    restore();
    editables().forEach(function(el){ el.addEventListener('input', markDirty); el.addEventListener('blur', save); });
    window.addEventListener('beforeunload', function(e){ if(dirty){ save(); } });
    window.addEventListener('keydown', function(e){
      if((e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'S')){
        e.preventDefault(); save(); window.__autosaveDownload();
      }
    });
  });
})();
</script>
<!-- AUTOSAVE-INJECT-END v1 -->
"""


def make_editable(src_path: Path, dst_path: Path) -> None:
    shutil.copy(src_path, dst_path)
    content = dst_path.read_text(encoding="utf-8")

    # 1. Force print colors on every element
    content = content.replace(
        "</style>",
        "*{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}\n</style>",
        1,
    )

    # 2. Update <title> with editor suffix
    content = re.sub(
        r"<title>(.*?)</title>",
        r"<title>\1 - עורך + הפקת PDF</title>",
        content,
        count=1,
    )

    # 3. Append editor CSS just before </style>
    content = content.replace("</style>", EDITOR_CSS + "\n</style>", 1)

    # 4. Insert floating toolbar + make the document (not the toolbar) editable
    content = content.replace("<body>", "<body>\n" + EDITOR_TOOLBAR, 1)
    content = content.replace('<main class="doc">', '<main class="doc" contenteditable="true" id="spec-doc">', 1)

    # 5. Inject autosave block before </body> (mandatory for editable HTML)
    if "AUTOSAVE-INJECT-START" not in content:
        content = content.replace("</body>", AUTOSAVE_BLOCK + "\n</body>", 1)

    dst_path.write_text(content, encoding="utf-8")
    print(f"wrote {dst_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: make_editable.py <input.html> <output.editable.html>", file=sys.stderr)
        sys.exit(2)
    make_editable(Path(sys.argv[1]), Path(sys.argv[2]))
