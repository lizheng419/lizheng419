"""Generate a public-only GitHub profile using Python's standard library.

Commits and line changes count this author's commits on the default branch
of owned, public, non-fork repositories; they are not contribution-graph totals.
An API failure aborts the update and preserves the last published profile.
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


def render_profile(stats, art):
    lines = art.strip('\n').splitlines()
    if not lines or len(lines) > 26 or max(map(len, lines)) > 46:
        raise ValueError('ASCII portrait must be at most 46 columns by 26 rows')
    palettes = {
        'dark': dict(text='#c9d1d9', muted='#8b949e', title='#58a6ff',
                     key='#ffa657', rule='#30363d', green='#3fb950', red='#f85149'),
        'light': dict(text='#24292f', muted='#57606a', title='#0969da',
                      key='#953800', rule='#d0d7de', green='#1a7f37', red='#cf222e'),
    }
    n = lambda value: f'{value:,}'
    files = {}
    for theme, colors in palettes.items():
        def svg(width, height, content):
            return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                    f'viewBox="0 0 {width} {height}" font-family="Menlo, Consolas, monospace" '
                    'font-size="13">\n' + '\n'.join(content) + '\n</svg>\n')

        def text(x, y, value, color='text', size=13, anchor='start'):
            return (f'<text x="{x}" y="{y}" fill="{colors[color]}" font-size="{size}" '
                    f'text-anchor="{anchor}" xml:space="preserve">{html.escape(str(value))}</text>')

        def kv(y, key, value):
            return (text(12, y, key, 'key') +
                    f'<text x="428" y="{y}" text-anchor="end" fill="{colors["text"]}">'
                    f'{html.escape(str(value))}</text>')

        top = (420 - len(lines) * 15) / 2 + 12
        files[f'img/profile-avatar-{theme}.svg'] = svg(350, 420, [
            text(4, top + i * 15, line, 'muted', 12) for i, line in enumerate(lines)
        ])
        info = [text(12, 24, USER + '@github', 'title', 16),
                f'<path d="M12 38 H428" stroke="{colors["rule"]}"/>']
        for i, (key, value) in enumerate([
            ('Name', 'Roccat'), ('Role', 'AI Application Engineer'), ('Host', 'MacBook Pro'),
            ('Focus', 'RAG / Agents / Enterprise AI'), ('Passions', 'Gaming / Basketball / AI apps'),
        ]):
            info.append(kv(61 + i * 21, key, value))
        info += [text(12, 173, 'Less AI theater. More working systems.', 'muted', 12),
                 text(12, 204, 'Contact', 'title')]
        files[f'img/profile-info-{theme}.svg'] = svg(440, 212, info)
        rows = [text(12, 20, 'GitHub Stats / Public', 'title')]
        for i, (key, value) in enumerate([
            ('Repositories', f'{n(stats["repos"])} ({n(stats["forks"])} forks)'),
            ('Stars received', n(stats['stars'])), ('Followers', n(stats['followers'])),
            ('Authored commits*', n(stats['commits'])),
        ]):
            rows.append(kv(44 + i * 21, key, value))
        rows += [text(12, 128, 'Code changes*', 'key'),
                 text(336, 128, '+' + n(stats['added']), 'green', anchor='end'),
                 text(428, 128, '-' + n(stats['deleted']), 'red', anchor='end'),
                 text(12, 154, '* Own non-forks, default branches only.', 'muted', 11),
                 text(12, 174, 'Updated ' + stats['updated'] + ' UTC', 'muted', 11)]
        files[f'img/profile-stats-{theme}.svg'] = svg(440, 184, rows)

    def picture(part, alt, width):
        return (f'<picture>\n<source media="(prefers-color-scheme: dark)" srcset="img/profile-{part}-dark.svg"/>\n'
                f'<source media="(prefers-color-scheme: light)" srcset="img/profile-{part}-light.svg"/>\n'
                f'<img src="img/profile-{part}-light.svg" width="{width}" alt="{html.escape(alt, quote=True)}"/>\n</picture>')

    # Contact anchors must remain HTML: links inside SVG image embeds are inert on GitHub.
    files['README.md'] = ('<table>\n<tr>\n<td width="38%" valign="middle">\n' +
        picture('avatar', 'ASCII portrait of Roccat', '100%') + '\n</td>\n<td width="62%" valign="top">\n' +
        picture('info', 'Roccat — AI Application Engineer. MacBook Pro. RAG, Agents, Enterprise AI. Gaming, basketball, AI apps.', '100%') +
        '\n<p><samp>&#160;&#160;GitHub: <a href="https://github.com/lizheng419">@lizheng419</a><br/>\n'
        '&#160;&#160;X:&#160;&#160;&#160;&#160;&#160;&#160;<a href="https://x.com/Roccat_fi">@Roccat_fi</a></samp></p>\n' +
        picture('stats', f'Public repositories: {stats["repos"]}; stars: {stats["stars"]}; followers: {stats["followers"]}; '
                f'authored commits on owned non-fork default branches: {stats["commits"]}; '
                f'lines added: {stats["added"]}; removed: {stats["deleted"]}; updated {stats["updated"]} UTC.', '100%') +
        '\n</td>\n</tr>\n</table>\n')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, help='Render a previously verified public-statistics JSON snapshot')
    args = parser.parse_args()
    stats = json.loads(args.snapshot.read_text()) if args.snapshot else fetch_stats()
    art = (ROOT / 'img/avatar.txt').read_text()
    files = render_profile(stats, art)
    for name, document in files.items():
        target = ROOT / name
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_text(document, encoding='utf-8')
        temporary.replace(target)
    print(json.dumps(stats, sort_keys=True))


if __name__ == '__main__':
    main()
