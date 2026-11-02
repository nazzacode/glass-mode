"""glasslab — liquid-glass site styles toolkit (docs/GLASS.md).

  ./glasslab add NAME URL [--agent] [--act JS] [--content-first] [--dark-only]  URL → verified site style, one command
  ./glasslab test [FILTER] [--save-baseline] [--compare] [--no-explore]  readability + unity: screens + their hidden UI
  ./glasslab discover URL [--act JS]                                  what actually paints a site (causal tokens)
  ./glasslab new-site NAME URL [--content-first] [--dark-only]        scaffold style + registry + test screen
  ./glasslab wallpapers DIR|FILE…                                     backdrops + contrast bounds from your wallpapers
  ./glasslab baseline RESULTS.json…                                  merge runs (parallel lab ports) into baseline.json
  ./glasslab report [RUN]                                             local HTML report (default: latest run)
  ./glasslab shots [FILTER] [--out DIR] [--modes dark,light] [--all]  showcase shots; --all: test tiles, every screen + hidden UI
  ./glasslab shots --sweep SCREEN [--modes dark]                      opacity 10→90 % animation (launch GIF)
  ./glasslab shots --strip SCREEN [--modes dark]                      the same screen at 10 / 45 / 90 % (README)
  ./glasslab replay HOST                                              real pages from your Zen cache, for sites that wall the lab
  ./glasslab corpus import|seed|check|list|install [FILTER]           frozen real pages, panels open (recorder: Alt+Shift+R). Local only
  ./glasslab vote [build [FILTER]|results]                            A vs B on frozen pages, localhost, blind (votes in ~/.cache/glasslab/vote)
  ./glasslab site [--run RUN]                                         public site (site/index.html) + README sites table
"""
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = Path.home() / ".cache/glasslab/runs"


def xpi(build):
    if build:
        subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True)
    zips = sorted((ROOT / "builds").glob("*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        raise SystemExit("glasslab: no build in builds/ (npm run build, or pass --build)")
    return zips[-1]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="glasslab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test"); t.add_argument("filter", nargs="?", default="")
    t.add_argument("--save-baseline", action="store_true"); t.add_argument("--compare", action="store_true")
    t.add_argument("--build", action="store_true"); t.add_argument("--out"); t.add_argument("--no-explore", action="store_true")
    g = sub.add_parser("add"); g.add_argument("name"); g.add_argument("url"); g.add_argument("--act")
    g.add_argument("--content-first", action="store_true"); g.add_argument("--dark-only", action="store_true")
    g.add_argument("--agent", action="store_true"); g.add_argument("--rounds", type=int, default=4); g.add_argument("--force", action="store_true")
    d = sub.add_parser("discover"); d.add_argument("url"); d.add_argument("--act"); d.add_argument("--build", action="store_true")
    d.add_argument("--scheme", choices=["dark", "light"], default="dark", help="the site's own theme (prefers-color-scheme)")
    n = sub.add_parser("new-site"); n.add_argument("name"); n.add_argument("url"); n.add_argument("--act")
    n.add_argument("--content-first", action="store_true"); n.add_argument("--dark-only", action="store_true")
    n.add_argument("--force", action="store_true"); n.add_argument("--build", action="store_true")
    w = sub.add_parser("wallpapers"); w.add_argument("paths", nargs="+"); w.add_argument("--blur", type=int, default=22)
    r = sub.add_parser("report"); r.add_argument("run", nargs="?")
    b = sub.add_parser("baseline"); b.add_argument("results", nargs="+")
    s = sub.add_parser("shots"); s.add_argument("filter", nargs="?", default=""); s.add_argument("--out"); s.add_argument("--sweep", metavar="SCREEN"); s.add_argument("--strip", metavar="SCREEN")
    s.add_argument("--modes", default="dark,light"); s.add_argument("--build", action="store_true")
    s.add_argument("--all", action="store_true")
    p = sub.add_parser("site"); p.add_argument("--run"); p.add_argument("--out")
    rp = sub.add_parser("replay"); rp.add_argument("host")
    co = sub.add_parser("corpus"); co.add_argument("action", choices=["import", "seed", "check", "list", "install"]); co.add_argument("filter", nargs="?", default="")
    co.add_argument("--build", action="store_true")
    vo = sub.add_parser("vote"); vo.add_argument("action", nargs="?", choices=["serve", "build", "results"], default="serve"); vo.add_argument("filter", nargs="?", default="")
    vo.add_argument("--build", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "replay":
        from . import replay
        pages = replay.capture(a.host)
        print(f"{len(pages)} pages in {replay.STORE / a.host}:", *pages, sep="\n  ")
        return 0
    if a.cmd == "corpus":
        from . import corpus
        if a.action == "install":
            print(f"recorder → {corpus.install_recorder()} (active from Zen's next start)")
        if a.action == "import":
            print(f"imported {len(corpus.import_inbox())}")
        if a.action == "seed":
            print(f"seeded {len(corpus.seed(xpi(a.build), a.filter))}")
        if a.action == "check":
            rows = corpus.check(xpi(a.build), a.filter)
            print(f"{sum(r['drift'] < 0.05 for r in rows)}/{len(rows)} within 5 % of live")
        if a.action == "list":
            for m in corpus.captures(a.filter):
                print(f"{m['id']:44s} {m['source']:8s} {m.get('drift', -1):6.1%}  {m['url'][:60]}  {m.get('state', '')[:30]}")
        return 0
    if a.cmd == "vote":
        from . import vote
        if a.action == "serve":
            vote.serve()
        if a.action == "build":
            print(f"{len(vote.build(xpi(a.build), a.filter))} pairs")
        if a.action == "results":
            import json
            print(json.dumps(vote.results(), indent=1))
        return 0
    if a.cmd == "test":
        from . import suite
        return suite.main(xpi(a.build), a.filter, a.out, a.save_baseline, a.compare, not a.no_explore)
    if a.cmd == "add":
        from . import pipeline
        return pipeline.add(a.name, a.url, a.act, a.content_first, a.dark_only, a.agent, a.rounds, a.force)
    if a.cmd == "discover":
        from . import discover
        discover.discover(xpi(a.build), a.url, a.act, a.scheme)
    if a.cmd == "new-site":
        from . import discover
        discover.new_site(xpi(a.build), a.name, a.url, a.act, a.content_first, a.dark_only, a.force)
    if a.cmd == "wallpapers":
        from . import wallpapers
        wallpapers.main(a.paths, a.blur)
    if a.cmd == "baseline":
        import json
        from . import suite
        bl = Path(__file__).parent / "baseline.json"
        runs = [json.loads(Path(p).read_text()) for p in a.results]
        bl.write_text(json.dumps(suite.merge_baseline(json.loads(bl.read_text()) if bl.exists() else {}, runs), indent=1) + "\n")
        print(f"baseline: merged {sum(map(len, runs))} rows from {len(runs)} runs")
    if a.cmd == "report":
        from . import report
        run = Path(a.run) if a.run else max(RUNS.iterdir(), key=lambda p: p.stat().st_mtime)
        report.main(run)
    if a.cmd == "shots":
        from . import shots
        if a.strip:
            return shots.main_strip(xpi(a.build), a.strip, a.out, a.modes.split(",")[0])
        if a.sweep:
            return shots.main_sweep(xpi(a.build), a.sweep, a.out, a.modes.split(",")[0])
        return (shots.main_all if a.all else shots.main)(xpi(a.build), a.filter, a.out, a.modes.split(","))
    if a.cmd == "site":
        from . import site
        return site.main(Path(a.run) if a.run else None, Path(a.out) if a.out else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
