"""Rasterize the MailPilot envelope mark for the Office manifest."""
from pathlib import Path
from PIL import Image,ImageDraw
base=Image.new("RGBA",(320,320))
draw=ImageDraw.Draw(base)
draw.rounded_rectangle((0,0,319,319),radius=64,fill="#12645f")
draw.rounded_rectangle((49,80,271,236),radius=17,outline="white",width=14)
draw.line([(56,89),(161,173),(265,89)],fill="white",width=15,joint="curve")
for size in (16,32,80):
    base.resize((size,size),Image.Resampling.LANCZOS).save(Path(__file__).resolve().parents[1]/"docs"/f"icon-{size}.png")
