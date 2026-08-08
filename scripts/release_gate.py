from pathlib import Path
import ast
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def fail(msg):
    print(f"FAIL: {msg}")
    raise SystemExit(1)

# Python syntax gate.
files = [p for p in ROOT.rglob('*.py') if '.git' not in p.parts and '__pycache__' not in p.parts]
for p in files:
    try:
        ast.parse(p.read_text(encoding='utf-8'))
    except SyntaxError as exc:
        fail(f"Python syntax error in {p}: {exc}")

# Migration dependency graph gate.
nodes = set(); deps = {}
for p in ROOT.glob('*/migrations/*.py'):
    if p.name == '__init__.py':
        continue
    tree = ast.parse(p.read_text(encoding='utf-8'))
    values = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == 'dependencies':
                    try: values = ast.literal_eval(n.value)
                    except Exception: values = []
    node = (p.parent.parent.name, p.stem); nodes.add(node); deps[node] = values
for node, values in deps.items():
    for dep in values:
        if isinstance(dep, tuple) and len(dep) == 2 and dep not in nodes and dep[0] != '__setting__':
            fail(f"Missing migration dependency {dep} referenced by {node}")
state = {}
def visit(n):
    state[n] = 1
    for dep in deps.get(n, []):
        if dep not in nodes:
            continue
        if state.get(dep) == 1:
            fail(f"Migration cycle involving {n} and {dep}")
        if state.get(dep, 0) == 0:
            visit(dep)
    state[n] = 2
for n in nodes:
    if state.get(n, 0) == 0:
        visit(n)

# Template block gate.
opens = {'if':'endif','for':'endfor','block':'endblock','with':'endwith','comment':'endcomment','filter':'endfilter','spaceless':'endspaceless','autoescape':'endautoescape','verbatim':'endverbatim'}
for p in ROOT.rglob('*.html'):
    stack=[]
    for m in re.finditer(r'{%\s*(\w+)', p.read_text(encoding='utf-8')):
        tag=m.group(1)
        if tag in opens: stack.append(tag)
        elif tag.startswith('end'):
            if not stack or opens[stack[-1]] != tag:
                fail(f"Template block mismatch in {p}: {tag}")
            stack.pop()
    if stack:
        fail(f"Unclosed template blocks in {p}: {stack}")

# Required release files.
required = [
    'calendar_app/models.py', 'calendar_app/views.py', 'calendar_app/services.py',
    'calendar_app/tests.py', 'calendar_app/management/commands/process_calendar_approvals.py',
    'delivery/migrations/0009_milestone_modalities.py',
    'tenants/migrations/0011_team_manager.py', 'tenants/migrations/0012_leave_approval_settings.py',
    '.github/workflows/epms-calendar-validation.yml', 'CALENDAR_DEPLOYMENT.md',
]
for item in required:
    if not (ROOT / item).exists():
        fail(f"Missing required release file: {item}")

print(f"RELEASE_GATE_OK python_files={len(files)} migrations={len(nodes)} templates_checked")
