"""Convert the current GitHub avatar to 45 x 23 ASCII characters.

Requires FFmpeg only when changing the avatar:
python3 tools/ascii_avatar.py /path/to/avatar.png > img/avatar.txt
The blue/bright mask is tuned for Roccat's current portrait.
"""
import subprocess
import sys


def convert(path):
    pixels = subprocess.run([
        'ffmpeg', '-v', 'error', '-i', path, '-vf', 'scale=45:23:flags=area',
        '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgba', 'pipe:1',
    ], check=True, capture_output=True).stdout
    if len(pixels) != 45 * 23 * 4:
        raise ValueError('Expected a 45 x 23 RGBA image')
    chars = '@%#*+=-:. '
    rows = []
    for y in range(23):
        line = ''
        for x in range(45):
            offset = (y * 45 + x) * 4
            r, g, b, a = pixels[offset:offset + 4]
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            # The avatar has a black matte and a saturated blue backdrop; retain dark hair.
            background = (a < 128 or max(r, g, b) < 8 or lum > 235
                          or (b - r > 12 and lum > 90)
                          or (b - r > 40 and lum > 35))
            line += ' ' if background else chars[round((lum / 255) ** 0.45 * (len(chars) - 1))]
        rows.append(line)
    remaining = {(x, y) for y, row in enumerate(rows) for x, char in enumerate(row) if char != ' '}
    largest = set()
    while remaining:
        component = {remaining.pop()}
        stack = list(component)
        while stack:
            x, y = stack.pop()
            neighbors = {(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)} & remaining
            remaining -= neighbors
            component |= neighbors
            stack.extend(neighbors)
        if len(component) > len(largest):
            largest = component
    rows = [''.join(char if (x, y) in largest else ' ' for x, char in enumerate(row)).rstrip()
            for y, row in enumerate(rows)]
    if not largest:
        raise ValueError('No foreground found; adjust the avatar background mask')
    return '\n'.join(rows).strip('\n') + '\n'


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 tools/ascii_avatar.py avatar.png > img/avatar.txt')
    print(convert(sys.argv[1]), end='')
