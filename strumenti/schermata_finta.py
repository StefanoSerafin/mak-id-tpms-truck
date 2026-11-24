#!/usr/bin/env python3
"""Schermate finte del VT Truck, per provare schema, configurazione e ruota evidenziata.

Non servono a misurare la lettura dell'ID: il carattere del display vero è diverso.
Proporzioni prese dalle foto reali di Enrico (ruote 55x20 px, assi a circa 62 px).

  genera(percorso, gruppi=[[2,4,2]], rossa=(gruppo, asse, 'su'|'giu', 'est'|'int'), id='5C307051')
"""
from PIL import Image, ImageDraw, ImageFont

VERDE = (40, 220, 40)
ROSSO = (230, 40, 30)


def genera(percorso, gruppi, rossa=None, id_testo='5C307051', larghezza=1200, altezza=1600):
    im = Image.new('RGB', (larghezza, altezza), (40, 40, 44))
    d = ImageDraw.Draw(im)
    d.rectangle([200, 300, 1000, 900], fill=(5, 5, 8))            # display
    d.rectangle([230, 380, 860, 590], fill=(120, 140, 175))       # sagoma del mezzo
    x = 320
    for gi, g in enumerate(gruppi):
        if gi:
            x += 150                                               # stacco tra trattore e rimorchio
        for ai, n in enumerate(g):
            d.line([x, 410, x, 570], fill=(230, 230, 230), width=5)
            posti = {('su', 'est'): 403, ('giu', 'est'): 555}
            if n == 4:
                posti.update({('su', 'int'): 430, ('giu', 'int'): 525})
            for (lato, pos), y in posti.items():
                if rossa and rossa == (gi, ai + 1, lato, pos):
                    d.rectangle([x - 31, y - 4, x + 31, y + 24], outline=ROSSO, width=4)
                    d.rectangle([x - 18, y + 5, x + 18, y + 15], fill=VERDE)
                else:
                    d.rectangle([x - 27, y, x + 27, y + 20], fill=VERDE)
            x += 62
    try:
        f = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 30)
    except OSError:
        f = ImageFont.load_default()
    d.text((238, 620), id_testo, font=f, fill=(235, 235, 235))
    d.text((238, 668), '133.4 PSI', font=f, fill=(235, 235, 235))
    d.text((655, 620), 'STAZIONARIO', font=f, fill=(235, 235, 235))
    d.ellipse([290, 1050, 320, 1080], fill=(60, 200, 90))          # led wifi verde, da ignorare
    im.save(percorso, quality=88)


if __name__ == '__main__':
    import sys
    genera(sys.argv[1], [[2, 4, 2]], (0, 2, 'su', 'int'))
