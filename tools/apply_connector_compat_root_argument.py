from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "scripts" / "windows" / "Deployment-Agent.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-connector-compat-root-argument.yml"
SELF = Path(__file__).resolve()

text = AGENT.read_text(encoding="utf-8-sig")
identifier = 'if ($deploymentId -eq "connector-acceptance-run-20260725") {'
start = text.index(identifier)
end = text.index('            & powershell.exe -NoLogo', start)
block = text[start:end]

if '"-ProjectRoot", $ProjectRoot' not in block:
    old = '                    "-SetadPages", "2",\n                    "-AgentRoot", $AgentRoot\n'
    new = '                    "-SetadPages", "2",\n                    "-AgentRoot", $AgentRoot,\n                    "-ProjectRoot", $ProjectRoot\n'
    if old not in block:
        raise RuntimeError("Compatibility acceptance argument block was not found")
    block = block.replace(old, new, 1)
    text = text[:start] + block + text[end:]
    AGENT.write_text(text, encoding="utf-8-sig")

for temporary in (WORKFLOW, SELF):
    if temporary.exists():
        temporary.unlink()
