#!/usr/bin/env python3
"""Utenze delle officine di ID TPMS TRUCK.

Non esiste registrazione libera: un'officina entra solo quando l'agente MAK lo chiede
e qualcuno lancia questo script dal Mac.

Uso (dalla cartella del progetto):
  venv/bin/python strumenti/utenze.py attiva    --nome "Officina Rossi" --email officina@rossi.it --agente "Enrico Galante"
  venv/bin/python strumenti/utenze.py reimposta --email officina@rossi.it
  venv/bin/python strumenti/utenze.py sospendi  --email officina@rossi.it
  venv/bin/python strumenti/utenze.py riattiva  --email officina@rossi.it
  venv/bin/python strumenti/utenze.py elenco
  venv/bin/python strumenti/utenze.py elimina   --email officina@rossi.it   (cancella anche tutti i suoi mezzi)

La password generata si vede una sola volta: va comunicata all'officina, non salvata altrove.
Il token Cloudflare viene letto dal Portachiavi (voce cloudflare-api-token).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile

DB = 'mak-id-tpms-truck'
ITER = 20000  # PBKDF2-SHA256; basso perché il piano gratuito dà 10 ms di calcolo per richiesta e le password sono casuali
CARATTERI = 'abcdefghjkmnpqrstuvwxyz23456789'  # niente 0/o, 1/l/i: si dettano al telefono
RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RE_EMAIL = re.compile(r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$')


def token():
    try:
        return subprocess.run(['security', 'find-generic-password', '-s', 'cloudflare-api-token', '-w'],
                              capture_output=True, text=True, check=True).stdout.strip()
    except subprocess.CalledProcessError:
        sys.exit('Token Cloudflare non trovato nel Portachiavi (voce cloudflare-api-token).')


def sql(testo, leggi=False):
    """Esegue SQL sul database remoto passando da un file, per non avere valori nella riga di comando."""
    with tempfile.NamedTemporaryFile('w', suffix='.sql', delete=False) as f:
        f.write(testo)
        nome = f.name
    try:
        cmd = ['npx', '-y', 'wrangler@4', 'd1', 'execute', DB, '--remote', '--file', nome]
        if leggi:
            cmd = ['npx', '-y', 'wrangler@4', 'd1', 'execute', DB, '--remote', '--json', '--command', testo]
        r = subprocess.run(cmd, cwd=RADICE, capture_output=True, text=True,
                           env={**os.environ, 'CLOUDFLARE_API_TOKEN': token()})
    finally:
        os.unlink(nome)
    if r.returncode != 0:
        sys.exit('Errore dal database:\n' + (r.stderr or r.stdout)[-1500:])
    if leggi:
        testo_json = r.stdout[r.stdout.find('['):]
        return json.loads(testo_json)[0]['results']
    return None


def q(s):
    """Valore testuale per SQL: apici raddoppiati."""
    return "'" + str(s).replace("'", "''") + "'"


def email_ok(e):
    e = e.strip().lower()
    if not RE_EMAIL.match(e) or len(e) > 200:
        sys.exit(f'Mail non valida: {e}')
    return e


def nuova_password():
    gruppi = [''.join(secrets.choice(CARATTERI) for _ in range(4)) for _ in range(3)]
    return '-'.join(gruppi)


def hash_password(pwd):
    sale = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac('sha256', pwd.encode(), sale, ITER)
    return h.hex(), sale.hex()


def esiste(email):
    return sql(f"SELECT id, nome, attiva FROM officine WHERE email = {q(email)}", leggi=True)


def mostra_password(email, pwd):
    print('\n  Mail:     ', email)
    print('  Password: ', pwd)
    print('\n  Comunicala all\'officina: non viene salvata da nessuna parte e non si può rivedere.\n')


def attiva(a):
    email = email_ok(a.email)
    nome = a.nome.strip()
    if not nome or len(nome) > 120:
        sys.exit('Nome officina obbligatorio (massimo 120 caratteri).')
    if esiste(email):
        sys.exit('Questa mail ha già un\'utenza. Usa "reimposta" per una nuova password.')
    pwd = nuova_password()
    h, s = hash_password(pwd)
    ora = dt.datetime.now(dt.timezone.utc).isoformat()
    sql(f"INSERT INTO officine (nome, email, pwd_hash, pwd_sale, pwd_iter, attiva, agente, creata) "
        f"VALUES ({q(nome)}, {q(email)}, {q(h)}, {q(s)}, {ITER}, 1, {q(a.agente or '')}, {q(ora)});")
    print(f'Utenza attivata per {nome}.')
    mostra_password(email, pwd)


def reimposta(a):
    email = email_ok(a.email)
    if not esiste(email):
        sys.exit('Nessuna utenza con questa mail.')
    pwd = nuova_password()
    h, s = hash_password(pwd)
    sql(f"UPDATE officine SET pwd_hash = {q(h)}, pwd_sale = {q(s)}, pwd_iter = {ITER}, tentativi = 0, blocco_fino = NULL "
        f"WHERE email = {q(email)};\n"
        f"DELETE FROM sessioni WHERE officina_id = (SELECT id FROM officine WHERE email = {q(email)});")
    print('Password reimpostata: tutti i dispositivi devono accedere di nuovo.')
    mostra_password(email, pwd)


def sospendi(a, valore=0):
    email = email_ok(a.email)
    if not esiste(email):
        sys.exit('Nessuna utenza con questa mail.')
    extra = f"\nDELETE FROM sessioni WHERE officina_id = (SELECT id FROM officine WHERE email = {q(email)});" if valore == 0 else ''
    sql(f"UPDATE officine SET attiva = {valore} WHERE email = {q(email)};" + extra)
    print('Utenza sospesa: i dispositivi collegati sono stati scollegati.' if valore == 0 else 'Utenza riattivata.')


def elimina(a):
    email = email_ok(a.email)
    r = esiste(email)
    if not r:
        sys.exit('Nessuna utenza con questa mail.')
    risposta = input(f'Eliminare {r[0]["nome"]} con TUTTI i suoi mezzi? Scrivi ELIMINA per confermare: ')
    if risposta.strip() != 'ELIMINA':
        sys.exit('Annullato.')
    i = f"(SELECT id FROM officine WHERE email = {q(email)})"
    sql(f"DELETE FROM ruote WHERE mezzo_id IN (SELECT id FROM mezzi WHERE officina_id = {i});\n"
        f"DELETE FROM mezzi WHERE officina_id = {i};\n"
        f"DELETE FROM sessioni WHERE officina_id = {i};\n"
        f"DELETE FROM officine WHERE email = {q(email)};")
    print('Utenza e dati eliminati.')


def elenco(a):
    righe = sql("SELECT o.nome, o.email, o.attiva, o.agente, substr(o.creata,1,10) AS creata, "
                "substr(o.ultimo_accesso,1,10) AS accesso, "
                "(SELECT COUNT(*) FROM mezzi m WHERE m.officina_id = o.id) AS mezzi "
                "FROM officine o ORDER BY o.nome", leggi=True)
    if not righe:
        print('Nessuna officina attivata.')
        return
    for r in righe:
        stato = 'attiva' if r['attiva'] else 'SOSPESA'
        print(f"{r['nome'][:30]:30} {r['email'][:34]:34} {stato:8} mezzi {r['mezzi']:>4}  "
              f"creata {r['creata']}  ultimo accesso {r['accesso'] or '-'}  agente {r['agente'] or '-'}")


def main():
    p = argparse.ArgumentParser(description='Utenze officine ID TPMS TRUCK')
    s = p.add_subparsers(dest='cmd', required=True)
    x = s.add_parser('attiva'); x.add_argument('--nome', required=True); x.add_argument('--email', required=True); x.add_argument('--agente', default='')
    for c in ('reimposta', 'sospendi', 'riattiva', 'elimina'):
        s.add_parser(c).add_argument('--email', required=True)
    s.add_parser('elenco')
    a = p.parse_args()
    {'attiva': attiva, 'reimposta': reimposta, 'sospendi': sospendi, 'riattiva': lambda a: sospendi(a, 1),
     'elimina': elimina, 'elenco': elenco}[a.cmd](a)


if __name__ == '__main__':
    main()
