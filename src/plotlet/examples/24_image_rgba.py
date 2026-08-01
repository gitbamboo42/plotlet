"""RGB pixel data

image_rgba places real pixel data — an (H, W, 3|4) array where each
cell already is a color — with no colormap in between. Pixel data is
just an array: slicing it is cropping. Row 0 renders at the top by
default, so the photo displays as-seen.
"""
import plotlet as pt

earth = pt.load_dataset("earth")   # (256, 256, 3) uint8 — Apollo 17, NASA
zoom = earth[16:112, 72:168]       # a slice IS a crop

full = pt.chart(title="the blue marble", data_width=224, data_height=224)
full.add_image_rgba(earth)

crop = pt.chart(title="earth[16:112, 72:168]", data_width=224, data_height=224)
crop.add_image_rgba(zoom)

c = full | crop
