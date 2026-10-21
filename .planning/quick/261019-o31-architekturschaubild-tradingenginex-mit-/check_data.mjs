import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const STATUSES = ['umgesetzt', 'umgesetzt-override', 'teilweise', 'teilweise-p6', 'offen', 'verworfen-override'];
const INFL = ['entscheidet', 'eingabe', 'nachauswertung', 'leitplanke', 'ablauf', 'keiner'];

export function loadData(src) {
  const ctx = vm.createContext({});
  vm.runInContext(src + '\n;this.__d = TEX_DATA;', ctx);
  return ctx.__d;
}

function tally(reqs) {
  const t = { total: reqs.length, umgesetzt: 0, teilweise: 0, p6: 0, offen: 0, verworfen: 0, override: 0 };
  for (const r of reqs) {
    if (r.status === 'umgesetzt' || r.status === 'umgesetzt-override') t.umgesetzt++;
    if (r.status === 'umgesetzt-override') t.override++;
    if (r.status === 'teilweise' || r.status === 'teilweise-p6') t.teilweise++;
    if (r.status === 'teilweise-p6') t.p6++;
    if (r.status === 'offen') t.offen++;
    if (r.status === 'verworfen-override') t.verworfen++;
  }
  return t;
}

export function summarize(D) {
  const by = s => D.requirements.filter(r => r.source === s);
  return { M1: tally(by('M1')), M2: tally(by('M2')), Upstream: tally(by('Upstream')), Strang: tally(by('Strang')) };
}

export function checkData(D) {
  const err = [];
  const eq = (what, got, want) => { if (got !== want) err.push(what + ': ' + got + ' statt ' + want); };
  const S = summarize(D);
  const exp = {
    M1: { total: 13, umgesetzt: 9, teilweise: 1, p6: 0, offen: 2, verworfen: 1, override: 0 },
    M2: { total: 70, umgesetzt: 51, teilweise: 10, p6: 6, offen: 9, verworfen: 0, override: 2 },
    Upstream: { total: 35, umgesetzt: 34, teilweise: 0, p6: 0, offen: 1, verworfen: 0, override: 0 },
    Strang: { total: 9, umgesetzt: 8, teilweise: 1, p6: 1, offen: 0, verworfen: 0, override: 0 },
  };
  for (const k of Object.keys(exp)) for (const f of Object.keys(exp[k])) eq(k + '.' + f, S[k][f], exp[k][f]);
  eq('Summe Anforderungen', D.requirements.length, 127);
  // M1 ohne die zwei Zusatzpunkte (11 P1/P2-Punkte): 7/1/2/1 nach Codex 261019-oxc
  const p12 = summarize({ requirements: D.requirements.filter(r => r.source === 'M1' && r.subsource !== 'M1-Zusatz') }).M1;
  eq('M1 P1/P2 total', p12.total, 11); eq('M1 P1/P2 umgesetzt', p12.umgesetzt, 7); eq('M1 P1/P2 teilweise', p12.teilweise, 1); eq('M1 P1/P2 offen', p12.offen, 2); eq('M1 P1/P2 verworfen', p12.verworfen, 1);
  eq('M1-Zusatz', D.requirements.filter(r => r.subsource === 'M1-Zusatz').length, 2);
  eq('M1-Zusatz umgesetzt', D.requirements.filter(r => r.subsource === 'M1-Zusatz' && r.status === 'umgesetzt').length, 2);
  const ids = D.requirements.map(r => r.id);
  eq('eindeutige IDs', new Set(ids).size, ids.length);
  const seq = (prefix, n, pad) => { for (let i = 1; i <= n; i++) { const id = prefix + String(i).padStart(pad, '0'); if (!ids.includes(id)) err.push('fehlt: ' + id); } };
  seq('REQ-IBKR-', 70, 2); seq('U-', 35, 2); seq('S-', 9, 2);
  const compIds = new Set(D.components.map(c => c.id));
  eq('Komponenten', D.components.length, 20);
  for (const r of D.requirements) {
    if (!STATUSES.includes(r.status)) err.push(r.id + ': status ' + r.status);
    if (!['upstream', 'strang'].includes(r.originKind)) err.push(r.id + ': originKind ' + r.originKind);
    if (!compIds.has(r.comp)) err.push(r.id + ': comp ' + r.comp);
    if (!r.title || !r.evidence) err.push(r.id + ': leerer Titel/Nachweis');
  }
  const real = D.nodes.filter(n => !n.terminal);
  eq('Knoten (ohne Terminal)', real.length, 65);
  const nodeIds = D.nodes.map(n => n.id);
  eq('eindeutige Knoten-IDs', new Set(nodeIds).size, nodeIds.length);
  const zoneIds = new Set(D.zones.map(z => z.id));
  eq('Zonen', D.zones.length, 6);
  for (const n of D.nodes) {
    if (!zoneIds.has(n.zone)) err.push(n.id + ': zone ' + n.zone);
    for (const c of n.comps) if (!compIds.has(c)) err.push(n.id + ': comp ' + c);
  }
  for (const c of compIds) if (!real.some(n => n.comps.includes(c))) err.push('Komponente ohne Knoten: ' + c);
  const cnt = s => D.edges.filter(e => e.src === s).length;
  eq('Kanten 2a', cnt('2a'), 21); eq('Kanten 2b', cnt('2b'), 25); eq('Kanten abgeleitet', cnt('abgeleitet'), 27);
  for (const e of D.edges) { if (!nodeIds.includes(e.from)) err.push('Kante from ' + e.from); if (!nodeIds.includes(e.to)) err.push('Kante to ' + e.to); }
  const m = g => D.methods.filter(x => x.group === g).length;
  eq('Methoden stochastisch', m('stochastisch'), 8); eq('Methoden heuristisch', m('heuristisch'), 11); eq('Methoden semantisch', m('semantisch'), 8);
  for (const x of D.methods) if (!INFL.includes(x.influenceKind)) err.push(x.method + ': influenceKind');
  eq('Antwort', D.answer.length, 5);
  eq('Befunde', D.findings.length, 9);
  eq('meta.head', D.meta.head, '5f1998a');
  if (!String(D.meta.upstream).includes('e8f5503')) err.push('meta.upstream ohne e8f5503');
  return err;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const file = process.argv[2] || path.join(here, 'arch-data.js');
  const D = loadData(fs.readFileSync(file, 'utf8'));
  const err = checkData(D);
  const S = summarize(D);
  const f = t => t.total + ' (' + t.umgesetzt + ' umgesetzt davon ' + t.override + ' Override / ' + t.teilweise + ' teilweise davon ' + t.p6 + ' Phase 6 / ' + t.offen + ' offen / ' + t.verworfen + ' verworfen)';
  console.log('M1 ' + f(S.M1)); console.log('M2 ' + f(S.M2)); console.log('Upstream ' + f(S.Upstream)); console.log('Strang ' + f(S.Strang));
  console.log('Summe ' + D.requirements.length + '; Knoten ' + D.nodes.filter(n => !n.terminal).length + '; Kanten ' + ['2a', '2b', 'abgeleitet'].map(s => D.edges.filter(e => e.src === s).length).join('/') +
    '; Methoden ' + ['stochastisch', 'heuristisch', 'semantisch'].map(g => D.methods.filter(x => x.group === g).length).join('/') + '; Antwort ' + D.answer.length + '; Befunde ' + D.findings.length);
  if (err.length) { console.error('FEHLER:\n - ' + err.join('\n - ')); process.exit(1); }
  console.log('OK');
}
