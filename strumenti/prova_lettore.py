#!/usr/bin/env python3
"""Misura il lettore (lettore.js) nel browser vero, Chromium e WebKit, con Playwright.

  venv/bin/python strumenti/prova_lettore.py            foto reali in prove/foto/ con i valori di prove/attesi.json
  venv/bin/python strumenti/prova_lettore.py --finte    schermate finte: solo schema, configurazione e ruota

Con le foto reali la lettura dell'ID si misura in due modi:
  - "tenendo fuori": i modelli vengono rifatti ogni volta senza la foto che si sta leggendo (misura onesta);
  - "modelli.js": con i modelli pubblicati (comprendono la foto letta, quindi è ottimistica).
Ogni foto viene provata anche peggiorata: ruotata, sfocata, più scura, più chiara, rimpicciolita.
"""
import base64
import functools
import http.server
import io
import json
import os
import sys
import tempfile
import threading

from PIL import Image, ImageEnhance, ImageFilter
from playwright.sync_api import sync_playwright

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RADICE, 'strumenti'))
from schermata_finta import genera  # noqa: E402

PAGINA = '<!doctype html><meta charset="utf-8"><script src="modelli.js"></script><script src="lettore.js"></script>'
JS = """async ([b64, modelli]) => {
  const blob = await (await fetch('data:image/jpeg;base64,' + b64)).blob();
  const img = await Lettore.leggiFile(blob);
  return Lettore.analizza(img, modelli === 'pubblicati' ? window.MODELLI : modelli);
}"""
JS_CELLE = """async ([b64, attese]) => {
  const blob = await (await fetch('data:image/jpeg;base64,' + b64)).blob();
  return Lettore.celle(await Lettore.leggiFile(blob), attese);
}"""


class Silenzioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def server():
    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Silenzioso, directory=RADICE))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    with open(os.path.join(RADICE, '_prova_lettore.html'), 'w') as f:
        f.write(PAGINA)
    return s, f'http://127.0.0.1:{s.server_address[1]}/_prova_lettore.html'


def b64(im):
    buf = io.BytesIO()
    im.convert('RGB').save(buf, 'JPEG', quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def varianti(im):
    yield 'originale', im
    yield 'ruotata +5', im.rotate(5, resample=Image.BICUBIC, expand=False, fillcolor=(30, 30, 30))
    yield 'ruotata -5', im.rotate(-5, resample=Image.BICUBIC, expand=False, fillcolor=(30, 30, 30))
    yield 'sfocata', im.filter(ImageFilter.GaussianBlur(1.6))
    yield 'più scura', ImageEnhance.Brightness(im).enhance(0.6)
    yield 'più chiara', ImageEnhance.Brightness(im).enhance(1.35)
    yield 'rimpicciolita', im.resize((im.width * 2 // 3, im.height * 2 // 3))


def modelli_senza(campioni, escludi):
    per = {}
    passi = []
    for nome, c in campioni.items():
        if nome == escludi or 'campioni' not in c:
            continue
        passi.append(c['passo'])
        for x in c['campioni']:
            per.setdefault(x['c'], []).append(x['v'])
    return {'passo': sum(passi) / len(passi) if passi else 0.69, 'campioni': per, 'provvisori': []}


def finte(pagina):
    casi = [
        ([[2, 4, 2]], (0, 2, 'su', 'int'), [[2, 4, 2]], (0, 'A2-su-int')),
        ([[2, 4, 2]], (0, 1, 'giu', 'est'), [[2, 4, 2]], (0, 'A1-giu-est')),
        ([[2, 4, 2]], (0, 3, 'su', 'est'), [[2, 4, 2]], (0, 'A3-su-est')),
        ([[2, 4, 4]], (0, 3, 'giu', 'int'), [[2, 4, 4]], (0, 'A3-giu-int')),
        ([[2, 2, 2]], (0, 3, 'giu', 'est'), [[2, 2, 2]], (0, 'A3-giu-est')),
        ([[2, 4], [2, 2, 2]], (1, 1, 'giu', 'est'), [[2, 4], [2, 2, 2]], (1, 'A1-giu-est')),
        ([[2, 4], [2, 2, 2]], (0, 2, 'giu', 'int'), [[2, 4], [2, 2, 2]], (0, 'A2-giu-int')),
    ]
    ok = tot = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (gruppi, rossa, att_g, att_r) in enumerate(casi):
            p = os.path.join(tmp, f'f{i}.jpg')
            genera(p, gruppi, rossa)
            base = Image.open(p)
            for nome, im in varianti(base):
                r = pagina.evaluate(JS, [b64(im), None])
                ru = r.get('ruota') or {}
                giusto = r.get('gruppi') == att_g and (ru.get('gruppo'), ru.get('chiave')) == att_r
                ok += giusto
                tot += 1
                if not giusto or nome == 'originale':
                    print(f"  {'OK' if giusto else 'NO'}  {str(gruppi):22} {nome:13} gruppi {r.get('gruppi')} ruota {ru.get('gruppo')} {ru.get('chiave')}")
    return ok, tot


def reali(pagina):
    att = json.load(open(os.path.join(RADICE, 'prove', 'attesi.json')))['foto']
    cartella = os.path.join(RADICE, 'prove', 'foto')
    presenti = {n: v for n, v in att.items() if os.path.exists(os.path.join(cartella, n))}
    if not presenti:
        sys.exit('Nessuna foto in prove/foto/: copiarle prima (vedi README).')
    immagini = {n: Image.open(os.path.join(cartella, n)) for n in presenti}
    campioni = {n: pagina.evaluate(JS_CELLE, [b64(im), {k: presenti[n][k] for k in ('id', 'pressione', 'temperatura')}])
                for n, im in immagini.items()}
    conti = {'conf': [0, 0], 'ruota': [0, 0], 'id_fuori': [0, 0], 'id_pubbl': [0, 0], 'id_salvo_conferma': [0, 0]}
    for n, im in immagini.items():
        a = presenti[n]
        attesa = f"A{a['asse']}-{a['lato']}-{a['pos']}"
        mod = modelli_senza(campioni, n)
        for nome, v in varianti(im):
            r = pagina.evaluate(JS, [b64(v), mod])
            rp = pagina.evaluate(JS, [b64(v), 'pubblicati']) if nome == 'originale' else None
            ru = (r.get('ruota') or {}).get('chiave')
            conti['conf'][0] += r.get('configurazione') == a['configurazione']; conti['conf'][1] += 1
            conti['ruota'][0] += ru == attesa; conti['ruota'][1] += 1
            conti['id_fuori'][0] += r.get('id') == a['id']; conti['id_fuori'][1] += 1
            # errore pericoloso: ID sbagliato senza nessun carattere segnalato come incerto
            if r.get('id') and r.get('id') != a['id']:
                segnalato = any(c['incerto'] for c in r['caratteri'])
                conti['id_salvo_conferma'][0] += segnalato; conti['id_salvo_conferma'][1] += 1
            if rp is not None:
                conti['id_pubbl'][0] += rp.get('id') == a['id']; conti['id_pubbl'][1] += 1
            if nome == 'originale' or r.get('id') != a['id']:
                print(f"  {n[-22:]:22} {nome:13} ID {r.get('id')} (atteso {a['id']}) ruota {ru} conf {r.get('configurazione')} esito {r.get('esito')}")
    return conti


def main():
    s, url = server()
    esito = 0
    try:
        with sync_playwright() as p:
            for motore in (p.chromium, p.webkit):
                b = motore.launch()
                pg = b.new_page()
                pg.goto(url)
                print(f'\n=== {motore.name} ===')
                if '--finte' in sys.argv:
                    ok, tot = finte(pg)
                    print(f'  schermate finte: {ok} su {tot} con gruppi e ruota giusti')
                    esito |= ok != tot
                else:
                    c = reali(pg)
                    print(f"  configurazione giusta: {c['conf'][0]}/{c['conf'][1]}")
                    print(f"  ruota giusta: {c['ruota'][0]}/{c['ruota'][1]}")
                    print(f"  ID giusto, modelli senza la foto letta: {c['id_fuori'][0]}/{c['id_fuori'][1]}")
                    print(f"  ID giusto, modelli pubblicati (foto originali): {c['id_pubbl'][0]}/{c['id_pubbl'][1]}")
                    print(f"  ID sbagliati con almeno un carattere segnalato: {c['id_salvo_conferma'][0]}/{c['id_salvo_conferma'][1]}")
                b.close()
    finally:
        s.shutdown()
        os.remove(os.path.join(RADICE, '_prova_lettore.html'))
    sys.exit(esito)


if __name__ == '__main__':
    main()
