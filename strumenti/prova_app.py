#!/usr/bin/env python3
"""Collaudo dell'app nel browser (WebKit come iPhone, Chromium come Android) con l'API vera.

  PWD_A=... venv/bin/python strumenti/prova_app.py

Usa l'officina di prova prova-a@esempio.invalid e targhe fittizie ZZ...PR, cancellate alla fine.
Serve l'app su http://localhost:8765 (ammesso nei CORS del Worker).
Le foto sono schermate finte (strumenti/schermata_finta.py): provano schema e ruota, non la lettura dell'ID.
"""
import functools
import http.server
import json
import os
import sys
import tempfile
import threading
import urllib.request

from playwright.sync_api import sync_playwright, expect

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RADICE, 'strumenti'))
from schermata_finta import genera  # noqa: E402

API = 'https://mak-id-tpms-truck.serafin-stefano72.workers.dev'
URL = 'http://localhost:8765/'
EMAIL = 'prova-a@esempio.invalid'
esiti = []


class Silenzioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def verifica(nome, cond):
    esiti.append(bool(cond))
    print(('    OK  ' if cond else '    NO  ') + nome)


def api(metodo, percorso, corpo=None, token=None):
    r = urllib.request.Request(API + percorso, method=metodo, data=json.dumps(corpo).encode() if corpo is not None else None,
                               headers={'Content-Type': 'application/json', 'User-Agent': 'prova-app',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        with urllib.request.urlopen(r) as x:
            return x.status, json.loads(x.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def ruote(token, targa):
    s, b = api('GET', '/mezzi/' + targa, token=token)
    return {r['posizione']: r for r in b.get('ruote', [])} if s == 200 else None, b


def accedi(pg, pwd):
    pg.goto(URL)
    pg.fill('#lEmail', EMAIL)
    pg.fill('#lPwd', pwd)
    pg.click('#loginForm button[type=submit]')
    expect(pg.locator('#v-home')).to_be_visible()


def ruota(pg, contenitore, pos):
    pg.locator(f'{contenitore} .ru[data-pos="{pos}"] rect').first.click(force=True)


def scenario(p, motore, dispositivo, pwd, foto, token):
    print(f'\n=== {motore.name} ({dispositivo}) ===')
    T1, T2 = ('ZZ111PR', 'YY222RM') if motore.name == 'webkit' else ('XX333PR', 'WW444RM')
    for t in (T1, T2):
        api('DELETE', '/mezzi/' + t, token=token)
    b = motore.launch()
    ctx = b.new_context(**p.devices[dispositivo], service_workers='block')
    pg = ctx.new_page()
    accedi(pg, pwd)
    verifica('dopo l\'accesso la home mostra i tre tasti',
             pg.locator('#v-home button.big').all_inner_texts().__len__() == 3
             and 'Targa Trattore / Motrice' in pg.inner_text('#v-home')
             and 'Targa Rimorchio / Semirimorchio' in pg.inner_text('#v-home')
             and 'Recupera targa' in pg.inner_text('#v-home'))

    # --- trattore: targa scritta a mano, prima foto crea lo schema ---
    pg.click('[data-nuova="trattore_motrice"]')
    pg.fill('#tInput', T1[:2].lower() + ' ' + T1[2:5] + ' ' + T1[5:].lower())
    verifica('la targa scritta viene ripetuta in grande e normalizzata', pg.inner_text('#tAnteprima') == T1)
    pg.click('#targaForm button[type=submit]')
    expect(pg.locator('#v-scheda')).to_be_visible()
    verifica('scheda nuova senza schema chiede la foto', 'Fotografa la prima schermata' in pg.inner_text('#sCorpo'))
    verifica('il tipo segue il tasto usato', pg.inner_text('#sTipo').lower() == 'trattore / motrice')
    pg.set_input_files('#fotoInput', foto['242_A2-su-int'])
    expect(pg.locator('#v-conferma')).to_be_visible()
    verifica('schema 2-4-2 ricavato dalla foto', '2-4-2' in pg.inner_text('#cAvvisi'))
    verifica('ruota proposta dalla foto: asse 2 alto interna', pg.inner_text('#cRuota') == 'Asse 2, lato alto, interna')
    verifica('senza modelli: chiede di scrivere l\'ID a mano', 'Scrivilo a mano' in pg.inner_text('#cAvvisi'))
    verifica('conferma bloccata senza ID', pg.locator('#cOk').is_disabled())
    pg.fill('#cId', '5c35-a04e')
    verifica('ID ripulito: solo 0-9 e A-F in maiuscolo', pg.input_value('#cId') == '5C35A04E')
    pg.click('#cOk')
    expect(pg.locator('#v-scheda')).to_be_visible()
    verifica('dopo il salvataggio propone la ruota vuota successiva', 'Prossima ruota vuota' in pg.inner_text('#sAvvisi'))
    pg.wait_for_function('() => JSON.parse(localStorage.getItem("idtpms.coda") || "[]").length === 0', timeout=15000)
    r, _ = ruote(token, T1)
    verifica('sul server: configurazione e ID salvati', r and r.get('A2-su-int', {}).get('sensore_id') == '5C35A04E')

    # --- ID a mano senza foto, poi sovrascrittura e doppione ---
    ruota(pg, '#sCorpo', 'A1-su-est')
    pg.click('#bMano')
    pg.fill('#cId', '5C30387F')
    pg.click('#cOk')
    ruota(pg, '#sCorpo', 'A1-su-est')
    ruota(pg, '#sCorpo', 'A1-su-est') if 'Asse 1, lato alto, esterna' not in pg.inner_text('#sCorpo') else None
    pg.click('#bMano')
    pg.fill('#cId', '5C35A04E')
    testo = pg.inner_text('#cSovr')
    verifica('avviso di sovrascrittura con vecchio e nuovo ID', '5C30387F' in testo and 'sostituito' in testo)
    verifica('avviso ID già presente su un\'altra ruota', 'già salvato su Asse 2' in testo)
    pg.fill('#cId', 'AAAA1111')
    pg.click('#cOk')
    pg.wait_for_function('() => JSON.parse(localStorage.getItem("idtpms.coda") || "[]").length === 0', timeout=15000)
    r, _ = ruote(token, T1)
    verifica('sul server: nuovo ID con il precedente conservato',
             r['A1-su-est']['sensore_id'] == 'AAAA1111' and r['A1-su-est']['id_precedente'] == '5C30387F')
    ruota(pg, '#sCorpo', 'A1-su-est') if 'prima era' not in pg.inner_text('#sCorpo') else None
    verifica('la scheda mostra «prima era»', 'prima era 5C30387F' in pg.inner_text('#sCorpo'))

    # --- foto con configurazione diversa: avviso, nessuna ruota proposta ---
    pg.set_input_files('#fotoInput', foto['222_A3-giu-est'])
    expect(pg.locator('#v-conferma')).to_be_visible()
    verifica('foto con assi diversi: avviso', 'mostra gli assi' in pg.inner_text('#cAvvisi'))
    verifica('foto con assi diversi: nessuna ruota proposta', pg.inner_text('#cRuota') == 'Tocca la ruota sullo schema')
    pg.click('#cAnnulla')

    # --- senza rete: la lettura resta in coda e parte al ritorno della rete ---
    ctx.set_offline(True)
    ruota(pg, '#sCorpo', 'A3-giu-est')
    pg.click('#bMano')
    pg.fill('#cId', '5C3030BA')
    pg.click('#cOk')
    verifica('senza rete: modifica in attesa segnalata', 'in attesa di rete' in pg.inner_text('#sAvvisi'))
    ctx.set_offline(False)
    pg.evaluate('() => window.dispatchEvent(new Event("online"))')
    pg.wait_for_function('() => JSON.parse(localStorage.getItem("idtpms.coda") || "[]").length === 0', timeout=20000)
    r, _ = ruote(token, T1)
    verifica('al ritorno della rete l\'ID arriva al server', r.get('A3-giu-est', {}).get('sensore_id') == '5C3030BA')

    # --- conflitto: due telefoni sulla stessa ruota ---
    pg2 = ctx.browser.new_context(**p.devices[dispositivo], service_workers='block').new_page()
    accedi(pg2, pwd)
    ctx.set_offline(True)
    ruota(pg, '#sCorpo', 'A3-su-est')
    pg.click('#bMano'); pg.fill('#cId', '11112222'); pg.click('#cOk')
    pg2.click('#bRecupera'); pg2.fill('#rInput', T1); pg2.click('#recForm button[type=submit]')
    expect(pg2.locator('#v-scheda')).to_be_visible()
    ruota(pg2, '#sCorpo', 'A3-su-est')
    pg2.click('#bMano'); pg2.fill('#cId', '33334444'); pg2.click('#cOk')
    pg2.wait_for_function('() => JSON.parse(localStorage.getItem("idtpms.coda") || "[]").length === 0', timeout=15000)
    ctx.set_offline(False)
    pg.evaluate('() => window.dispatchEvent(new Event("online"))')
    pg.wait_for_function('() => JSON.parse(localStorage.getItem("idtpms.coda") || "[]").length === 0', timeout=20000)
    expect(pg.locator('#sAvvisi')).to_contain_text('un altro dispositivo ha salvato', timeout=10000)
    verifica('conflitto mostrato con i due ID', '11112222' in pg.inner_text('#sAvvisi') and '33334444' in pg.inner_text('#sAvvisi'))
    pg.click('[data-scelta="mio"]')
    pg.wait_for_function('() => JSON.parse(localStorage.getItem("idtpms.coda") || "[]").length === 0', timeout=15000)
    r, _ = ruote(token, T1)
    verifica('«Tieni il mio» salva il proprio ID', r['A3-su-est']['sensore_id'] == '11112222')

    # --- rimorchio: schermata con trattore e rimorchio insieme ---
    pg.click('[data-home]:visible')
    pg.click('[data-nuova="rimorchio_semirimorchio"]')
    pg.fill('#tInput', T2)
    pg.click('#targaForm button[type=submit]')
    expect(pg.locator('#v-scheda')).to_be_visible()
    pg.set_input_files('#fotoInput', foto['24+222_rim_A1-giu-est'])
    expect(pg.locator('#v-conferma')).to_be_visible()
    verifica('tasto rimorchio: prende il secondo gruppo di assi (2-2-2)', '2-2-2' in pg.inner_text('#cAvvisi'))
    verifica('tasto rimorchio: ruota del rimorchio proposta', pg.inner_text('#cRuota') == 'Asse 1, lato basso, esterna')
    pg.fill('#cId', '5C302FCD'); pg.click('#cOk')
    pg.set_input_files('#fotoInput', foto['24+222_tra_A2-giu-int'])
    expect(pg.locator('#v-conferma')).to_be_visible()
    verifica('ruota evidenziata sul trattore: avviso e nessuna proposta',
             'appartiene al trattore' in pg.inner_text('#cAvvisi') and pg.inner_text('#cRuota') == 'Tocca la ruota sullo schema')
    pg.click('#cAnnulla')

    # --- recupera targa con un carattere sbagliato ---
    pg.click('[data-home]:visible')
    pg.click('#bRecupera')
    pg.fill('#rInput', T1[:-1] + 'Q')
    pg.click('#recForm button[type=submit]')
    expect(pg.locator('#recEsito')).to_contain_text('non trovata')
    verifica('targa sbagliata: propone quella simile', T1 in pg.inner_text('#recEsito'))
    pg.click(f'[data-apri="{T1}"]')
    expect(pg.locator('#v-scheda')).to_be_visible()
    verifica('recupero: scheda con gli ID salvati', '4 di 8 ruote' in pg.inner_text('#sCorpo'))
    pg.screenshot(path=os.path.join(tempfile.gettempdir(), f'id-tpms-{motore.name}.png'), full_page=True)

    b.close()
    for t in (T1, T2):
        api('DELETE', '/mezzi/' + t, token=token)


def main():
    pwd = os.environ.get('PWD_A') or sys.exit('Serve PWD_A.')
    s = http.server.ThreadingHTTPServer(('localhost', 8765), functools.partial(Silenzioso, directory=RADICE))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    st, b = api('POST', '/login', {'email': EMAIL, 'password': pwd})
    token = b['token']
    with tempfile.TemporaryDirectory() as tmp:
        foto = {}
        for nome, gruppi, rossa in [('242_A2-su-int', [[2, 4, 2]], (0, 2, 'su', 'int')),
                                    ('222_A3-giu-est', [[2, 2, 2]], (0, 3, 'giu', 'est')),
                                    ('24+222_rim_A1-giu-est', [[2, 4], [2, 2, 2]], (1, 1, 'giu', 'est')),
                                    ('24+222_tra_A2-giu-int', [[2, 4], [2, 2, 2]], (0, 2, 'giu', 'int'))]:
            foto[nome] = os.path.join(tmp, nome + '.jpg')
            genera(foto[nome], gruppi, rossa)
        try:
            with sync_playwright() as p:
                scenario(p, p.webkit, 'iPhone 13', pwd, foto, token)
                scenario(p, p.chromium, 'Pixel 7', pwd, foto, token)
        finally:
            api('POST', '/logout', token=token)
            s.shutdown()
    print(f'\n{sum(esiti)} su {len(esiti)} verifiche superate')
    sys.exit(0 if all(esiti) else 1)


if __name__ == '__main__':
    main()
