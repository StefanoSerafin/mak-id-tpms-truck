// ID TPMS TRUCK - API (Cloudflare Worker + D1)
// Archivio degli ID dei sensori TPMS per targa, separato per officina.
// Le foto non arrivano mai qui: il telefono legge la schermata e manda solo il testo confermato.
//
// Variabili (wrangler.toml): ORIGINI = indirizzi ammessi per CORS, separati da virgola.
// Nessun segreto: le password sono salvate come hash PBKDF2 da strumenti/utenze.py.

const SESSIONE_GIORNI = 180;
const MAX_TENTATIVI = 5;
const BLOCCO_MINUTI = 15;
const TIPI = ['trattore_motrice', 'rimorchio_semirimorchio'];
const RE_ID = /^[0-9A-F]{4,12}$/;
const RE_POS = /^A(\d{1,2})-(su|giu)-(est|int)$/;

export default {
  async fetch(req, env) {
    const cors = intestazioniCors(req, env);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    try {
      const r = await instrada(req, env);
      for (const [k, v] of Object.entries(cors)) r.headers.set(k, v);
      return r;
    } catch (e) {
      if (e instanceof Errore) return json({ errore: e.message, ...e.extra }, e.stato, cors);
      console.log('errore interno', e && e.stack || e);
      return json({ errore: 'Errore interno, riprova.' }, 500, cors);
    }
  },
};

class Errore extends Error {
  constructor(stato, messaggio, extra = {}) { super(messaggio); this.stato = stato; this.extra = extra; }
}

function intestazioniCors(req, env) {
  const ammessi = String(env.ORIGINI || '').split(',').map(s => s.trim()).filter(Boolean);
  const o = req.headers.get('Origin') || '';
  const h = {
    'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  };
  if (ammessi.includes(o)) h['Access-Control-Allow-Origin'] = o;
  return h;
}

function json(dati, stato = 200, extra = {}) {
  return new Response(JSON.stringify(dati), {
    status: stato,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra },
  });
}

const ora = () => new Date().toISOString();

async function corpo(req) {
  const t = await req.text();
  if (t.length > 4000) throw new Errore(413, 'Richiesta troppo grande.');
  if (!t) return {};
  try { const o = JSON.parse(t); if (o && typeof o === 'object' && !Array.isArray(o)) return o; } catch (e) { /* sotto */ }
  throw new Errore(400, 'Richiesta non valida.');
}

// ---------- normalizzazioni e controlli ----------

export function normTarga(s) {
  const t = String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (t.length < 4 || t.length > 10) throw new Errore(400, 'Targa non valida: servono da 4 a 10 lettere o cifre.');
  return t;
}

function normId(s) {
  const t = String(s || '').toUpperCase().replace(/[^0-9A-F]/g, '');
  if (!RE_ID.test(t)) throw new Errore(400, 'ID non valido: servono da 4 a 12 caratteri tra 0-9 e A-F.');
  return t;
}

export function controllaConfigurazione(c) {
  if (!Array.isArray(c) || c.length < 1 || c.length > 10) throw new Errore(400, 'Configurazione non valida.');
  let tot = 0;
  for (const n of c) {
    if (n !== 2 && n !== 4) throw new Errore(400, 'Configurazione non valida: ogni asse ha 2 o 4 ruote.');
    tot += n;
  }
  if (tot > 26) throw new Errore(400, 'Configurazione non valida: massimo 26 ruote.');
  return c;
}

// Posizioni valide per una configurazione: A1-su-est, A2-su-int, ...
export function posizioni(config) {
  const out = [];
  config.forEach((n, i) => {
    const a = 'A' + (i + 1);
    out.push(a + '-su-est');
    if (n === 4) out.push(a + '-su-int', a + '-giu-int');
    out.push(a + '-giu-est');
  });
  return out;
}

function distanza1(a, b) {
  // vero se a e b differiscono per un solo carattere (sostituzione, aggiunta o tolta)
  if (a === b) return false;
  if (Math.abs(a.length - b.length) > 1) return false;
  if (a.length === b.length) { let d = 0; for (let i = 0; i < a.length; i++) if (a[i] !== b[i] && ++d > 1) return false; return d === 1; }
  const [c, l] = a.length < b.length ? [a, b] : [b, a];
  for (let i = 0; i < l.length; i++) if (l.slice(0, i) + l.slice(i + 1) === c) return true;
  return false;
}

// ---------- crittografia ----------

const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
const daHex = h => new Uint8Array(h.match(/../g).map(x => parseInt(x, 16)));

async function sha256(s) { return hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))); }

async function pbkdf2(password, saleHex, iter) {
  const k = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: daHex(saleHex), iterations: iter }, k, 256);
  return hex(bits);
}

function uguali(a, b) {
  if (a.length !== b.length) return false;
  let d = 0; for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

function nuovoToken() {
  const b = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// ---------- sessione ----------

async function officinaDaSessione(req, env) {
  const a = req.headers.get('Authorization') || '';
  const m = a.match(/^Bearer ([A-Za-z0-9_-]{20,100})$/);
  if (!m && env.ACCESSO_LIBERO) {
    // FASE DI PROVA: senza login tutte le richieste finiscono nell'officina indicata in wrangler.toml.
    // Prima del lancio togliere ACCESSO_LIBERO da wrangler.toml e ridistribuire.
    const o = await env.DB.prepare('SELECT id, nome, attiva FROM officine WHERE email = ?').bind(env.ACCESSO_LIBERO).first();
    if (!o || !o.attiva) throw new Errore(401, 'Officina di prova non disponibile.');
    return o;
  }
  if (!m) throw new Errore(401, 'Accesso richiesto.');
  const r = await env.DB.prepare(
    `SELECT s.officina_id AS id, s.scade, o.attiva, o.nome FROM sessioni s JOIN officine o ON o.id = s.officina_id WHERE s.token_hash = ?`
  ).bind(await sha256(m[1])).first();
  if (!r || r.scade < ora() || !r.attiva) throw new Errore(401, 'Sessione scaduta: accedi di nuovo.');
  return r;
}

// ---------- instradamento ----------

async function instrada(req, env) {
  const u = new URL(req.url);
  const p = u.pathname.replace(/\/+$/, '') || '/';
  const M = req.method;

  if (p === '/' && M === 'GET') return json({ servizio: 'ID TPMS TRUCK', ok: true });
  if (p === '/login' && M === 'POST') return login(req, env);

  const off = await officinaDaSessione(req, env);
  if (p === '/logout' && M === 'POST') {
    await env.DB.prepare('DELETE FROM sessioni WHERE token_hash = ?')
      .bind(await sha256((req.headers.get('Authorization') || '').slice(7))).run();
    return json({ ok: true });
  }
  if (p === '/io' && M === 'GET') return json({ officina: { nome: off.nome } });
  if (p === '/mezzi' && M === 'POST') return creaMezzo(req, env, off);

  let m = p.match(/^\/mezzi\/([^/]+)$/);
  if (m) {
    const targa = normTarga(decodeURIComponent(m[1]));
    if (M === 'GET') return leggiMezzo(env, off, targa);
    if (M === 'PATCH') return modificaMezzo(req, env, off, targa);
    if (M === 'DELETE') return eliminaMezzo(env, off, targa);
  }
  m = p.match(/^\/mezzi\/([^/]+)\/ruote\/([^/]+)$/);
  if (m) {
    const targa = normTarga(decodeURIComponent(m[1]));
    const pos = decodeURIComponent(m[2]);
    if (M === 'PUT') return salvaRuota(req, env, off, targa, pos);
    if (M === 'DELETE') return cancellaRuota(req, env, off, targa, pos);
  }
  throw new Errore(404, 'Indirizzo non trovato.');
}

// ---------- login ----------

async function login(req, env) {
  const b = await corpo(req);
  const email = String(b.email || '').trim().toLowerCase();
  const password = String(b.password || '');
  if (!email || !password || email.length > 200 || password.length > 200) throw new Errore(400, 'Mail e password sono obbligatorie.');
  const o = await env.DB.prepare('SELECT * FROM officine WHERE email = ?').bind(email).first();
  const sbagliate = new Errore(401, 'Mail o password non corrette.');
  if (!o) { await pbkdf2(password, '00'.repeat(16), 20000); throw sbagliate; } // stessi tempi
  if (o.blocco_fino && o.blocco_fino > ora()) throw new Errore(429, `Troppi tentativi: riprova tra ${BLOCCO_MINUTI} minuti.`);
  if (!o.attiva) throw new Errore(403, 'Utenza sospesa: contatta il tuo agente MAK.');
  const h = await pbkdf2(password, o.pwd_sale, o.pwd_iter);
  if (!uguali(h, o.pwd_hash)) {
    const t = o.tentativi + 1;
    const blocco = t >= MAX_TENTATIVI ? new Date(Date.now() + BLOCCO_MINUTI * 60000).toISOString() : null;
    await env.DB.prepare('UPDATE officine SET tentativi = ?, blocco_fino = ? WHERE id = ?').bind(blocco ? 0 : t, blocco, o.id).run();
    throw sbagliate;
  }
  const token = nuovoToken();
  const scade = new Date(Date.now() + SESSIONE_GIORNI * 86400000).toISOString();
  await env.DB.batch([
    env.DB.prepare('INSERT INTO sessioni (token_hash, officina_id, scade) VALUES (?, ?, ?)').bind(await sha256(token), o.id, scade),
    env.DB.prepare('UPDATE officine SET tentativi = 0, blocco_fino = NULL, ultimo_accesso = ? WHERE id = ?').bind(ora(), o.id),
    env.DB.prepare('DELETE FROM sessioni WHERE scade < ?').bind(ora()),
  ]);
  return json({ token, officina: { nome: o.nome } });
}

// ---------- mezzi ----------

async function trovaMezzo(env, off, targa) {
  return env.DB.prepare('SELECT * FROM mezzi WHERE officina_id = ? AND targa = ?').bind(off.id, targa).first();
}

async function schedaMezzo(env, m) {
  const r = await env.DB.prepare(
    'SELECT posizione, sensore_id, id_precedente, aggiornato, versione FROM ruote WHERE mezzo_id = ? ORDER BY posizione'
  ).bind(m.id).all();
  return {
    mezzo: {
      targa: m.targa, tipo: m.tipo,
      configurazione: m.configurazione_json ? JSON.parse(m.configurazione_json) : null,
      creato: m.creato, aggiornato: m.aggiornato,
    },
    ruote: r.results || [],
  };
}

async function simili(env, off, targa) {
  const r = await env.DB.prepare('SELECT targa, tipo FROM mezzi WHERE officina_id = ?').bind(off.id).all();
  return (r.results || []).filter(x => distanza1(x.targa, targa)).slice(0, 5);
}

async function leggiMezzo(env, off, targa) {
  const m = await trovaMezzo(env, off, targa);
  if (!m) throw new Errore(404, 'Targa non trovata.', { simili: await simili(env, off, targa) });
  return json(await schedaMezzo(env, m));
}

async function creaMezzo(req, env, off) {
  const b = await corpo(req);
  const targa = normTarga(b.targa);
  if (!TIPI.includes(b.tipo)) throw new Errore(400, 'Tipo di mezzo non valido.');
  const esiste = await trovaMezzo(env, off, targa);
  if (esiste) return json({ esistente: true, ...(await schedaMezzo(env, esiste)) }, 200);
  const t = ora();
  await env.DB.prepare('INSERT INTO mezzi (officina_id, targa, tipo, creato, aggiornato) VALUES (?, ?, ?, ?, ?)')
    .bind(off.id, targa, b.tipo, t, t).run();
  const m = await trovaMezzo(env, off, targa);
  return json({ esistente: false, simili: await simili(env, off, targa), ...(await schedaMezzo(env, m)) }, 201);
}

async function modificaMezzo(req, env, off, targa) {
  const b = await corpo(req);
  const m = await trovaMezzo(env, off, targa);
  if (!m) throw new Errore(404, 'Targa non trovata.');
  const st = [];
  const t = ora();
  if (b.configurazione !== undefined) {
    const c = controllaConfigurazione(b.configurazione);
    const valide = posizioni(c);
    st.push(env.DB.prepare('UPDATE mezzi SET configurazione_json = ?, aggiornato = ? WHERE id = ?').bind(JSON.stringify(c), t, m.id));
    // le ruote che non esistono nella nuova configurazione si eliminano (l'app chiede conferma prima)
    st.push(env.DB.prepare(
      `DELETE FROM ruote WHERE mezzo_id = ? AND posizione NOT IN (${valide.map(() => '?').join(',')})`
    ).bind(m.id, ...valide));
  }
  let nuova = targa;
  if (b.nuova_targa !== undefined) {
    nuova = normTarga(b.nuova_targa);
    if (nuova !== targa) {
      if (await trovaMezzo(env, off, nuova)) throw new Errore(409, 'Esiste già un mezzo con questa targa.');
      st.push(env.DB.prepare('UPDATE mezzi SET targa = ?, aggiornato = ? WHERE id = ?').bind(nuova, t, m.id));
    }
  }
  if (!st.length) throw new Errore(400, 'Niente da modificare.');
  await env.DB.batch(st);
  return json(await schedaMezzo(env, await trovaMezzo(env, off, nuova)));
}

async function eliminaMezzo(env, off, targa) {
  const m = await trovaMezzo(env, off, targa);
  if (!m) throw new Errore(404, 'Targa non trovata.');
  await env.DB.batch([
    env.DB.prepare('DELETE FROM ruote WHERE mezzo_id = ?').bind(m.id),
    env.DB.prepare('DELETE FROM mezzi WHERE id = ? AND officina_id = ?').bind(m.id, off.id),
  ]);
  return json({ ok: true });
}

// ---------- ruote ----------

async function ruotaDelMezzo(env, off, targa, pos) {
  if (!RE_POS.test(pos)) throw new Errore(400, 'Posizione non valida.');
  const m = await trovaMezzo(env, off, targa);
  if (!m) throw new Errore(404, 'Targa non trovata.');
  if (!m.configurazione_json) throw new Errore(409, 'Configurazione assi non ancora impostata.');
  if (!posizioni(JSON.parse(m.configurazione_json)).includes(pos)) throw new Errore(400, 'Questa ruota non esiste nello schema del mezzo.');
  const r = await env.DB.prepare('SELECT * FROM ruote WHERE mezzo_id = ? AND posizione = ?').bind(m.id, pos).first();
  return { m, r };
}

async function salvaRuota(req, env, off, targa, pos) {
  const b = await corpo(req);
  const id = normId(b.sensore_id);
  const versione = Number.isInteger(b.versione) ? b.versione : -1;
  const { m, r } = await ruotaDelMezzo(env, off, targa, pos);
  const attuale = r ? r.versione : 0;
  if (versione !== attuale) {
    throw new Errore(409, 'Un altro dispositivo ha cambiato questa ruota nel frattempo.', {
      attuale: r ? { sensore_id: r.sensore_id, id_precedente: r.id_precedente, aggiornato: r.aggiornato, versione: r.versione } : null,
    });
  }
  const t = ora();
  if (r && r.sensore_id === id) return json(await schedaMezzo(env, m));
  if (r) {
    const ok = await env.DB.prepare(
      'UPDATE ruote SET id_precedente = sensore_id, sensore_id = ?, aggiornato = ?, versione = versione + 1 WHERE mezzo_id = ? AND posizione = ? AND versione = ?'
    ).bind(id, t, m.id, pos, attuale).run();
    if (!ok.meta.changes) throw new Errore(409, 'Un altro dispositivo ha cambiato questa ruota nel frattempo.');
  } else {
    try {
      await env.DB.prepare('INSERT INTO ruote (mezzo_id, posizione, sensore_id, aggiornato, versione) VALUES (?, ?, ?, ?, 1)')
        .bind(m.id, pos, id, t).run();
    } catch (e) {
      throw new Errore(409, 'Un altro dispositivo ha salvato questa ruota nel frattempo.');
    }
  }
  await env.DB.prepare('UPDATE mezzi SET aggiornato = ? WHERE id = ?').bind(t, m.id).run();
  return json(await schedaMezzo(env, m));
}

async function cancellaRuota(req, env, off, targa, pos) {
  const b = await corpo(req);
  const { m, r } = await ruotaDelMezzo(env, off, targa, pos);
  if (!r) return json(await schedaMezzo(env, m));
  if (b.versione !== r.versione) throw new Errore(409, 'Un altro dispositivo ha cambiato questa ruota nel frattempo.');
  await env.DB.prepare('DELETE FROM ruote WHERE mezzo_id = ? AND posizione = ? AND versione = ?').bind(m.id, pos, r.versione).run();
  return json(await schedaMezzo(env, m));
}
