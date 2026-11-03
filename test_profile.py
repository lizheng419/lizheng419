import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from xml.etree import ElementTree as ET

import update_profile as profile
from tools.ascii_avatar import convert


class ProfileTests(unittest.TestCase):
    def test_avatar_keeps_dark_hair_and_removes_background_islands(self):
        pixels = bytearray([0, 0, 0, 255] * (45 * 23))
        for x, y, color in [(20, 10, (22, 26, 37, 255)),
                            (21, 10, (80, 65, 60, 255)),
                            (20, 11, (80, 65, 60, 255)),
                            (2, 2, (22, 26, 37, 255)),
                            (22, 10, (10, 90, 240, 255))]:
            offset = (y * 45 + x) * 4
            pixels[offset:offset + 4] = bytes(color)
        with patch('tools.ascii_avatar.subprocess.run') as command:
            command.return_value.stdout = bytes(pixels)
            art = convert('avatar.png')
        self.assertEqual(sum(char != ' ' for char in art.replace('\n', '')), 3)
        self.assertEqual(len(art.splitlines()), 2)

    def test_pagination_keeps_repository_101(self):
        with patch.object(profile, 'api', side_effect=[list(range(100)), [100]]):
            self.assertEqual(list(profile.pages('/repos?type=owner')), list(range(101)))

    def test_private_repos_and_fork_history_are_excluded(self):
        repos = [
            dict(name='own', private=False, fork=False, stargazers_count=2),
            dict(name='fork', private=False, fork=True, stargazers_count=3),
            dict(name='secret', private=True, fork=False, stargazers_count=900),
        ]
        def history(name):
            self.assertEqual(name, 'own')
            return 7, 120, 20
        with patch.object(profile, 'api', return_value={'followers': 4}), \
             patch.object(profile, 'pages', return_value=iter(repos)), \
             patch.object(profile, 'scan_repo', side_effect=history):
            stats = profile.fetch_stats()
        self.assertEqual((stats['repos'], stats['stars'], stats['forks']), (2, 5, 1))
        self.assertEqual((stats['commits'], stats['added'], stats['deleted']), (7, 120, 20))

    def test_failed_history_never_returns_partial_totals(self):
        with patch.object(profile, 'pages', return_value=iter([{'sha': 'abc'}])), \
             patch.object(profile, 'api', side_effect=RuntimeError('network failed')):
            with self.assertRaisesRegex(RuntimeError, 'network failed'):
                profile.scan_repo('example')

    def test_empty_repository_is_zero_not_an_error(self):
        with patch.object(profile, 'api', side_effect=HTTPError('url', 409, 'empty', {}, None)):
            self.assertEqual(profile.scan_repo('empty'), (0, 0, 0))

    def test_contact_values_are_links_inside_the_terminal_card(self):
        stats = dict(repos=38, stars=27, followers=21, forks=37,
                     commits=23, added=375, deleted=43, updated='2026-11-03')
        document = profile.render(stats, '  <&>\n @@@')
        card = ET.fromstring(document)
        self.assertEqual(card.tag, 'pre')
        links = {node.text: node.attrib['href'] for node in card.iter('a')}
        self.assertEqual(links['@Roccat_fi'], 'https://x.com/Roccat_fi')
        self.assertEqual(links['github.com/lizheng419'], 'https://github.com/lizheng419')
        self.assertIn('<&>', ''.join(card.itertext()))
        self.assertNotIn('<img', document)
        for line in ''.join(card.itertext()).splitlines():
            self.assertLessEqual(len(line), 96)


if __name__ == '__main__':
    unittest.main()
