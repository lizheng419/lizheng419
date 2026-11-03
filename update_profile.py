"""Generate a public-only GitHub profile using Python's standard library.

Commits and line changes count this author's commits on the default branch
of owned, public, non-fork repositories; they are not contribution-graph totals.
An API failure aborts the update and preserves the last published README.
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


def render(stats, art):
    # GitHub image embeds cannot expose SVG links; native preformatted HTML can.
    def kv(key, value, url=None):
        value = str(value)
        dots = '.' * max(1, 47 - len(key) - len(value) - 3)
        label = html.escape(value)
        if url:
            label = f'<a href="{html.escape(url, quote=True)}">{label}</a>'
        return f'<b>{html.escape(key)}:</b> {dots} {label}'

    lines = art.strip('\n').splitlines()
    if not lines or len(lines) > 26 or max(map(len, lines)) > 46:
        raise ValueError('ASCII portrait must be at most 46 columns by 26 rows')
    n = lambda value: f'{value:,}'
    rows = [
        f'<b>{USER}@github</b>',
        '-' * 47,
        kv('Name', 'Roccat'),
        kv('Role', 'AI Application Engineer'),
        kv('Host', 'MacBook Pro'),
        kv('Focus', 'RAG / Agents / Enterprise AI'),
        kv('Passions', 'Gaming / Basketball / AI apps'),
        '',
        'Less AI theater. More working systems.',
        '',
        '<b>- Contact ' + '-' * 37 + '</b>',
        kv('GitHub', 'github.com/lizheng419', 'https://github.com/lizheng419'),
        kv('X', '@Roccat_fi', 'https://x.com/Roccat_fi'),
        '',
        '<b>' + '- GitHub Stats / Public '.ljust(47, '-') + '</b>',
        kv('Repositories', f'{n(stats["repos"])} ({n(stats["forks"])} forks)'),
        kv('Stars received', n(stats['stars'])),
        kv('Followers', n(stats['followers'])),
        kv('Authored commits*', n(stats['commits'])),
        kv('Code changes*', '+' + n(stats['added']) + ' / -' + n(stats['deleted'])),
        '* Own non-forks, default branches only.',
        'Updated ' + stats['updated'] + ' UTC',
    ]
    height = max(len(lines), len(rows))
    lines = [''] * ((height - len(lines)) // 2) + lines
    lines += [''] * (height - len(lines))
    rows += [''] * (height - len(rows))
    body = '\n'.join((html.escape(left.ljust(46)) + '   ' + right).rstrip()
                     for left, right in zip(lines, rows))
    return '<pre>' + body + '</pre>\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, help='Render a previously verified public-statistics JSON snapshot')
    args = parser.parse_args()
    stats = json.loads(args.snapshot.read_text()) if args.snapshot else fetch_stats()
    art = (ROOT / 'img/avatar.txt').read_text()
    document = render(stats, art)
    target = ROOT / 'README.md'
    temporary = target.with_suffix('.md.tmp')
    temporary.write_text(document, encoding='utf-8')
    temporary.replace(target)
    print(json.dumps(stats, sort_keys=True))


if __name__ == '__main__':
    main()
