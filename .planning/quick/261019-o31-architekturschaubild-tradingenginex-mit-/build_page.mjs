import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const MARKER = '/*@@TEX_DATA@@*/';
const src = fs.readFileSync(path.join(here, 'page-src.html'), 'utf8').replace(/\r\n/g, '\n');
const data = fs.readFileSync(path.join(here, 'arch-data.js'), 'utf8').replace(/\r\n/g, '\n');
const n = src.split(MARKER).length - 1;
if (n !== 1) { console.error('Marker ' + MARKER + ' kommt ' + n + 'x vor (erwartet 1x)'); process.exit(1); }
const out = src.split(MARKER).join(data.replace(/<\/script/gi, '<\/script'));
fs.writeFileSync(path.join(here, 'architektur.html'), out, { encoding: 'utf8' });
console.log('architektur.html geschrieben: ' + out.length + ' Zeichen');
