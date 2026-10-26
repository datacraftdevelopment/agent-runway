#!/usr/bin/env python3
"""notes-html.py <release-notes/VERSION.md> [version]: the version's notes as a small HTML page for Sparkle's update
window (the appcast item's <description>). The same file What's New shows: front matter dropped, `### ` headings,
`- ` bullets and plain paragraphs, `code` and **bold** inline. Styled to sit in the update window in light and dark.
Stdlib only."""

import html
import re
import sys

STYLE = """<style>
:root { color-scheme: light dark; }
body { font: 13px/1.45 -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif; margin: 12px 14px;
       color: #1d1d1f; background: transparent; }
h2 { font-size: 15px; margin: 0 0 8px; }
h3 { font-size: 13px; margin: 14px 0 4px; }
ul { margin: 0; padding-left: 18px; }
li { margin: 0 0 6px; }
p { margin: 0 0 8px; }
code { font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; background: rgba(127, 127, 127, 0.15);
       padding: 1px 4px; border-radius: 4px; }
@media (prefers-color-scheme: dark) { body { color: #f2f2f2; } }
</style>"""


def inline(text):
    out = html.escape(text, quote=False)
    out = re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', out)


def render(text, version=None):
    lines = text.splitlines()
    if lines and lines[0].strip() == '---':                       # front matter (big: true) is for the app only
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == '---'), None)
        if end is not None:
            lines = lines[end + 1:]
    parts = [STYLE]
    if version:
        parts.append(f'<h2>Runway {html.escape(version)}</h2>')
    in_list = False
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
    # It goes inside <![CDATA[...]]>, which can't hold "]]>".
    return '\n'.join(parts).replace(']]>', ']]&gt;')


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as f:
        print(render(f.read(), sys.argv[2] if len(sys.argv) > 2 else None))
