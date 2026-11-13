"""Prepare the pack icon from the project's supplied source artwork."""
import argparse
import pathlib

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_ICON = ROOT / 'artwork/pack-icon-source.png'


def render(size, source=SOURCE_ICON):
    with Image.open(source) as artwork:
        if artwork.width != artwork.height:
            raise ValueError('Pack artwork must be square; no automatic cropping is applied.')
        return artwork.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', type=int, default=512)
    parser.add_argument('--source', type=pathlib.Path, default=SOURCE_ICON)
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'src/main/resources/pack.png')
    args = parser.parse_args()
    if not 32 <= args.size <= 2048:
        parser.error('--size must be between 32 and 2048 pixels.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render(args.size, args.source).save(args.output, optimize=True)
    print(args.output.resolve())


if __name__ == '__main__':
    main()
