"""Render the original train-and-memory-chip mark without fonts or external artwork."""
import argparse
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]


def render(size):
    # Draw in fixed design coordinates, then antialias once for consistent small icons.
    scale = 4
    canvas = Image.new('RGBA', (512 * scale, 512 * scale))
    draw = ImageDraw.Draw(canvas)
    navy, panel, teal, ivory, amber = '#101F30', '#193949', '#57DBC5', '#EFF8F3', '#FFCD76'

    def box(bounds, radius, fill, outline=None, width=1):
        draw.rounded_rectangle(tuple(n * scale for n in bounds), radius * scale,
                               fill=fill, outline=outline, width=width * scale)

    def line(points, fill, width):
        draw.line([(x * scale, y * scale) for x, y in points], fill=fill,
                  width=width * scale, joint='curve')

    box((0, 0, 512, 512), 104, navy)
    # Repeated connector pins make the memory motif readable at 32 and 64 pixels.
    for coordinate in (164, 224, 284, 344):
        box((66, coordinate - 8, 118, coordinate + 8), 8, teal)
        box((394, coordinate - 8, 446, coordinate + 8), 8, teal)
    for coordinate in (168, 226, 284, 342):
        box((coordinate - 8, 62, coordinate + 8, 108), 8, teal)
    box((108, 100, 404, 394), 56, panel, teal, 9)
    # Railway tracks continue beyond the chip, joining the two concepts in one mark.
    line([(215, 366), (177, 454)], amber, 13)
    line([(297, 366), (335, 454)], amber, 13)
    line([(193, 420), (319, 420)], amber, 10)
    line([(183, 444), (329, 444)], amber, 10)
    # A broad windshield and two lamps retain the train silhouette when reduced.
    box((164, 128, 348, 366), 42, ivory)
    box((216, 144, 296, 157), 6, teal)
    box((181, 175, 331, 263), 20, navy)
    line([(256, 176), (256, 262)], ivory, 8)
    line([(195, 241), (227, 203)], '#3B6174', 7)
    line([(274, 241), (306, 203)], '#3B6174', 7)
    box((164, 282, 348, 302), 0, teal)
    for x in (199, 313):
        box((x - 10, 315, x + 10, 335), 10, amber)
    box((234, 342, 278, 353), 5, navy)
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', type=int, default=512)
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'src/main/resources/pack.png')
    args = parser.parse_args()
    if not 32 <= args.size <= 2048:
        parser.error('--size must be between 32 and 2048 pixels.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render(args.size).save(args.output, optimize=True)
    print(args.output.resolve())


if __name__ == '__main__':
    main()
