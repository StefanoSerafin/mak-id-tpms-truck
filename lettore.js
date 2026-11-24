/* ID TPMS TRUCK - lettore delle schermate ATEQ VT Truck 2.0
 *
 * Tutto gira sul telefono: la foto non esce mai dal dispositivo.
 * Passi: ruote verdi + riquadro rosso -> schema e configurazione assi -> riga dell'ID sotto lo schema
 * -> caratteri confrontati con i modelli del display (modelli.js).
 *
 * window.Lettore.leggiFile(file)            -> Promise<ImageData> (lato lungo max 1600 px, orientamento corretto)
 * window.Lettore.analizza(imageData, modelli) -> risultato (vedi in fondo)
 * window.Lettore.celle(imageData, attese)   -> campioni dei caratteri, solo per strumenti/crea_modelli.py
 */
(function () {
  'use strict';
  const LATO_MAX = 1600;
  const MW = 20, MH = 30;               // dimensione normalizzata di un carattere
  const PASSO_PREDEFINITO = 0.69;       // passo dei caratteri / altezza riga, se manca nei modelli

  // ---------- immagine ----------

  function leggiFile(file) {
    return new Promise((ok, ko) => {
      const url = URL.createObjectURL(file);
      const im = new Image();
      im.onload = () => {
        try {
          const s = Math.min(1, LATO_MAX / Math.max(im.naturalWidth, im.naturalHeight));
          const w = Math.round(im.naturalWidth * s), h = Math.round(im.naturalHeight * s);
          const c = document.createElement('canvas'); c.width = w; c.height = h;
          const x = c.getContext('2d', { willReadFrequently: true });
          x.drawImage(im, 0, 0, w, h);   // i browser applicano già l'orientamento EXIF
          URL.revokeObjectURL(url);
          ok(x.getImageData(0, 0, w, h));
        } catch (e) { URL.revokeObjectURL(url); ko(e); }
      };
      im.onerror = () => { URL.revokeObjectURL(url); ko(new Error('Foto non leggibile')); };
      im.src = url;
    });
  }

  function grigi(img) {
    const d = img.data, n = img.width * img.height, g = new Uint8ClampedArray(n);
    for (let i = 0, j = 0; i < n; i++, j += 4) g[i] = (d[j] * 299 + d[j + 1] * 587 + d[j + 2] * 114) / 1000;
    return g;
  }

  // ---------- componenti connesse ----------

  function componenti(maschera, W, H, areaMin) {
    const lab = new Int32Array(W * H), out = [], pila = new Int32Array(W * H);
    let id = 0;
    for (let p = 0; p < W * H; p++) {
      if (!maschera[p] || lab[p]) continue;
      id++;
      let sp = 0, area = 0, x0 = W, x1 = 0, y0 = H, y1 = 0, sx = 0, sy = 0;
      pila[sp++] = p; lab[p] = id;
      while (sp) {
        const q = pila[--sp], x = q % W, y = (q - x) / W;
        area++; sx += x; sy += y;
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
        if (x > 0 && maschera[q - 1] && !lab[q - 1]) { lab[q - 1] = id; pila[sp++] = q - 1; }
        if (x < W - 1 && maschera[q + 1] && !lab[q + 1]) { lab[q + 1] = id; pila[sp++] = q + 1; }
        if (y > 0 && maschera[q - W] && !lab[q - W]) { lab[q - W] = id; pila[sp++] = q - W; }
        if (y < H - 1 && maschera[q + W] && !lab[q + W]) { lab[q + W] = id; pila[sp++] = q + W; }
      }
      if (area >= areaMin) out.push({ area, x0, x1: x1 + 1, y0, y1: y1 + 1, cx: sx / area, cy: sy / area, w: x1 + 1 - x0, h: y1 + 1 - y0 });
    }
    return out;
  }

  const mediana = a => { if (!a.length) return 0; const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };

  // ---------- schema del mezzo ----------

  function trovaSchema(img) {
    const { width: W, height: H, data: d } = img;
    const verde = new Uint8Array(W * H);
    for (let i = 0, j = 0; i < W * H; i++, j += 4) {
      const r = d[j], g = d[j + 1], b = d[j + 2];
      verde[i] = g > 85 && g > 1.6 * r + 10 && g > 1.6 * b + 10 ? 1 : 0;
    }
    const areaMin = Math.max(40, W * H * 0.00004);
    // ruote: rettangoli orizzontali pieni
    const cand = componenti(verde, W, H, areaMin)
      .filter(c => c.w / c.h > 1.2 && c.w / c.h < 7 && c.area / (c.w * c.h) > 0.45);
    if (cand.length < 2) return null;

    // gruppo principale: ruote vicine tra loro (esclude il led wifi e riflessi)
    const n = cand.length, padre = cand.map((_, i) => i);
    const radice = i => (padre[i] === i ? i : (padre[i] = radice(padre[i])));
    // vicine in verticale (ruote dello stesso asse) o sulla stessa fascia orizzontale anche lontane
    // (trattore e rimorchio sulla stessa schermata)
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const a = cand[i], b = cand[j], hh = Math.max(a.h, b.h, 6);
      const dx = Math.max(0, Math.max(a.x0, b.x0) - Math.min(a.x1, b.x1));
      const dy = Math.max(0, Math.max(a.y0, b.y0) - Math.min(a.y1, b.y1));
      const stessaFascia = Math.abs(a.cy - b.cy) < 0.8 * hh;
      if ((dx < 5 * hh && dy < 7.5 * hh) || (stessaFascia && dx < 14 * hh)) padre[radice(i)] = radice(j);
    }
    const gruppi = {};
    cand.forEach((c, i) => (gruppi[radice(i)] = gruppi[radice(i)] || []).push(c));
    const ruote = Object.values(gruppi).sort((a, b) => b.length - a.length || b.reduce((s, c) => s + c.area, 0) - a.reduce((s, c) => s + c.area, 0))[0];
    if (!ruote || ruote.length < 2) return null;

    let x0 = Math.min(...ruote.map(c => c.x0)), x1 = Math.max(...ruote.map(c => c.x1));
    let y0 = Math.min(...ruote.map(c => c.y0)), y1 = Math.max(...ruote.map(c => c.y1));
    const hS = y1 - y0;
    if (hS < 20) return null;

    // riquadro rosso: la ruota appena letta
    const m = Math.round(0.15 * hS);
    let rn = 0, rx = 0, ry = 0;
    for (let y = Math.max(0, y0 - m); y < Math.min(H, y1 + m); y++) for (let x = Math.max(0, x0 - m); x < Math.min(W, x1 + m); x++) {
      const j = (y * W + x) * 4, r = d[j], g = d[j + 1], b = d[j + 2];
      if (r > 100 && r > 2 * g + 10 && r > 2 * b + 10) { rn++; rx += x; ry += y; }
    }
    const rosso = rn > Math.max(15, hS * 0.3) ? { cx: rx / rn, cy: ry / rn } : null;

    // centri ruota, uniti se coincidono (la ruota nel riquadro rosso compare una volta sola)
    const wMed = mediana(ruote.map(c => c.w)), hMed = mediana(ruote.map(c => c.h));
    const centri = [];
    for (const p of [...ruote.map(c => ({ cx: c.cx, cy: c.cy })), ...(rosso ? [rosso] : [])]) {
      if (!centri.some(q => Math.abs(q.cx - p.cx) < 0.5 * wMed && Math.abs(q.cy - p.cy) < 0.6 * hMed)) centri.push(p);
    }

    // assi: centri con la stessa x
    const perX = [...centri].sort((a, b) => a.cx - b.cx);
    const assi = [];
    for (const p of perX) {
      const ult = assi[assi.length - 1];
      if (ult && p.cx - ult.x < 0.6 * wMed) { ult.ruote.push(p); ult.x = ult.ruote.reduce((s, q) => s + q.cx, 0) / ult.ruote.length; }
      else assi.push({ x: p.cx, ruote: [p] });
    }
    assi.forEach(a => a.ruote.sort((p, q) => p.cy - q.cy));
    const conf = assi.map(a => a.ruote.length);
    const valida = conf.every(k => k === 2 || k === 4);

    // gruppi di assi: trattore/motrice e rimorchio sulla stessa schermata (regola da verificare sul campo)
    let taglio = -1;
    if (assi.length >= 3) {
      const gap = assi.slice(1).map((a, i) => a.x - assi[i].x);
      const ord = gap.map((g, i) => [g, i]).sort((a, b) => b[0] - a[0]);
      if (ord[0][0] > 1.5 * ord[1][0] && ord[0][0] > 2 * mediana(gap)) taglio = ord[0][1];
    }
    const gruppiAssi = taglio < 0 ? [assi] : [assi.slice(0, taglio + 1), assi.slice(taglio + 1)];

    // ruota evidenziata
    let ruota = null;
    if (rosso && valida) {
      const ia = assi.reduce((b, a, i) => (Math.abs(a.x - rosso.cx) < Math.abs(assi[b].x - rosso.cx) ? i : b), 0);
      const a = assi[ia];
      const k = a.ruote.reduce((b, p, i) => (Math.abs(p.cy - rosso.cy) < Math.abs(a.ruote[b].cy - rosso.cy) ? i : b), 0);
      const n2 = a.ruote.length;
      const lato = k < n2 / 2 ? 'su' : 'giu';
      const pos = n2 === 4 && (k === 1 || k === 2) ? 'int' : 'est';
      const gruppo = taglio >= 0 && ia > taglio ? 1 : 0;
      const asseNelGruppo = gruppo === 1 ? ia - taglio : ia + 1;
      ruota = { gruppo, asse: asseNelGruppo, lato, pos, chiave: `A${asseNelGruppo}-${lato}-${pos}` };
    }

    return {
      x0, x1, y0, y1, h: hS,
      configurazione: valida ? conf : null,
      gruppi: valida ? gruppiAssi.map(g => g.map(a => a.ruote.length)) : null,
      ruota, rossoTrovato: !!rosso,
    };
  }

  // ---------- righe di testo e caratteri ----------

  function otsu(v) {
    const h = new Float64Array(256); for (const x of v) h[x]++;
    const n = v.length; let sum = 0; for (let i = 0; i < 256; i++) sum += i * h[i];
    let wB = 0, sB = 0, best = 0, t = 0;
    for (let i = 0; i < 256; i++) {
      wB += h[i]; if (!wB) continue; const wF = n - wB; if (!wF) break;
      sB += i * h[i]; const mB = sB / wB, mF = (sum - sB) / wF, s = wB * wF * (mB - mF) * (mB - mF);
      if (s > best) { best = s; t = i; }
    }
    return t;
  }

  // ritaglio in scala di grigi: {w, h, v}
  function ritaglia(g, W, H, x0, y0, x1, y1) {
    x0 = Math.max(0, Math.round(x0)); y0 = Math.max(0, Math.round(y0));
    x1 = Math.min(W, Math.round(x1)); y1 = Math.min(H, Math.round(y1));
    const w = Math.max(0, x1 - x0), h = Math.max(0, y1 - y0), v = new Uint8ClampedArray(w * h);
    for (let y = 0; y < h; y++) v.set(g.subarray((y0 + y) * W + x0, (y0 + y) * W + x0 + w), y * w);
    return { w, h, v, x0, y0 };
  }

  // righe di testo chiaro su fondo scuro
  function righe(r, altezzaMin) {
    const t = Math.max(otsu(r.v), 105), acc = new Uint8Array(r.w * r.h);
    for (let i = 0; i < acc.length; i++) acc[i] = r.v[i] > t ? 1 : 0;
    const out = []; let in0 = -1;
    for (let y = 0; y <= r.h; y++) {
      let c = 0; if (y < r.h) for (let x = 0; x < r.w; x++) c += acc[y * r.w + x];
      if (c > 2 && in0 < 0) in0 = y;
      if ((c <= 2 || y === r.h) && in0 >= 0) { if (y - in0 >= altezzaMin) out.push({ y0: in0, y1: y }); in0 = -1; }
    }
    return { righe: out, acc, t };
  }

  function colonne(r, acc, riga) {
    const col = new Uint8Array(r.w);
    for (let x = 0; x < r.w; x++) for (let y = riga.y0; y < riga.y1; y++) if (acc[y * r.w + x]) { col[x] = 1; break; }
    return col;
  }

  // prima parola della riga, interrotta da un vuoto largo
  function parola(col, vuotoMax, daDestra) {
    const idx = []; for (let x = 0; x < col.length; x++) if (col[x]) idx.push(x);
    if (!idx.length) return null;
    if (daDestra) {
      let fine = idx[idx.length - 1], ini = fine;
      for (let k = idx.length - 1; k > 0; k--) { if (idx[k] - idx[k - 1] > vuotoMax) break; ini = idx[k - 1]; }
      return { ini, fine };
    }
    let ini = idx[0], fine = ini;
    for (let k = 1; k < idx.length; k++) { if (idx[k] - idx[k - 1] > vuotoMax) break; fine = idx[k]; }
    return { ini, fine };
  }

  // carattere normalizzato MWxMH (valori 0-255) dalla cella [a,b) della riga
  function cella(r, riga, a, b) {
    a = Math.max(0, Math.round(a)); b = Math.min(r.w, Math.round(b));
    const y0 = Math.max(0, riga.y0 - 1), y1 = Math.min(r.h, riga.y1 + 1);
    if (b - a < 2) return null;
    const v = []; for (let y = y0; y < y1; y++) for (let x = a; x < b; x++) v.push(r.v[y * r.w + x]);
    const t = Math.max(otsu(Uint8ClampedArray.from(v)), 105);
    let bx0 = b, bx1 = a - 1, by0 = y1, by1 = y0 - 1;
    for (let y = y0; y < y1; y++) for (let x = a; x < b; x++) if (r.v[y * r.w + x] > t) {
      if (x < bx0) bx0 = x; if (x > bx1) bx1 = x; if (y < by0) by0 = y; if (y > by1) by1 = y;
    }
    if (bx1 < bx0 || by1 < by0) return null;
    const cw = bx1 - bx0 + 1, ch = by1 - by0 + 1, out = new Uint8ClampedArray(MW * MH);
    for (let j = 0; j < MH; j++) for (let i = 0; i < MW; i++) {
      // campionamento bilineare
      const sx = Math.min(cw - 1, Math.max(0, (i + 0.5) * cw / MW - 0.5)), sy = Math.min(ch - 1, Math.max(0, (j + 0.5) * ch / MH - 0.5));
      const xa = Math.floor(sx), ya = Math.floor(sy), xb = Math.min(cw - 1, xa + 1), yb = Math.min(ch - 1, ya + 1), fx = sx - xa, fy = sy - ya;
      const p = (x, y) => r.v[(by0 + y) * r.w + bx0 + x];
      out[j * MW + i] = (p(xa, ya) * (1 - fx) + p(xb, ya) * fx) * (1 - fy) + (p(xa, yb) * (1 - fx) + p(xb, yb) * fx) * fy;
    }
    return out;
  }

  function zeta(v) {
    let m = 0; for (const x of v) m += x; m /= v.length;
    let s = 0; for (const x of v) s += (x - m) * (x - m); s = Math.sqrt(s / v.length) || 1;
    return Float32Array.from(v, x => (x - m) / s);
  }

  // zone di testo sotto lo schema (proporzioni misurate sulle foto di Enrico)
  function zone(img, sc) {
    const g = grigi(img), W = img.width, H = img.height, h = sc.h;
    const sx = ritaglia(g, W, H, sc.x0 - 0.6 * h, sc.y1 + 0.12 * h, sc.x0 + 1.1 * h, sc.y1 + 0.8 * h);
    const dx = ritaglia(g, W, H, sc.x0 + 1.2 * h, sc.y1 + 0.12 * h, sc.x0 + 3.6 * h, sc.y1 + 0.8 * h);
    return { sx, dx, altezzaMin: Math.max(6, Math.round(0.06 * h)) };
  }

  // ---------- modelli ----------

  let cacheModelli = null, cacheFonte = null;
  function preparaModelli(m) {
    if (!m || !m.campioni) return null;
    if (cacheFonte === m) return cacheModelli;
    const out = {};
    for (const [c, lista] of Object.entries(m.campioni)) {
      out[c] = lista.map(b64 => { const s = atob(b64); return zeta(Uint8Array.from(s, ch => ch.charCodeAt(0))); });
    }
    cacheFonte = m; cacheModelli = out;
    return out;
  }

  function classifica(z, mod) {
    const pt = [];
    for (const [c, lista] of Object.entries(mod)) {
      let best = -2;
      for (const t of lista) { let s = 0; for (let i = 0; i < z.length; i++) s += z[i] * t[i]; s /= z.length; if (s > best) best = s; }
      pt.push([best, c]);
    }
    pt.sort((a, b) => b[0] - a[0]);
    return { c: pt[0][1], punteggio: pt[0][0], margine: pt[0][0] - (pt[1] ? pt[1][0] : -1), secondo: pt[1] ? pt[1][1] : null };
  }

  // ---------- lettura completa ----------

  function analizza(img, modelli) {
    const sc = trovaSchema(img);
    if (!sc) return { esito: 'schema_non_trovato', id: null, caratteri: [], configurazione: null, gruppi: null, ruota: null };
    const ris = { esito: 'ok', id: null, caratteri: [], configurazione: sc.configurazione, gruppi: sc.gruppi, ruota: sc.ruota, rossoTrovato: sc.rossoTrovato };
    const mod = preparaModelli(modelli);
    if (!mod) { ris.esito = 'senza_modelli'; return ris; }

    const z = zone(img, sc), r = z.sx;
    const { righe: rr, acc } = righe(r, z.altezzaMin);
    if (!rr.length) { ris.esito = 'id_non_trovato'; return ris; }
    const riga = rr[0], hR = riga.y1 - riga.y0;
    const passoStimato = (modelli.passo || PASSO_PREDEFINITO) * hR;
    const p = parola(colonne(r, acc, riga), 0.55 * passoStimato, false);
    if (!p) { ris.esito = 'id_non_trovato'; return ris; }
    const largh = p.fine - p.ini + 1;
    const n = Math.round(largh / passoStimato);
    if (n < 4 || n > 12) { ris.esito = 'id_non_trovato'; return ris; }
    const passo = largh / n;
    for (let i = 0; i < n; i++) {
      const c = cella(r, riga, p.ini + i * passo, p.ini + (i + 1) * passo);
      if (!c) { ris.esito = 'id_non_trovato'; return ris; }
      const k = classifica(zeta(c), mod);
      const prov = (modelli.provvisori || []).includes(k.c);
      // se ai modelli manca qualche carattere, un carattere mai visto verrebbe scambiato con il più simile:
      // si alza la soglia oltre la quale il carattere è considerato sicuro
      const soglia = (modelli.mancanti || []).length ? 0.75 : 0.55;
      ris.caratteri.push({ c: k.c, punteggio: +k.punteggio.toFixed(3), margine: +k.margine.toFixed(3), secondo: k.secondo,
        incerto: prov || k.punteggio < soglia || k.margine < 0.06 });
    }
    ris.id = ris.caratteri.map(x => x.c).join('');
    return ris;
  }

  // ---------- campioni per i modelli (solo strumenti) ----------
  // attese = {id: '5C307051', pressione: '133.4', temperatura: '71'}
  function celle(img, attese) {
    const sc = trovaSchema(img);
    if (!sc) return { errore: 'schema non trovato' };
    const z = zone(img, sc), out = { schema: sc, campioni: [], passo: null };
    const b64 = a => btoa(String.fromCharCode(...a));

    const L = righe(z.sx, z.altezzaMin);
    if (L.righe.length < 1) return { errore: 'righe non trovate', ...out };
    const rid = L.righe[0], hR = rid.y1 - rid.y0;
    const pid = parola(colonne(z.sx, L.acc, rid), 0.55 * PASSO_PREDEFINITO * hR, false);
    const passo = (pid.fine - pid.ini + 1) / attese.id.length;
    out.passo = passo / hR;
    [...attese.id].forEach((ch, i) => {
      const c = cella(z.sx, rid, pid.ini + i * passo, pid.ini + (i + 1) * passo);
      if (c) out.campioni.push({ c: ch, fonte: 'id', v: b64(c) });
    });
    if (attese.pressione && L.righe[1]) {
      const rp = L.righe[1], pp = parola(colonne(z.sx, L.acc, rp), 0.55 * passo, false);
      if (pp) [...attese.pressione].forEach((ch, i) => {
        if (!/[0-9A-F]/.test(ch)) return;
        const c = cella(z.sx, rp, pp.ini + i * passo, pp.ini + (i + 1) * passo);
        if (c) out.campioni.push({ c: ch, fonte: 'pressione', v: b64(c) });
      });
    }
    if (attese.temperatura) {
      const D = righe(z.dx, z.altezzaMin);
      const rt = D.righe[1];
      if (rt) {
        const pt = parola(colonne(z.dx, D.acc, rt), 0.9 * passo, true);
        // da destra: F, simbolo dei gradi, poi le cifre al contrario
        if (pt) [...attese.temperatura].reverse().forEach((ch, j) => {
          const fine = pt.fine + 1 - (j + 2) * passo;
          const c = cella(z.dx, rt, fine - passo, fine);
          if (c) out.campioni.push({ c: ch, fonte: 'temperatura', v: b64(c) });
        });
      }
    }
    return out;
  }

  window.Lettore = { leggiFile, analizza, celle, _trovaSchema: trovaSchema };
})();
