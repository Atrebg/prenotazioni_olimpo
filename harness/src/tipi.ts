export interface Prenotazione {
  id: string;
  nome: string;
  coperti: number;
  data: string; // AAAA-MM-GG
  turno: number; // 0-based: il turno promesso, congelato
  ora_richiesta?: string;
  note?: string;
  prenotata_il: string; // ISO
  unita: string; // chiave dell'unità (tavolo, gruppo del lungo, pezzo di blocco): può cambiare, non è promessa
  fissata?: boolean; // voluta dal proprietario: nessun riordino la sposta
  stato: "accettata" | "annullata";
}

export interface Serata {
  data: string;
  versione: number;
  prenotazioni: Prenotazione[];
  prossimo_id: number;
}

export interface Bozza {
  azione: string; // cosa l'agente sta per fare, in una riga
  dettagli: Record<string, unknown>; // quello che ha già capito
  mancano: string[]; // quello che manca
  domanda: string; // l'ultima domanda posta
  creata_il: string; // ISO
}

export interface Conversazione {
  storia: { role: "user" | "assistant"; content: string }[];
  bozza?: Bozza;
}
