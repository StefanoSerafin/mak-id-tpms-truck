-- ID TPMS TRUCK - database D1
-- Si applica con: npx -y wrangler@4 d1 execute mak-id-tpms-truck --remote --file worker/schema.sql
-- Nessuna foto, nessun nome di proprietari, flotte o operatori.

CREATE TABLE IF NOT EXISTS officine (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  nome            TEXT NOT NULL,
  email           TEXT NOT NULL UNIQUE,          -- mail aziendale, minuscolo
  pwd_hash        TEXT NOT NULL,                 -- PBKDF2-SHA256, esadecimale
  pwd_sale        TEXT NOT NULL,                 -- esadecimale
  pwd_iter        INTEGER NOT NULL DEFAULT 20000,
  attiva          INTEGER NOT NULL DEFAULT 1,
  agente          TEXT NOT NULL DEFAULT '',      -- agente MAK che ha chiesto l'attivazione
  creata          TEXT NOT NULL,
  ultimo_accesso  TEXT,
  tentativi       INTEGER NOT NULL DEFAULT 0,
  blocco_fino     TEXT
);

CREATE TABLE IF NOT EXISTS sessioni (
  token_hash   TEXT PRIMARY KEY,                 -- SHA-256 del token, mai il token
  officina_id  INTEGER NOT NULL REFERENCES officine(id) ON DELETE CASCADE,
  scade        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessioni_officina ON sessioni(officina_id);

CREATE TABLE IF NOT EXISTS mezzi (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  officina_id         INTEGER NOT NULL REFERENCES officine(id) ON DELETE CASCADE,
  targa               TEXT NOT NULL,             -- maiuscolo, solo lettere e cifre
  tipo                TEXT NOT NULL CHECK (tipo IN ('trattore_motrice','rimorchio_semirimorchio')),
  configurazione_json TEXT,                      -- es. [2,4,2]: ruote per asse, dalla prima foto
  creato              TEXT NOT NULL,
  aggiornato          TEXT NOT NULL,
  UNIQUE (officina_id, targa)
);

CREATE TABLE IF NOT EXISTS ruote (
  mezzo_id       INTEGER NOT NULL REFERENCES mezzi(id) ON DELETE CASCADE,
  posizione      TEXT NOT NULL,                  -- es. A2-su-int
  sensore_id     TEXT NOT NULL,
  id_precedente  TEXT,
  aggiornato     TEXT NOT NULL,
  versione       INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (mezzo_id, posizione)
);
