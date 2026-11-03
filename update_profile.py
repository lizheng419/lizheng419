"""Generate a public-only GitHub profile using Python's standard library.

Commits and line changes count this author's commits on the default branch
of owned, public, non-fork repositories; they are not contribution-graph totals.
An API failure aborts the update and preserves the last published images.
"""
import argparse
import html
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER = 'lizheng419'
ROOT = Path(__file__).resolve().parent
PALETTES = {
    'dark': dict(bg='#0d1117', border='#30363d', art='#8b949e',
                 title='#58a6ff', key='#ffa657', value='#c9d1d9',
                 dots='#484f58', green='#3fb950', red='#f85149'),
    'light': dict(bg='#ffffff', border='#d0d7de', art='#57606a',
                  title='#0969da', key='#953800', value='#24292f',
                  dots='#afb8c1', green='#1a7f37', red='#cf222e'),
}


def api(path):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': USER + '-profile'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = Request('https://api.github.com' + path, headers=headers)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def pages(path):
    separator = '&' if '?' in path else '?'
    page = 1
    while True:
        batch = api(f'{path}{separator}per_page=100&page={page}')
        yield from batch
        if len(batch) < 100:
            break
        page += 1


def scan_repo(name):
    count = added = deleted = 0
    try:
        commits = list(pages(f'/repos/{USER}/{name}/commits?' + urlencode({'author': USER})))
    except HTTPError as error:
        if error.code == 409:  # GitHub reports an empty Git repository as a conflict.
            return 0, 0, 0
        raise
    for commit in commits:
        stats = api(f'/repos/{USER}/{name}/commits/{commit["sha"]}')['stats']
        count += 1
        added += stats['additions']
        deleted += stats['deletions']
    return count, added, deleted


def fetch_stats():
    user = api(f'/users/{USER}')
    repos = [repo for repo in pages(f'/users/{USER}/repos?type=owner') if not repo['private']]
    originals = [repo['name'] for repo in repos if not repo['fork']]
    with ThreadPoolExecutor(max_workers=4) as pool:
        totals = list(pool.map(scan_repo, originals))
    return dict(
        repos=len(repos), forks=len(repos) - len(originals),
        stars=sum(repo['stargazers_count'] for repo in repos), followers=user['followers'],
        commits=sum(row[0] for row in totals), added=sum(row[1] for row in totals),
        deleted=sum(row[2] for row in totals), updated=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    )


def render(theme, stats, art):
    p = PALETTES[theme]
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="840" height="500" viewBox="0 0 840 500" '
        'font-family="Consolas, Menlo, monospace" font-size="13px" role="img" aria-labelledby="title desc">',
        '<title id="title">Roccat — GitHub profile</title>',
        '<desc id="desc">AI Application Engineer. MacBook Pro. Gaming, basketball and AI apps. '
        'X: Roccat_fi. Statistics cover public repositories only. Commits and line changes '
        'cover authored commits on default branches of owned non-fork repositories.</desc>',
        f'<rect x="0.5" y="0.5" width="839" height="499" rx="10" fill="{p["bg"]}" stroke="{p["border"]}"/>',
    ]

    def text(x, y, segments):
        spans = ''.join(f'<tspan fill="{p[color]}">{html.escape(str(value))}</tspan>'
                        for value, color in segments)
        node = f'<text x="{x}" y="{y}" xml:space="preserve">{spans}</text>'
        out.append(node)

    def kv(key, value):
        value = str(value)
        dots = '.' * max(1, 54 - len(key) - len(value) - 3)
        return [(key + ': ', 'key'), (dots + ' ', 'dots'), (value, 'value')]

    lines = art.strip('\n').splitlines()
    if not lines or len(lines) > 26 or max(map(len, lines)) > 46:
        raise ValueError('ASCII portrait must be at most 46 columns by 26 rows')
    top = 40 + (460 - len(lines) * 15) / 2
    for index, line in enumerate(lines):
        text(10, top + index * 15, [(line, 'art')])

    n = lambda value: f'{value:,}'
    rows = [
        [(USER + '@github', 'title')],
        [('─' * 54, 'dots')],
        kv('Name', 'Roccat'),
        kv('Role', 'AI Application Engineer'),
        kv('Host', 'MacBook Pro'),
        kv('Focus', 'RAG / Agents / Enterprise AI'),
        kv('Passions', 'Gaming / Basketball / AI apps'),
        [],
        [('Less AI theater. More working systems.', 'value')],
        [],
        [('─ Contact ' + '─' * 44, 'title')],
        kv('GitHub', 'github.com/lizheng419'),
        kv('X', '@Roccat_fi'),
        [],
        [('─ GitHub Stats · Public ' + '─' * 30, 'title')],
        kv('Repositories', f'{n(stats["repos"])} ({n(stats["forks"])} forks)'),
        kv('Stars received', n(stats['stars'])),
        kv('Followers', n(stats['followers'])),
        kv('Authored commits*', n(stats['commits'])),
        [('Code changes*: ', 'key'), ('+' + n(stats['added']), 'green'),
         (' / ', 'dots'), ('-' + n(stats['deleted']), 'red')],
        [('* Own non-forks, default branches only.', 'art')],
        [('Updated ' + stats['updated'] + ' UTC', 'art')],
    ]
    for index, row in enumerate(rows):
        text(390, 45 + index * 21, row)
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, help='Render a previously verified public-statistics JSON snapshot')
    args = parser.parse_args()
    stats = json.loads(args.snapshot.read_text()) if args.snapshot else fetch_stats()
    art = (ROOT / 'img/avatar.txt').read_text()
    images = {theme: render(theme, stats, art) for theme in PALETTES}
    for theme, svg in images.items():
        target = ROOT / 'img' / f'{theme}.svg'
        temporary = target.with_suffix('.svg.tmp')
        temporary.write_text(svg, encoding='utf-8')
        temporary.replace(target)
    print(json.dumps(stats, sort_keys=True))


if __name__ == '__main__':
    main()
