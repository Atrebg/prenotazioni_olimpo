// Gli strumenti che il modello può chiamare. Il modello propone, qui il codice controlla le regole dure e scrive.
// Niente viene scritto se il piano del turno non passa il validatore.
import type { Sala } from "./sala";
import type { Store } from "./store";
import type { Bozza, Prenotazione, Serata } from "./tipi";
import { controllaData, dataLocale, giornoSettimana, turnoPerOrario } from "./orari";
import { dimostratoPieno, punteggio, validaTurno, type Posto } from "./validatore";

export class ErroreStrumento extends Error {}

export interface Contesto {
  sala: Sala;
  store: Store;
  adesso: () => Date;
  mittente: string;
}

export interface Strumento {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  esegui: (args: any, ctx: Contesto) => Promise<unknown>;
}

type Args = Record<string, any>;

export const URL_PIANTINA = "https://atrebg.github.io/prenotazioni_olimpo/olimpo/piantina.html";
const MAX_OPZIONI = 5;
const MAX_SPOSTAMENTI_PROVATI = 1;

// ---------- aiuti ----------

function turnoIdx(sala: Sala, turno: unknown): number {
  const n = Number(turno);
  if (!Number.isInteger(n) || n < 1 || n > sala.turni.length) {
    throw new ErroreStrumento(`turno non valido: ${String(turno)} (1 = ${sala.turni[0].nome}, ${sala.turni.length} = ${sala.turni.at(-1)!.nome})`);
  }
  return n - 1;
}

function controllaDataCtx(ctx: Contesto, data: unknown): string {
  const d = String(data ?? "");
  const e = controllaData(d, dataLocale(ctx.adesso()));
  if (e) throw new ErroreStrumento(e);
  return d;
}

function copertiOk(sala: Sala, c: unknown): number {
  const n = Number(c);
  if (!Number.isInteger(n) || n < 1) throw new ErroreStrumento(`coperti non validi: ${String(c)}`);
  if (n > sala.capienzaMassima) throw new ErroreStrumento(`${n} coperti: il posto più grande della sala ne ha ${sala.capienzaMassima}`);
  return n;
}

const attive = (s: Serata, turno: number) => s.prenotazioni.filter((p) => p.stato === "accettata" && p.turno === turno);
const comePosto = (p: Prenotazione): Posto => ({ id: p.id, nome: p.nome, coperti: p.coperti, unita: p.unita });

function trovaPrenotazione(s: Serata, id: unknown): Prenotazione {
  const p = s.prenotazioni.find((x) => x.id === String(id) && x.stato === "accettata");
  if (!p) throw new ErroreStrumento(`prenotazione ${String(id)} non trovata (o già annullata) il ${s.data}`);
  return p;
}

/** Applica le riassegnazioni richieste alle prenotazioni del turno; le fissate non si toccano. */
function riassegna(s: Serata, turno: number, lista: unknown, tranne?: string): Map<string, string> {
  const mappa = new Map<string, string>();
  for (const r of (lista as { prenotazione_id: string; unita: string }[] | undefined) ?? []) {
    const p = trovaPrenotazione(s, r.prenotazione_id);
    if (p.turno !== turno) throw new ErroreStrumento(`${p.nome} è nell'altro turno: si riassegna solo dentro lo stesso turno`);
    if (p.id === tranne) continue;
    if (p.fissata && r.unita !== p.unita) {
      throw new ErroreStrumento(`${p.nome} è fissata dal proprietario: non si sposta senza che lo chieda (strumento "libera")`);
    }
    mappa.set(p.id, r.unita);
  }
  return mappa;
}

function pianoDelTurno(s: Serata, turno: number, cambi: Map<string, string>, aggiunta?: Posto): Posto[] {
  const posti = attive(s, turno).map((p) => ({ ...comePosto(p), unita: cambi.get(p.id) ?? p.unita }));
  if (aggiunta) posti.push(aggiunta);
  return posti;
}

function esigiPianoValido(sala: Sala, posti: Posto[]): void {
  const errori = validaTurno(sala, posti);
  if (errori.length) throw new ErroreStrumento(`piano non ammesso: ${errori.join("; ")}`);
}

async function salva(ctx: Contesto, s: Serata): Promise<void> {
  s.versione += 1;
  await ctx.store.salvaSerata(s);
}

function nomeTurno(sala: Sala, t: number): string {
  return `${sala.turni[t].nome} turno (${sala.turni[t].inizio})`;
}

function dataBreve(data: string): string {
  const [, m, g] = data.split("-");
  return `${giornoSettimana(data).slice(0, 3)} ${g}/${m}`;
}

function conferma(sala: Sala, p: Prenotazione): string {
  return `✓ ${p.nome} · ${p.coperti} ${p.coperti === 1 ? "persona" : "persone"} · ${dataBreve(p.data)} · ${nomeTurno(sala, p.turno)}${p.note ? ` · ${p.note}` : ""}`;
}

function vista(sala: Sala, p: Prenotazione) {
  return { id: p.id, nome: p.nome, coperti: p.coperti, unita: p.unita, dove: sala.etichetta(p.unita), fissata: !!p.fissata, note: p.note ?? null };
}

// ---------- ricerca di un posto ----------

interface Opzione {
  unita: string;
  dove: string;
  costo: number;
  posti_vuoti: number;
  sposta: { prenotazione_id: string; nome: string; da: string; a: string }[];
}

function cercaPostoNelTurno(sala: Sala, esistenti: Prenotazione[], coperti: number): Opzione[] {
  const base: Posto[] = esistenti.map(comePosto);
  const nuova = (u: string): Posto => ({ id: "nuova", nome: "(nuova)", coperti, unita: u });
  const candidate = sala.unita.filter((u) => u.posti >= coperti);
  const costoBase = punteggio(sala, base).costo;
  const opzioni: Opzione[] = [];

  for (const u of candidate) {
    const piano = [...base, nuova(u.chiave)];
    if (validaTurno(sala, piano).length) continue;
    const sc = punteggio(sala, piano);
    opzioni.push({ unita: u.chiave, dove: sala.etichetta(u.chiave), costo: sc.costo - costoBase, posti_vuoti: u.posti - coperti, sposta: [] });
  }
  if (opzioni.length || MAX_SPOSTAMENTI_PROVATI < 1) return ordina(opzioni);

  // nessun posto senza spostare nessuno: provo a spostare UNA prenotazione non fissata
  for (const b of esistenti) {
    if (b.fissata) continue;
    for (const u2 of sala.unita) {
      if (u2.chiave === b.unita || u2.posti < b.coperti) continue;
      const spostata = base.map((p) => (p.id === b.id ? { ...p, unita: u2.chiave } : p));
      if (validaTurno(sala, spostata).length) continue;
      for (const u of candidate) {
        const piano = [...spostata, nuova(u.chiave)];
        if (validaTurno(sala, piano).length) continue;
        opzioni.push({
          unita: u.chiave,
          dove: sala.etichetta(u.chiave),
          costo: punteggio(sala, piano).costo - costoBase,
          posti_vuoti: u.posti - coperti,
          sposta: [{ prenotazione_id: b.id, nome: b.nome, da: sala.etichetta(b.unita), a: sala.etichetta(u2.chiave) }],
        });
      }
    }
  }
  return ordina(opzioni);
}

function ordina(o: Opzione[]): Opzione[] {
  return o.sort((a, b) => a.sposta.length - b.sposta.length || a.costo - b.costo || a.unita.localeCompare(b.unita)).slice(0, MAX_OPZIONI);
}

// ---------- strumenti ----------

const schemaData = { type: "string", description: "Data AAAA-MM-GG (usa il calendario del prompt, non calcolarla)" };
const schemaTurno = { type: "integer", description: "Turno: 1 = primo, 2 = secondo" };
const schemaRiassegna = {
  type: "array",
  description: "Facoltativo: altre prenotazioni dello stesso turno da spostare in un altro posto per far entrare questa",
  items: {
    type: "object",
    properties: { prenotazione_id: { type: "string" }, unita: { type: "string" } },
    required: ["prenotazione_id", "unita"],
  },
};

export const STRUMENTI: Strumento[] = [
  {
    name: "piantina",
    description: "Elenco dei tavoli della sala con i posti e i pezzi in cui si può dividere ogni blocco. Serve per leggere i riferimenti del proprietario (\"il 21\").",
    parameters: { type: "object", properties: {} },
    async esegui(_a, { sala }) {
      return {
        turni: sala.turni.map((t, i) => ({ turno: i + 1, nome: t.nome, inizio: t.inizio, fine: t.fine })),
        tavoli: sala.tavoli.map((t) => ({
          id: t.id,
          tipo: t.tipo,
          posti: t.posti,
          ...(t.tipo === "blocco" ? { quadrati: t.moduli, separabile: !!t.separabile } : {}),
          posti_assegnabili: sala.unitaDel(t).map((u) => ({ unita: u.chiave, nome: sala.etichetta(u.chiave), posti: u.posti })),
        })),
        regole: "Lungo (11): un gruppo fino a 20 oppure due fino a 8. Blocchi separabili: pezzi contigui; un quadrato da solo ha 4 posti, un pezzo da j>=2 quadrati ne ha 2j+2.",
      };
    },
  },
  {
    name: "turno_per_orario",
    description: "In quale turno cade un orario (es. \"20:30\"). Dice se è a metà tra due turni o troppo lontano dai turni.",
    parameters: { type: "object", properties: { orario: { type: "string", description: "HH:MM, 24 ore" } }, required: ["orario"] },
    async esegui(a, { sala }) {
      if (!/^\d{1,2}:\d{2}$/.test(String(a.orario))) throw new ErroreStrumento(`orario non valido: ${String(a.orario)}`);
      return turnoPerOrario(sala, String(a.orario).padStart(5, "0"));
    },
  },
  {
    name: "stato_serata",
    description: "Prenotazioni accettate di una serata, per turno, con il posto assegnato a ciascuna.",
    parameters: { type: "object", properties: { data: schemaData }, required: ["data"] },
    async esegui(a, ctx) {
      const data = controllaDataCtx(ctx, a.data);
      const s = await ctx.store.serata(data);
      return {
        data,
        turni: ctx.sala.turni.map((t, i) => {
          const lista = attive(s, i);
          const posti = lista.map(comePosto);
          return {
            turno: i + 1,
            nome: t.nome,
            prenotazioni: lista.length,
            coperti: lista.reduce((n, p) => n + p.coperti, 0),
            posti_vuoti: punteggio(ctx.sala, posti).vuoti,
            elenco: lista.map((p) => vista(ctx.sala, p)),
          };
        }),
      };
    },
  },
  {
    name: "riepilogo",
    description: "Testo del riepilogo di una serata, già pronto per il proprietario: per turno, chi siede dove. Solo qui si dice il tavolo.",
    parameters: { type: "object", properties: { data: schemaData }, required: ["data"] },
    async esegui(a, ctx) {
      const data = controllaDataCtx(ctx, a.data);
      const s = await ctx.store.serata(data);
      const righe = [`Riepilogo ${dataBreve(data)}`];
      ctx.sala.turni.forEach((t, i) => {
        const lista = attive(s, i);
        righe.push(`${t.nome[0].toUpperCase()}${t.nome.slice(1)} turno (${t.inizio}): ${lista.length} prenotazioni, ${lista.reduce((n, p) => n + p.coperti, 0)} coperti`);
        const ord = [...lista].sort((x, y) => x.prenotata_il.localeCompare(y.prenotata_il));
        for (const p of ord) righe.push(`  ${p.nome} ${p.coperti} · ${ctx.sala.etichetta(p.unita)}${p.fissata ? " (fissata)" : ""}${p.note ? ` · ${p.note}` : ""}`);
      });
      return { testo: righe.join("\n") };
    },
  },
  {
    name: "cerca_posto",
    description:
      "Cerca dove sedere una nuova prenotazione in un turno, senza scrivere nulla. Prima senza spostare nessuno, poi spostando una prenotazione non fissata. " +
      "Se risponde dimostrato_pieno=true il turno è sicuramente pieno per quel gruppo; se non trova posto ma dimostrato_pieno=false NON dire \"pieno\": di' che non hai trovato posto.",
    parameters: {
      type: "object",
      properties: { data: schemaData, turno: schemaTurno, coperti: { type: "integer" } },
      required: ["data", "turno", "coperti"],
    },
    async esegui(a, ctx) {
      const data = controllaDataCtx(ctx, a.data);
      const t = turnoIdx(ctx.sala, a.turno);
      const coperti = copertiOk(ctx.sala, a.coperti);
      const s = await ctx.store.serata(data);
      const esistenti = attive(s, t);
      const opzioni = cercaPostoNelTurno(ctx.sala, esistenti, coperti);
      const pieno = dimostratoPieno(ctx.sala, [...esistenti.map((p) => p.coperti), coperti]);
      return {
        turno: nomeTurno(ctx.sala, t),
        esito: opzioni.length ? "trovato" : "non_trovato",
        dimostrato_pieno: pieno,
        opzioni,
        nota: opzioni.length
          ? "Scegli la prima opzione salvo richieste del proprietario; con sposta[] vanno passate a registra come riassegna."
          : pieno
            ? "Il conteggio dimostra che in questo turno non c'è posto."
            : "Nessun posto trovato con al più uno spostamento, ma non è dimostrato che sia pieno.",
      };
    },
  },
  {
    name: "verifica_piano",
    description: "Controlla (senza scrivere) un piano completo di un turno: elenco di prenotazione_id e posto. Risponde con gli errori o con il punteggio.",
    parameters: {
      type: "object",
      properties: { data: schemaData, turno: schemaTurno, assegnazioni: schemaRiassegna },
      required: ["data", "turno", "assegnazioni"],
    },
    async esegui(a, ctx) {
      const data = controllaDataCtx(ctx, a.data);
      const t = turnoIdx(ctx.sala, a.turno);
      const s = await ctx.store.serata(data);
      const cambi = riassegna(s, t, a.assegnazioni);
      const piano = pianoDelTurno(s, t, cambi);
      const errori = validaTurno(ctx.sala, piano);
      return { ammesso: errori.length === 0, errori, ...punteggio(ctx.sala, piano) };
    },
  },
  {
    name: "registra",
    description:
      "Registra una nuova prenotazione nel turno e nel posto indicati. Si usa solo dopo cerca_posto (o la richiesta esplicita del proprietario) e solo se il cliente ha " +
      "accettato il turno. Scrive soltanto se il piano del turno è ammesso. Non citare il tavolo al proprietario: nella conferma si dice solo il turno.",
    parameters: {
      type: "object",
      properties: {
        nome: { type: "string" },
        coperti: { type: "integer" },
        data: schemaData,
        turno: schemaTurno,
        unita: { type: "string", description: "Chiave del posto, da cerca_posto o piantina (es. t4, t21.q0-0, t11.g2)" },
        ora_richiesta: { type: "string", description: "Orario chiesto dal cliente, HH:MM, se c'è" },
        note: { type: "string" },
        riassegna: schemaRiassegna,
        altra_prenotazione_stesso_nome: { type: "boolean", description: "true solo se il proprietario ha detto che è un'altra prenotazione di un nome già presente" },
      },
      required: ["nome", "coperti", "data", "turno", "unita"],
    },
    async esegui(a, ctx) {
      const data = controllaDataCtx(ctx, a.data);
      const t = turnoIdx(ctx.sala, a.turno);
      const coperti = copertiOk(ctx.sala, a.coperti);
      const nome = String(a.nome ?? "").trim();
      if (!nome) throw new ErroreStrumento("manca il nome");
      const s = await ctx.store.serata(data);
      const omonimo = s.prenotazioni.find((p) => p.stato === "accettata" && p.nome.toLowerCase() === nome.toLowerCase());
      if (omonimo && !a.altra_prenotazione_stesso_nome) {
        throw new ErroreStrumento(
          `C'è già ${omonimo.nome} (${omonimo.coperti} persone, ${nomeTurno(ctx.sala, omonimo.turno)}): chiedi al proprietario se è un'altra prenotazione o una modifica`,
        );
      }
      const id = `P${s.prossimo_id}`;
      const cambi = riassegna(s, t, a.riassegna);
      esigiPianoValido(ctx.sala, pianoDelTurno(s, t, cambi, { id, nome, coperti, unita: String(a.unita) }));
      for (const p of attive(s, t)) if (cambi.has(p.id)) p.unita = cambi.get(p.id)!;
      const nuova: Prenotazione = {
        id,
        nome,
        coperti,
        data,
        turno: t,
        ora_richiesta: a.ora_richiesta ? String(a.ora_richiesta) : undefined,
        note: a.note ? String(a.note) : undefined,
        prenotata_il: ctx.adesso().toISOString(),
        unita: String(a.unita),
        stato: "accettata",
      };
      s.prenotazioni.push(nuova);
      s.prossimo_id += 1;
      await salva(ctx, s);
      return { registrata: true, id, conferma: conferma(ctx.sala, nuova) };
    },
  },
  {
    name: "annulla",
    description: "Annulla una prenotazione (solo se il proprietario l'ha chiesto). Libera il posto.",
    parameters: { type: "object", properties: { data: schemaData, prenotazione_id: { type: "string" } }, required: ["data", "prenotazione_id"] },
    async esegui(a, ctx) {
      const data = controllaDataCtx(ctx, a.data);
      const s = await ctx.store.serata(data);
      const p = trovaPrenotazione(s, a.prenotazione_id);
      p.stato = "annullata";
      await salva(ctx, s);
      return { annullata: true, testo: `✓ Annullata: ${p.nome} · ${p.coperti} · ${dataBreve(data)} · ${nomeTurno(ctx.sala, p.turno)}` };
    },
  },
  {
    name: "modifica",
    description:
      "Cambia una prenotazione: coperti, note, posto o turno. Cambiare turno tocca il cliente: serve cliente_ha_accettato=true e il nuovo posto in unita. " +
      "La data non si cambia: si annulla e si riprenota.",
    parameters: {
      type: "object",
      properties: {
        data: schemaData,
        prenotazione_id: { type: "string" },
        coperti: { type: "integer" },
        note: { type: "string" },
        unita: { type: "string", description: "Nuovo posto (stesso turno, o nuovo turno se nuovo_turno è dato)" },
        nuovo_turno: schemaTurno,
        cliente_ha_accettato: { type: "boolean" },
        riassegna: schemaRiassegna,
      },
      required: ["data", "prenotazione_id"],
    },
    async esegui(a, ctx) {
      const data = controllaDataCtx(ctx, a.data);
      const s = await ctx.store.serata(data);
      const p = trovaPrenotazione(s, a.prenotazione_id);
      const vecchio = p.turno;
      const turnoNuovo = a.nuovo_turno !== undefined ? turnoIdx(ctx.sala, a.nuovo_turno) : vecchio;
      if (turnoNuovo !== vecchio) {
        if (!a.cliente_ha_accettato) throw new ErroreStrumento("cambiare turno richiede il sì del cliente: chiedi prima al proprietario");
        if (!a.unita) throw new ErroreStrumento("per cambiare turno indica anche il nuovo posto (unita)");
      }
      const coperti = a.coperti !== undefined ? copertiOk(ctx.sala, a.coperti) : p.coperti;
      const unita = a.unita ? String(a.unita) : p.unita;
      if (p.fissata && a.unita && unita !== p.unita) {
        throw new ErroreStrumento(`${p.nome} è fissata dal proprietario: libera prima, oppure usa "fissa" per cambiare posto`);
      }
      const cambi = riassegna(s, turnoNuovo, a.riassegna, p.id);
      const altri = attive(s, turnoNuovo).filter((x) => x.id !== p.id);
      const piano = [...altri.map((x) => ({ ...comePosto(x), unita: cambi.get(x.id) ?? x.unita })), { id: p.id, nome: p.nome, coperti, unita }];
      esigiPianoValido(ctx.sala, piano);
      for (const x of altri) if (cambi.has(x.id)) x.unita = cambi.get(x.id)!;
      p.coperti = coperti;
      p.unita = unita;
      p.turno = turnoNuovo;
      if (a.note !== undefined) p.note = String(a.note) || undefined;
      await salva(ctx, s);
      return { modificata: true, conferma: conferma(ctx.sala, p) };
    },
  },
  {
    name: "fissa",
    description:
      "Per ordine del proprietario: mette una prenotazione in un posto preciso e la fissa (nessun riordino la sposta). Vale anche per dividere un blocco: " +
      "si assegna il pezzo voluto (es. t21.q0-0). Rispetta solo le regole dure; il buonsenso lo decide il proprietario.",
    parameters: {
      type: "object",
      properties: { data: schemaData, prenotazione_id: { type: "string" }, unita: { type: "string" }, riassegna: schemaRiassegna },
      required: ["data", "prenotazione_id", "unita"],
    },
    async esegui(a, ctx) {
      const data = controllaDataCtx(ctx, a.data);
      const s = await ctx.store.serata(data);
      const p = trovaPrenotazione(s, a.prenotazione_id);
      const cambi = riassegna(s, p.turno, a.riassegna, p.id);
      cambi.set(p.id, String(a.unita));
      esigiPianoValido(ctx.sala, pianoDelTurno(s, p.turno, cambi));
      for (const x of attive(s, p.turno)) if (cambi.has(x.id)) x.unita = cambi.get(x.id)!;
      p.fissata = true;
      await salva(ctx, s);
      return { fissata: true, id: p.id, dove: ctx.sala.etichetta(p.unita), testo: `✓ ${p.nome} fissata: ${ctx.sala.etichetta(p.unita)}` };
    },
  },
  {
    name: "libera",
    description: "Toglie il fissaggio a una prenotazione: da qui in poi si può riordinare.",
    parameters: { type: "object", properties: { data: schemaData, prenotazione_id: { type: "string" } }, required: ["data", "prenotazione_id"] },
    async esegui(a, ctx) {
      const data = controllaDataCtx(ctx, a.data);
      const s = await ctx.store.serata(data);
      const p = trovaPrenotazione(s, a.prenotazione_id);
      p.fissata = false;
      await salva(ctx, s);
      return { liberata: true, testo: `✓ ${p.nome}: di nuovo automatica` };
    },
  },
  {
    name: "memorizza_bozza",
    description:
      "Quando l'ordine del proprietario non è chiaro o va confermato: salva cosa hai capito, cosa manca e la domanda che gli fai. Alla risposta successiva la ritrovi nel prompt. " +
      "Fai UNA domanda sola, in fondo al messaggio, e non scrivere nulla finché non ha risposto.",
    parameters: {
      type: "object",
      properties: {
        azione: { type: "string", description: "Cosa stai per fare, in una riga" },
        dettagli: { type: "object", description: "Quello che hai già capito (nome, coperti, data, turno, posti...)" },
        mancano: { type: "array", items: { type: "string" } },
        domanda: { type: "string" },
        opzioni: { type: "array", items: { type: "string" }, description: "Facoltativo: risposte brevi (max 6, ognuna sotto i 30 caratteri) mostrate come pulsanti" },
      },
      required: ["azione", "domanda"],
    },
    async esegui(a, ctx) {
      const c = await ctx.store.conversazione(ctx.mittente);
      const bozza: Bozza = {
        azione: String(a.azione),
        dettagli: (a.dettagli as Record<string, unknown>) ?? {},
        mancano: (a.mancano as string[]) ?? [],
        domanda: String(a.domanda),
        opzioni: Array.isArray(a.opzioni) ? (a.opzioni as unknown[]).map(String).filter((o) => o && o.length <= 30).slice(0, 6) : undefined,
        creata_il: ctx.adesso().toISOString(),
      };
      c.bozza = bozza;
      await ctx.store.salvaConversazione(ctx.mittente, c);
      return { salvata: true };
    },
  },
  {
    name: "link_piantina",
    description: "Indirizzo della piantina della sala (si apre nel browser): i tavoli hanno i numeri. Da dare al proprietario quando deve indicare un tavolo.",
    parameters: { type: "object", properties: {} },
    async esegui() {
      return { url: URL_PIANTINA };
    },
  },
  {
    name: "cancella_bozza",
    description: "Elimina la bozza in sospeso (il proprietario ha detto di lasciar stare, o l'azione è finita).",
    parameters: { type: "object", properties: {} },
    async esegui(_a, ctx) {
      const c = await ctx.store.conversazione(ctx.mittente);
      delete c.bozza;
      await ctx.store.salvaConversazione(ctx.mittente, c);
      return { cancellata: true };
    },
  },
];

export const NOMI_STRUMENTI = STRUMENTI.map((s) => s.name);
