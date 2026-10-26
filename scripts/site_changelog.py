#!/usr/bin/env python3
"""site_changelog.py: writes site/changelog.html from app/release-notes/<version>.md, the same files What's New,
Sparkle's update window and the GitHub release show, so the changelog is never written twice.

Page chrome (head, styles, nav, footer) is copied from site/skills.html. A version newer than app/VERSION is shown
as the next update. A note's front matter may carry `date: YYYY-MM-DD`. Stdlib only.

    python3 scripts/site_changelog.py           # write the page
    python3 scripts/site_changelog.py --check   # exit 1 if the page is out of date
"""

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / 'app' / 'release-notes'
SITE = ROOT / 'site'
RELEASES = 'https://github.com/datacraftdevelopment/agent-runway/releases'

STYLE = """.log{display:grid;gap:0}
.release{display:grid;grid-template-columns:200px 1fr;gap:24px;padding-block:32px;border-top:1px solid var(--line)}
.release:first-child{border-top:0}
.release .ver{display:grid;gap:6px;align-content:start}
.release .ver h2{font-size:34px}
.release .when{font:600 11px/1.4 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.release.next .when{color:var(--accent)}
.release .body{min-width:0;display:grid;gap:12px;align-content:start}
.release h3{font-size:21px;margin-top:6px}
.release ul{margin:0;padding-left:20px;display:grid;gap:8px}
.release code{font:14px var(--mono);background:var(--surface);border:1px solid var(--line);border-radius:5px;padding:0 5px}
.release .gh{font-size:15px;color:var(--muted)}
@media (max-width:640px){.release{grid-template-columns:1fr;gap:12px}}"""


def version_key(v):
    return tuple(int(p) for p in v.split('.'))


def inline(text):
    out = html.escape(text, quote=False)
    out = re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', out)


def parse(text):
    """(front matter dict, body lines)."""
    lines, meta = text.splitlines(), {}
    if lines and lines[0].strip() == '---':
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == '---'), None)
        if end is not None:
            for l in lines[1:end]:
                k, _, v = l.partition(':')
                meta[k.strip()] = v.strip()
            lines = lines[end + 1:]
    return meta, lines


def body_html(lines):
    parts, in_list = [], False
    for raw in lines:
        line = raw.strip()
        bullet = line.startswith(('- ', '* '))
        if in_list and not bullet:
            parts.append('</ul>')
            in_list = False
        if not line:
            continue
        if line.startswith('#'):
            parts.append(f'<h3>{inline(line.lstrip("#").strip())}</h3>')
        elif bullet:
            if not in_list:
                parts.append('<ul>')
                in_list = True
            parts.append(f'<li>{inline(line[2:])}</li>')
        else:
            parts.append(f'<p>{inline(line)}</p>')
    if in_list:
        parts.append('</ul>')
    return '\n'.join(parts)


def releases():
    current = version_key((ROOT / 'app' / 'VERSION').read_text().strip())
    found = []
    for f in NOTES.glob('*.md'):
        if not re.fullmatch(r'\d+(\.\d+)*', f.stem):
            continue
        meta, lines = parse(f.read_text())
        found.append((f.stem, meta.get('date', ''), version_key(f.stem) > current, lines))
    return sorted(found, key=lambda r: version_key(r[0]), reverse=True)


def render():
    shell = (SITE / 'skills.html').read_text()
    head, rest = shell.split('</style>', 1)
    head = re.sub(r'<title>.*?</title>', '<title>Changelog · Agent Runway</title>', head)
    head = re.sub(r'(<meta name="description" content=")[^"]*', r'\1What changed in each version of Agent Runway.', head)
    head = re.sub(r'(<meta property="og:title" content=")[^"]*', r'\1Agent Runway changelog', head)
    nav = rest[rest.index('<body>'):rest.index('</nav>') + len('</nav>')]
    footer = rest[rest.index('<footer>'):]

    items = []
    for version, date, upcoming, lines in releases():
        if upcoming:
            when = 'Next update'
            link = ''
        else:
            when = date or 'Released'
            link = f'<p class="gh"><a href="{RELEASES}/tag/v{version}">Release on GitHub</a></p>'
        items.append(f"""<article class="release{' next' if upcoming else ''}" id="v{version}">
  <div class="ver"><h2>{version}</h2><span class="when">{html.escape(when)}</span></div>
  <div class="body">
{body_html(lines)}
{link}
  </div>
</article>""")

    return f"""{head}{STYLE}
</style>
</head>
{nav}

<header class="page-head">
  <div class="wrap narrow">
    <p class="eyebrow">Changelog</p>
    <h1>What's new in Runway</h1>
    <p class="lede">Every version, newest first. The app shows the same notes in What's New after it updates itself.</p>
  </div>
  <div class="runway-line" style="margin-top:48px"></div>
</header>

<main>
<section style="border-top:0">
  <div class="wrap narrow log">
{chr(10).join(items)}
  </div>
</section>
</main>

{footer}"""


def main(argv):
    page, out = render(), SITE / 'changelog.html'
    if '--check' in argv:
        if not out.exists() or out.read_text() != page:
            print('site/changelog.html is out of date: run python3 scripts/site_changelog.py')
            return 1
        return 0
    out.write_text(page)
    print(f'wrote {out.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
