"""glasslab inspect: open one hidden-UI state (trigger label regex) and dump its layer: element chain + computed paint.
  python3 -m tools.glasslab.inspect_layer URL LABEL_RE [MODE]   (debug aid for fixing a failing explored state)"""
import asyncio, json, re, sys

from . import cli, explore, lab

DUMP = """(sel => { const root = document.querySelector(sel); const out = [];
  const d = (e, depth) => { if (depth > 6 || out.length > 60) return; const cs = getComputedStyle(e), r = e.getBoundingClientRect();
    if (r.width * r.height > 200) out.push('  '.repeat(depth) + e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + [...e.classList].slice(0, 3).map(c => '.' + c).join('')
      + (e.getAttribute('role') ? `[role=${e.getAttribute('role')}]` : '') + ` ${cs.position} bg=${cs.backgroundColor}${cs.backgroundImage !== 'none' ? ' bi=' + cs.backgroundImage.slice(0, 90) : ''} fg=${cs.color} op=${cs.opacity} ${Math.round(r.width)}x${Math.round(r.height)}`);
    for (const c of e.children) d(c, depth + 1); };
  const anc = []; for (let e = root.parentElement; e && anc.length < 6; e = e.parentElement) anc.push(e.tagName.toLowerCase() + [...e.classList].slice(0, 3).map(c => '.' + c).join('') + (e.getAttribute('role') ? '[role=' + e.getAttribute('role') + ']' : '') + (e.getAttribute('jsname') ? '[jsname=' + e.getAttribute('jsname') + ']' : '') + ' ' + getComputedStyle(e).position + ' z=' + getComputedStyle(e).zIndex + ' bg=' + getComputedStyle(e).backgroundColor + ' sh=' + (getComputedStyle(e).boxShadow !== 'none'));
  d(root, 0); return JSON.stringify({ ancestors: anc, tree: out }); })(%s)"""


async def main(url, label, mode="dark"):
    async with lab.session(cli.xpi(False), "/tmp/inspect.log") as pg:
        await pg.goto(url, 7)
        await pg.glass(mode, 0.45)
        for t in await pg.probe("triggers", explore.DANGER, 30):
            if re.search(label, t["label"], re.I):
                await pg.probe("layers", "mark")
                await explore.activate(pg, t)
                for l in await pg.probe("layers", "diff") or []:
                    d = json.loads(await pg.eval(DUMP % json.dumps(l["sel"])))
                    print(f"== {t['label']} → {l['sel']} panel {l['panel']}\nancestors: {d['ancestors']}\n" + "\n".join(d["tree"]))
                return
        print("no trigger matches", label)




GRADIENTS = """JSON.stringify([...document.querySelectorAll('body *')].filter(e => { const s = getComputedStyle(e), r = e.getBoundingClientRect();
  return s.backgroundImage.includes('gradient') && r.width * r.height > 500 && r.bottom > 0 && r.top < innerHeight; })
  .map(e => e.tagName.toLowerCase() + [...e.classList].slice(0, 3).map(c => '.' + c).join('') + (e.getAttribute('jsname') ? `[jsname=${e.getAttribute('jsname')}]` : '')
    + ' ' + getComputedStyle(e).backgroundImage.slice(0, 120)).slice(0, 20))"""


async def gradients(url, mode="dark"):
    async with lab.session(cli.xpi(False), "/tmp/inspect.log") as pg:
        await pg.goto(url, 7)
        await pg.glass(mode, 0.45)
        print("\n".join(json.loads(await pg.eval(GRADIENTS))))


ANCESTRY = """(sel => JSON.stringify([...document.querySelectorAll(sel)].slice(0, 2).map(e => { const a = [];
  for (let x = e; x && x !== document.body; x = x.parentElement) a.push(x.tagName.toLowerCase() + (x.id ? '#' + x.id : '')
    + [...x.classList].slice(0, 2).map(c => '.' + c).join('') + (x.getAttribute('role') ? `[role=${x.getAttribute('role')}]` : '')
    + (x.getAttribute('aria-label') ? `[aria-label="${x.getAttribute('aria-label').slice(0, 30)}"]` : ''));
  return a; })))(%s)"""


async def ancestry(url, sel):
    async with lab.session(cli.xpi(False), "/tmp/inspect.log") as pg:
        await pg.goto(url, 7)
        for chain in json.loads(await pg.eval(ANCESTRY % json.dumps(sel))):
            print(" < ".join(chain))


if __name__ == "__main__":
    cmd = {"--gradients": gradients, "--ancestry": ancestry}.get(sys.argv[1])
    asyncio.run(cmd(*sys.argv[2:]) if cmd else main(*sys.argv[1:]))
