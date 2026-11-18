"""Draw the MailPilot mark and the three PagePilot ribbon palettes at display sizes."""
import math
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "desktop/icons"
PALETTES = {"jade": ("#26534a", "#23997d", "#c9eae0"), "ocean": ("#2b4370", "#4671d6", "#d3dff9"),
            "graphite": ("#313843", "#515e6f", "#d8dee4")}
SCALE = 10

def artwork(kind, colors):
    ink, accent, pale = colors
    im = Image.new("RGBA", (64*SCALE, 64*SCALE))
    d = ImageDraw.Draw(im)
    def points(coords):
        return [tuple(round(x*SCALE) for x in p) for p in coords]
    def box(coords):
        return tuple(round(x*SCALE) for x in coords)
    def line(coords, color, width=3):
        d.line(points(coords), fill=color, width=round(width*SCALE), joint="curve")
        for x,y in (coords[0],coords[-1]):
            d.ellipse(box((x-width/2,y-width/2,x+width/2,y+width/2)), fill=color)
    def circle(coords, fill, stroke=None, w=1):
        d.ellipse(box(coords), fill=fill, outline=stroke, width=round(w*SCALE))
    def poly(coords, color):
        d.polygon(points(coords), fill=color)
    if kind == "brand":
        d.rounded_rectangle(box((1,1,63,63)), radius=15*SCALE, fill=ink)
        poly([(8,22),(51,11),(39,46),(27,38),(19,49),(18,34)], pale)
        poly([(8,22),(51,11),(23,31)], "white")
        poly([(23,31),(51,11),(27,38),(19,49)], accent)
        line([(35,51),(44,51)], pale, 2)
        line([(40,45),(53,45)], pale, 2)
    elif kind == "search":
        circle((7,7,46,46), pale, ink, 3)
        circle((12,12,41,41), "#ffffff")
        line([(40,41),(54,55)], ink, 8)
        line([(42,43),(54,55)], accent, 5)
        circle((17,30,21,34), accent)
        for angle in (0,60,120):
            dx,dy=6*math.cos(math.radians(angle)),6*math.sin(math.radians(angle))
            line([(29-dx,24-dy),(29+dx,24+dy)], accent, 2.6)
    elif kind == "ai":
        d.rounded_rectangle(box((6,16,48,48)), radius=9*SCALE,fill=pale,outline=ink,width=3*SCALE)
        poly([(12,43),(12,55),(26,46)], ink)
        poly([(15,42),(15,50),(25,43)], pale)
        line([(14,30),(27,30)],ink,2.4)
        line([(14,36),(22,36)],accent,2.4)
        for x,y,r in ((44,22,17),(54,8,5)):
            poly([(x,y-r),(x+r*.29,y-r*.29),(x+r,y),(x+r*.29,y+r*.29),
                  (x,y+r),(x-r*.29,y+r*.29),(x-r,y),(x-r*.29,y-r*.29)], accent)
    else:
        gear=[]
        for i in range(8):
            for step,r in ((-.5,20),(-.28,20),(-.19,26),(.19,26),(.28,20)):
                a=(i+step)*math.pi/4
                gear.append((32+r*math.cos(a),32+r*math.sin(a)))
        poly(gear,pale);line(gear+[gear[0]],ink,2.8)
        circle((19,19,45,45),accent)
        circle((25,25,39,39),"white",ink,2)
    return im

if __name__=="__main__":
    ICONS.mkdir(parents=True,exist_ok=True)
    for palette,colors in PALETTES.items():
        for kind in ("brand","search","ai","settings"):
            image=artwork(kind,colors)
            image.resize((96,96),Image.Resampling.LANCZOS).save(ICONS/f"{palette}-{kind}.png")
    mark=artwork("brand", PALETTES["jade"])
    for size in (16,32,80):
        mark.resize((size,size),Image.Resampling.LANCZOS).save(ROOT/"docs"/f"icon-{size}.png")
    mark.resize((256,256),Image.Resampling.LANCZOS).save(ICONS/"mailpilot.ico",
        sizes=[(n,n) for n in (16,20,24,32,40,48,64,128,256)])
