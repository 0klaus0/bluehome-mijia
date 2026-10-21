"""Generate the small, code-drawn FPK icon assets."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).parent / 'bluehome-mijia'
size = 1024
im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle((26, 26, 998, 998), radius=224, fill=(112, 144, 124))
d.ellipse((630, 160, 838, 368), fill=(246, 217, 153))
d.polygon([(205, 491), (506, 230), (819, 491)], fill=(250, 247, 237))
d.rounded_rectangle((287, 452, 735, 777), radius=30, fill=(250, 247, 237))
d.rounded_rectangle((450, 574, 574, 777), radius=23, fill=(162, 187, 164))
d.rounded_rectangle((333, 510, 413, 609), radius=17, fill=(184, 207, 189))
d.rounded_rectangle((608, 510, 688, 609), radius=17, fill=(184, 207, 189))
assets = [(root / 'ICON.PNG', 256), (root / 'ICON_256.PNG', 256),
          (root / 'app/ui/images/icon_256.png', 256), (root / 'app/ui/images/icon_64.png', 64)]
for path, width in assets:
    im.resize((width, width), Image.Resampling.LANCZOS).save(path)
