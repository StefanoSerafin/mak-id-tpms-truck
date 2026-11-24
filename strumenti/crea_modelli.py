#!/usr/bin/env python3
"""Costruisce modelli.js: i campioni dei caratteri del display del VT Truck.

  venv/bin/python strumenti/crea_modelli.py

Legge le foto in prove/foto/ con i valori corretti di prove/attesi.json e ritaglia i caratteri
con lo stesso codice dell'app (lettore.js, nel browser), così app e modelli non possono divergere.

Gli ID non si scelgono: per avere tutti i 16 caratteri (0-9, A-F) si usano anche le cifre di
pressione e temperatura. Se quelle righe non risultano scritte con lo stesso carattere degli ID,
i caratteri che vengono solo da lì sono segnati come «provvisori» e l'app li evidenzia sempre.
"""
import base64
import functools
import http.server
import json
import os
import sys
import threading

import numpy as np
from playwright.sync_api import sync_playwright

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TUTTI = '0123456789ABCDEF'
PAGINA = '<!doctype html><meta charset="utf-8"><script src="lettore.js"></script>'
JS = """async ([b64, attese]) => {
  const blob = await (await fetch('data:image/jpeg;base64,' + b64)).blob();
  return Lettore.celle(await Lettore.leggiFile(blob), attese);
}"""


class Silenzioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def zeta(b64):
    v = np.frombuffer(base64.b64decode(b64), dtype=np.uint8).astype(float)
    return (v - v.mean()) / (v.std() or 1)


def main():
    att = json.load(open(os.path.join(RADICE, 'prove', 'attesi.json')))['foto']
    cartella = os.path.join(RADICE, 'prove', 'foto')
    presenti = {n: v for n, v in att.items() if os.path.exists(os.path.join(cartella, n))}
    if not presenti:
        sys.exit('Nessuna foto in prove/foto/.')

    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Silenzioso, directory=RADICE))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    pag = os.path.join(RADICE, '_crea_modelli.html')
    open(pag, 'w').write(PAGINA)
    risultati = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto(f'http://127.0.0.1:{s.server_address[1]}/_crea_modelli.html')
            for n, v in presenti.items():
                dati = base64.b64encode(open(os.path.join(cartella, n), 'rb').read()).decode()
                risultati[n] = pg.evaluate(JS, [dati, {k: v.get(k) for k in ('id', 'pressione', 'temperatura')}])
            b.close()
    finally:
        s.shutdown()
        os.remove(pag)

    campioni, passi = [], []
    for n, r in risultati.items():
        if r.get('errore'):
            print(f'  {n}: {r["errore"]}')
            continue
        passi.append(r['passo'])
        campioni += r['campioni']
    if not campioni:
        sys.exit('Nessun campione ricavato: controllare le foto.')

    da_id = [c for c in campioni if c['fonte'] == 'id']
    altri = [c for c in campioni if c['fonte'] != 'id']
    # le righe di pressione e temperatura usano lo stesso carattere? Si prova a riconoscere
    # le loro cifre con i soli campioni degli ID, per i caratteri presenti in entrambi
    rif = {}
    for c in da_id:
        rif.setdefault(c['c'], []).append(zeta(c['v']))
    giusti = tot = 0
    for c in altri:
        if c['c'] not in rif:
            continue
        z = zeta(c['v'])
        punt = {k: max(float((z * t).mean()) for t in ts) for k, ts in rif.items()}
        giusti += max(punt, key=punt.get) == c['c']
        tot += 1
    compatibili = tot > 0 and giusti / tot >= 0.9
    print(f'Cifre di pressione/temperatura riconosciute con i soli modelli degli ID: {giusti}/{tot}'
          f' -> {"stesso carattere" if compatibili else "carattere diverso o ritaglio da rivedere"}')

    per = {}
    for c in da_id + altri:
        per.setdefault(c['c'], []).append(c['v'])
    solo_altri = sorted({c['c'] for c in altri} - {c['c'] for c in da_id})
    provvisori = [] if compatibili else solo_altri
    mancanti = [c for c in TUTTI if c not in per]
    modelli = {
        'versione': 1,
        'w': 20, 'h': 30,
        'passo': round(sum(passi) / len(passi), 4),
        'foto': len(passi),
        'provvisori': provvisori,
        'mancanti': mancanti,
        'campioni': {k: per[k] for k in sorted(per)},
    }
    with open(os.path.join(RADICE, 'modelli.js'), 'w') as f:
        f.write('// Generato da strumenti/crea_modelli.py: non modificare a mano.\n')
        f.write('window.MODELLI = ' + json.dumps(modelli, separators=(',', ':')) + ';\n')
    print(f"modelli.js: {len(per)} caratteri, {sum(len(v) for v in per.values())} campioni da {len(passi)} foto, "
          f"passo {modelli['passo']}")
    print('  solo da pressione/temperatura:', ''.join(solo_altri) or '-')
    print('  provvisori (sempre evidenziati):', ''.join(provvisori) or '-')
    print('  mancanti:', ''.join(mancanti) or '-')


if __name__ == '__main__':
    main()
