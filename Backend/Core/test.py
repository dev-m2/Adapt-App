import shutil

import chafa
from chafa.loader import Loader


def renderImage(path: str, max_width: int = 120):
    """
    Print an image/SVG to the terminal.

    path: path to image file
    max_width: maximum character width to render
    """

    image = Loader(path)

    term_width = shutil.get_terminal_size().columns

    canvas_width = min(term_width - 2, max_width)

    aspect = image.height / image.width

    # Terminal cells are roughly twice as tall as they are wide
    canvas_height = max(
        1,
        int(canvas_width * aspect * 0.5)
    )

    config = chafa.CanvasConfig()
    config.width = canvas_width
    config.height = canvas_height

    # Optional quality tweaks
    config.cell_width = 1
    config.cell_height = 1

    canvas = chafa.Canvas(config)

    canvas.draw_all_pixels(
        image.pixel_type,
        image.get_pixels(),
        image.width,
        image.height,
        image.rowstride,
    )

    print(canvas.print().decode())

print_image("bb.svg")
