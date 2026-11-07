// Genera i file letti dall'harness a partire dalle fonti uniche del repository:
// - ../olimpo/piantina.html  -> src/generato/sala.json (il blocco <script id="sala"> della piantina; l'editor
//   ne riscrive una copia dentro una stringa JavaScript, per questo il tag deve stare a inizio riga)
// - ../agente/regole.md      -> src/generato/regole.ts (testo delle regole, per il prompt)
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const qui = dirname(fileURLToPath(import.meta.url));
const radice = join(qui, "..", "..");
const fuori = join(qui, "..", "src", "generato");
mkdirSync(fuori, { recursive: true });

const html = readFileSync(join(radice, "olimpo", "piantina.html"), "utf-8");
const blocchi = [...html.matchAll(/^<script type="application\/json" id="sala">([\s\S]*?)<\/script>/gm)];
if (blocchi.length !== 1) throw new Error(`piantina.html: atteso un blocco id="sala", trovati ${blocchi.length}`);
const sala = JSON.parse(blocchi[0][1]);
writeFileSync(join(fuori, "sala.json"), JSON.stringify(sala));

const regole = readFileSync(join(radice, "agente", "regole.md"), "utf-8").replace(/\r\n/g, "\n");
writeFileSync(join(fuori, "regole.ts"), `export const REGOLE = ${JSON.stringify(regole)};\n`);
console.log(`generato: ${sala.tavoli.length} tavoli, ${sala.turni.length} turni, regole ${regole.length} caratteri`);
