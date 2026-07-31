from pathlib import Path

path = Path("app/procurement/ProcurementAnalysisCenterPanel.tsx")
text = path.read_text(encoding="utf-8")
old = 'useEffect(()=>{void load();const timer=window.setInterval(()=>void load(),10000);return()=>window.clearInterval(timer);},[load]);'
new = 'useEffect(()=>{const initial=window.setTimeout(()=>void load(),0);const timer=window.setInterval(()=>void load(),10000);return()=>{window.clearTimeout(initial);window.clearInterval(timer);};},[load]);'
if old not in text:
    raise SystemExit("Expected effect source not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
