#!/usr/bin/env python3
"""Collaudo del server con due officine di prova (dati fittizi).

Uso:
  PWD_A=... PWD_B=... venv/bin/python strumenti/prova_api.py

Le officine prova-a@esempio.invalid e prova-b@esempio.invalid si creano con utenze.py.
Lo script lascia il database come l'ha trovato (cancella la targa di prova).
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get('API', 'https://mak-id-tpms-truck.serafin-stefano72.workers.dev')
ORIG = 'http://localhost:8765'
esiti = []


def chiama(metodo, percorso, corpo=None, token=None):
    dati = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request(API + percorso, data=dati, method=metodo,
                               headers={'Content-Type': 'application/json', 'Origin': ORIG,
                                        'User-Agent': 'prova-api',
                                        **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        with urllib.request.urlopen(r) as x:
            return x.status, json.loads(x.read() or b'{}'), dict(x.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}'), dict(e.headers)


def verifica(nome, cond, extra=''):
    esiti.append(bool(cond))
    print(('OK  ' if cond else 'NO  ') + nome + (f'  [{extra}]' if extra and not cond else ''))


def accedi(email, pwd):
    s, b, h = chiama('POST', '/login', {'email': email, 'password': pwd})
    return s, b, h


def main():
    pa, pb = os.environ.get('PWD_A'), os.environ.get('PWD_B')
    if not pa or not pb:
        sys.exit('Servono PWD_A e PWD_B.')
    T = 'ZZ999PR'

    s, b, h = accedi('prova-a@esempio.invalid', 'sbagliata')
    verifica('password sbagliata rifiutata', s == 401, s)
    verifica('CORS per l\'origine ammessa', h.get('Access-Control-Allow-Origin') == ORIG, h.get('Access-Control-Allow-Origin'))
    s, b, _ = chiama('GET', '/mezzi/' + T)
    verifica('senza accesso: 401', s == 401, s)

    s, b, _ = accedi('PROVA-A@esempio.invalid', pa)
    verifica('accesso A (mail in maiuscolo)', s == 200 and b.get('token'), b)
    ta = b['token']
    s, b, _ = accedi('prova-b@esempio.invalid', pb)
    tb = b['token']

    chiama('DELETE', '/mezzi/' + T, token=ta)
    s, b, _ = chiama('POST', '/mezzi', {'targa': 'zz 999 pr', 'tipo': 'trattore_motrice'}, ta)
    verifica('crea mezzo con targa normalizzata', s == 201 and b['mezzo']['targa'] == T, b)
    s, b, _ = chiama('POST', '/mezzi', {'targa': T, 'tipo': 'trattore_motrice'}, ta)
    verifica('targa esistente non duplicata', s == 200 and b.get('esistente') is True, b)
    s, b, _ = chiama('POST', '/mezzi', {'targa': 'AB', 'tipo': 'trattore_motrice'}, ta)
    verifica('targa troppo corta rifiutata', s == 400, s)
    s, b, _ = chiama('POST', '/mezzi', {'targa': 'ZZ998PR', 'tipo': 'furgone'}, ta)
    verifica('tipo non valido rifiutato', s == 400, s)

    s, b, _ = chiama('PUT', f'/mezzi/{T}/ruote/A1-su-est', {'sensore_id': '5C30387F', 'versione': 0}, ta)
    verifica('ruota rifiutata senza configurazione', s == 409, s)
    s, b, _ = chiama('PATCH', '/mezzi/' + T, {'configurazione': [2, 3]}, ta)
    verifica('configurazione con 3 ruote rifiutata', s == 400, s)
    s, b, _ = chiama('PATCH', '/mezzi/' + T, {'configurazione': [2, 4, 2]}, ta)
    verifica('configurazione 2-4-2 salvata', s == 200 and b['mezzo']['configurazione'] == [2, 4, 2], b)

    s, b, _ = chiama('PUT', f'/mezzi/{T}/ruote/A1-su-est', {'sensore_id': '5c30387f', 'versione': 0}, ta)
    r = {x['posizione']: x for x in b.get('ruote', [])}
    verifica('ID salvato in maiuscolo', s == 200 and r['A1-su-est']['sensore_id'] == '5C30387F', b)
    s, b, _ = chiama('PUT', f'/mezzi/{T}/ruote/A1-su-int', {'sensore_id': '5C30387F', 'versione': 0}, ta)
    verifica('ruota inesistente nello schema rifiutata', s == 400, s)
    s, b, _ = chiama('PUT', f'/mezzi/{T}/ruote/A1-su-est', {'sensore_id': 'XYZ', 'versione': 1}, ta)
    verifica('ID non esadecimale rifiutato', s == 400, s)
    s, b, _ = chiama('PUT', f'/mezzi/{T}/ruote/A1-su-est', {'sensore_id': 'AAAA1111', 'versione': 0}, ta)
    verifica('versione vecchia: 409 con valore attuale', s == 409 and b.get('attuale', {}).get('sensore_id') == '5C30387F', b)
    s, b, _ = chiama('PUT', f'/mezzi/{T}/ruote/A1-su-est', {'sensore_id': 'AAAA1111', 'versione': 1}, ta)
    r = {x['posizione']: x for x in b.get('ruote', [])}
    verifica('sovrascrittura tiene l\'ID precedente', s == 200 and r['A1-su-est']['id_precedente'] == '5C30387F'
             and r['A1-su-est']['versione'] == 2, b)
    chiama('PUT', f'/mezzi/{T}/ruote/A2-giu-int', {'sensore_id': '5C358F80', 'versione': 0}, ta)

    s, b, _ = chiama('GET', '/mezzi/ZZ999PQ', token=ta)
    verifica('targa sbagliata di un carattere: suggerisce la simile', s == 404 and any(x['targa'] == T for x in b.get('simili', [])), b)

    s, b, _ = chiama('GET', '/mezzi/' + T, token=tb)
    verifica('officina B non vede il mezzo di A', s == 404 and not b.get('simili'), b)
    s, b, _ = chiama('PUT', f'/mezzi/{T}/ruote/A1-su-est', {'sensore_id': 'BBBB2222', 'versione': 2}, tb)
    verifica('officina B non modifica il mezzo di A', s == 404, s)
    s, b, _ = chiama('DELETE', '/mezzi/' + T, token=tb)
    verifica('officina B non cancella il mezzo di A', s == 404, s)

    s, b, _ = chiama('PATCH', '/mezzi/' + T, {'configurazione': [2, 2, 2]}, ta)
    pos = [x['posizione'] for x in b.get('ruote', [])]
    verifica('cambio configurazione elimina solo le ruote fuori schema', s == 200 and pos == ['A1-su-est'], pos)

    s, b, _ = chiama('PATCH', '/mezzi/' + T, {'nuova_targa': 'ZZ999PS'}, ta)
    verifica('correzione della targa', s == 200 and b['mezzo']['targa'] == 'ZZ999PS', b)
    s, b, _ = chiama('DELETE', '/mezzi/ZZ999PS', token=ta)
    verifica('eliminazione del mezzo', s == 200, s)
    s, b, _ = chiama('GET', '/mezzi/ZZ999PS', token=ta)
    verifica('mezzo eliminato non più presente', s == 404, s)

    s, b, _ = chiama('POST', '/logout', token=ta)
    s, b, _ = chiama('GET', '/io', token=ta)
    verifica('dopo l\'uscita il token non vale più', s == 401, s)
    chiama('POST', '/logout', token=tb)

    print(f'\n{sum(esiti)} su {len(esiti)} verifiche superate')
    sys.exit(0 if all(esiti) else 1)


if __name__ == '__main__':
    main()
