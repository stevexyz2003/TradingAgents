import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkData, loadData } from './check_data.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(here, 'architektur.html'), 'utf8');
const err = [];
const bad = (m) => err.push(m);

// (1) Vertrag: Kopf
if (!/^\s*<title>TradingEngineX Architektur<\/title>\s*<style>/.test(html)) bad('Seite beginnt nicht mit <title>…</title><style>');
if (/<!doctype|<html|<head|<body|<iframe/i.test(html)) bad('verbotenes Tag (doctype/html/head/body/iframe)');

// Skripte und CSS trennen
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const styleM = html.match(/<style>([\s\S]*?)<\/style>/);
const css = styleM ? styleM[1] : '';
if (scripts.length !== 2) bad('erwartet 2 Inline-Skripte, gefunden ' + scripts.length);
const dataBlock = scripts[0] || '';
const renderJs = scripts[1] || '';
const markup = html.replace(/<script>[\s\S]*?<\/script>/g, '').replace(/<style>[\s\S]*?<\/style>/, '');

// (2) verbotene Muster nur in Render-Skript, CSS, Markup (nicht im Datenblock)
const code = renderJs + '\n' + css + '\n' + markup;
const forbidden = [[/\balert\(/, 'alert('], [/\bconfirm\(/, 'confirm('], [/\bprompt\(/, 'prompt('], [/window\.print/, 'window.print'], [/\bprint\(\)/, 'print()'],
  [/\sdownload\b/, ' download'], [/\bfetch\(/, 'fetch('], [/XMLHttpRequest/, 'XMLHttpRequest'], [/@import/, '@import'], [/<link\b/i, '<link'], [/url\(#/, 'url(#'], [/\binnerHTML\b/, 'innerHTML'], [/\beval\(/, 'eval(']];
forbidden.forEach(([re, name]) => { if (re.test(code)) bad('verbotenes Muster: ' + name); });

// (3) URLs
const allowedHosts = ['cdnjs.cloudflare.com', 'cdn.jsdelivr.net', 'unpkg.com', 'fonts.googleapis.com', 'fonts.gstatic.com'];
for (const m of html.matchAll(/https?:\/\/[^\s"'<>)]+/g)) {
  const u = m[0];
  if (u === 'http://www.w3.org/2000/svg') continue;
  let host = ''; try { host = new URL(u).host; } catch { /* ignore */ }
  if (!allowedHosts.includes(host)) bad('URL mit nicht erlaubtem Host: ' + u);
}

// (4) Skript-Syntax und Datenprüfung
scripts.forEach((s, i) => { try { new vm.Script(s); } catch (e) { bad('Skript ' + (i + 1) + ' parst nicht: ' + e.message); } });
try { const D = loadData(dataBlock); checkData(D).forEach(e => bad('Daten: ' + e)); } catch (e) { bad('Datenblock nicht ausführbar: ' + e.message); }

// (5) CSS-Marker
const markers = [[/@media\s*\(prefers-color-scheme:\s*dark\)/, '@media dark'], [/:root:not\(\[data-theme="light"\]\)/, ':root:not(light)'], [/:root\[data-theme="dark"\]/, ':root[data-theme=dark]'],
  [/color-scheme:\s*dark/, 'color-scheme: dark'], [/prefers-reduced-motion/, 'reduced-motion'], [/:focus-visible/, ':focus-visible'], [/tabular-nums/, 'tabular-nums'], [/padding-inline/, 'padding-inline'], [/overflow-x:\s*auto/, 'overflow-x: auto']];
markers.forEach(([re, n]) => { if (!re.test(css)) bad('CSS-Marker fehlt: ' + n); });
if (/opacity:\s*0[;}\s]/.test(css)) bad('opacity: 0 im CSS');
// beide Dark-Blöcke tragen dieselben Token wie :root
const tokensOf = (block) => [...block.matchAll(/(--[a-z0-9-]+)\s*:/g)].map(m => m[1]).sort().join(',');
const rootBlock = (css.match(/:root\s*\{([\s\S]*?)\n\}/) || [])[1] || '';
const darkMedia = (css.match(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{([\s\S]*?)\n  \}/) || [])[1] || '';
const darkAttr = (css.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/) || [])[1] || '';
if (!rootBlock || tokensOf(rootBlock) !== tokensOf(darkMedia)) bad('Token-Liste Dark (Media) weicht von :root ab');
if (!rootBlock || tokensOf(rootBlock) !== tokensOf(darkAttr)) bad('Token-Liste Dark (data-theme) weicht von :root ab');

// (6) Farbliterale außerhalb der Token-Blöcke
const cssRest = css.replace(/:root\s*\{[\s\S]*?\n\}/, '').replace(/@media \(prefers-color-scheme: dark\)\s*\{[\s\S]*?\n  \}\n\}/, '').replace(/:root\[data-theme="dark"\]\s*\{[\s\S]*?\n\}/, '');
if (/#[0-9a-fA-F]{3,8}\b/.test(cssRest) || /\b(rgb|rgba|hsl|hsla|oklch)\(/.test(cssRest)) bad('Farbliteral im CSS außerhalb der Token-Blöcke');
if (/["']#[0-9a-fA-F]{3,8}["']/.test(renderJs)) bad('Hex-Farbliteral im Render-Skript');

// (7) Pflichtinhalte
['2026-10-19', 'b0989aa', 'e8f5503'].forEach(s => { if (!html.includes(s)) bad('Stand-Wert fehlt: ' + s); });
['f-source', 'f-status', 'f-comp', 'f-origin', 'f-search', 'f-reset', 'theme-toggle'].forEach(id => { if (!markup.includes('id="' + id + '"')) bad('ID fehlt im Markup: ' + id); });
if (!renderJs.includes('data-node')) bad('data-node fehlt im Render-Skript');
if (!/TEX_DATA/.test(renderJs)) bad('Render-Skript liest TEX_DATA nicht');

if (err.length) { console.error('PAGE FEHLER:\n - ' + err.join('\n - ')); process.exit(1); }
console.log('PAGE OK');
