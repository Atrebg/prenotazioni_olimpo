"""Sala vera dell'Olimpo, letta dalla piantina disegnata (`olimpo/piantina.html`).

La fonte unica è il blocco `<script type="application/json" id="sala">` della piantina, che il proprietario aggiorna:
qui lo si legge così com'è, senza copie. I tavoli non si spostano: il motore decide solo, per ogni turno, chi siede
dove. Le "unità" assegnabili in un turno sono:
- un tavolo semplice (panca, rettangolare, tondo, quadrato): una prenotazione, coperti <= posti;
- il tavolo lungo: un gruppo fino ai suoi posti (20) oppure due gruppi fino a `LUNGO_DUE_GRUPPI` (8) ciascuno;
- un blocco separabile di k quadrati: in ogni turno una partizione in pezzi CONTIGUI; il pezzo intero ha i posti del
  blocco, un pezzo da j >= 2 quadrati 2j + 2 posti, un quadrato da solo `posti_quadrato_separato`.
Le impostazioni del motore (servizio, pesi, tempi, chat) non stanno nella piantina: sono in `IMPOSTAZIONI` qui sotto.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

LUNGO_DUE_GRUPPI = 8               # "un gruppo fino a 20 oppure due gruppi fino a 8"
CHIUSURA = "24:00"                 # fine dell'ultimo turno: la piantina non la dice
NOMI_TURNI = ["primo", "secondo", "terzo", "quarto"]
TIPI_SEMPLICI = ("panca", "rettangolare", "tondo", "quadrato")

# impostazioni del motore per la sala vera (la piantina contiene solo la sala)
IMPOSTAZIONI = {
    "servizio": {"inizio": "19:00", "fine": CHIUSURA},
    "passo_orari_min": 15,
    "durate": [{"fino_a_coperti": None, "minuti": 90}],          # a turni non contano
    "riapparecchiatura_min": 0,
    "spostamenti_ammessi_min": [0],
    "accettazione": "ordine_di_arrivo",
    "disposizione": "fissa",
    "cliente_accetta_proposta": "sempre",
    "proposta_max_distanza_min": 120,
    "proposta_a_parita": "prima",
    "turno_a_parita": "prima",
    "turni_vicino_min": 45,
    "pesi": {"non_sistemata": 10000, "posto_vuoto": 10, "divisione_blocco": 4, "riallestimento": 2,
             "spostamento_per_quarto": 0, "accostamento_per_modulo": 0, "picco_cucina_per_coperto": 0},
    "solver": {"tempo_limite_s": 30, "tempo_decisione_s": 60, "tempo_spareggio_s": 10, "tempo_piantina_s": 60,
               "tempo_proposta_s": 30, "tempo_riepilogo_s": 1.5, "worker": 8, "seed": 42},
    # tabella delle disponibilità: con 1-2 worker CP-SAT non dimostra "turno pieno" (UNKNOWN dopo 30 s), con 4 sì in
    # meno di un secondo (misurato il 26/10/2026): qui 3 processi da 4 worker invece dei 6 da 2 della sala di esempio
    "chat": {"proposta_max_min": 60, "scadenza_proposta_min": 15, "giorni_max": 90, "servizio_serale": True,
             "tempo_verifica_s": 30, "disposizione": "fissa", "processi": 3, "worker_per_processo": 4,
             "tempo_cella_s": 20, "attesa_max_s": 5},
}


class ErrorePiantina(ValueError):
    """La piantina non ha il blocco dei dati o i dati non sono validi."""


class _CercaBlocco(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dentro, self.testo, self.trovati = False, [], 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("id") == "sala":
            self.dentro = True
            self.trovati += 1

    def handle_endtag(self, tag):
        if tag == "script":
            self.dentro = False

    def handle_data(self, data):
        if self.dentro:
            self.testo.append(data)


def leggi_blocco_sala(percorso: str | Path) -> dict:
    """Il JSON del blocco `<script type="application/json" id="sala">` della piantina."""
    p = _CercaBlocco()
    p.feed(Path(percorso).read_text(encoding="utf-8"))
    if p.trovati != 1:
        raise ErrorePiantina(f"{percorso}: atteso un blocco <script id=\"sala\">, trovati {p.trovati}")
    try:
        return json.loads("".join(p.testo))
    except json.JSONDecodeError as e:
        raise ErrorePiantina(f"{percorso}: il blocco dei dati non è JSON valido ({e})") from e


def sala_da_piantina(percorso: str | Path) -> dict:
    """Configurazione del motore per la sala vera: i dati della piantina più le impostazioni del motore.
    Turni: ogni turno dura fino all'inizio del successivo, l'ultimo fino alla chiusura."""
    dati = leggi_blocco_sala(percorso)
    inizi = [str(t) for t in dati.get("turni") or []]
    if not inizi:
        raise ErrorePiantina(f"{percorso}: mancano i turni")
    turni = [{"nome": NOMI_TURNI[i], "inizio": s, "fine": inizi[i + 1] if i + 1 < len(inizi) else CHIUSURA}
             for i, s in enumerate(inizi)]
    Piantina(dati)            # valida i tavoli
    return copy.deepcopy(IMPOSTAZIONI) | {"nome": dati.get("nome", "piantina"), "turni": turni, "piantina": dati,
                                          "fonte": str(percorso)}


def carica_sala(percorso: str | Path) -> dict:
    """`--sala`: un .html è una piantina (sala vera), altrimenti il JSON della sala di esempio."""
    if str(percorso).lower().endswith((".html", ".htm")):
        return sala_da_piantina(percorso)
    with open(percorso, encoding="utf-8") as fh:
        return json.load(fh)


@dataclass(frozen=True)
class Unita:
    """Un posto assegnabile in un turno a una sola prenotazione."""
    chiave: str                    # "t4", "t11.g2", "t5.q0-1": nomi stabili (senza turno) per variabili e hint
    tavolo: str
    tipo: str
    posti: int
    quadrati: tuple[int, int] | None = None   # blocco: primo e ultimo quadrato del pezzo (contiguo)
    gruppo: int | None = None                 # lungo: 1 (fino a 20) o 2 (secondo gruppo, fino a 8)
    intero: bool = False                      # blocco: il pezzo è il blocco intero


class Piantina:
    def __init__(self, dati: dict):
        self.dati = dati
        self.posti_separato = int(dati.get("posti_quadrato_separato", 4))
        self.tavoli: list[dict] = list(dati.get("tavoli") or [])
        visti = set()
        for t in self.tavoli:
            tid = str(t.get("id", ""))
            if not tid or tid in visti:
                raise ErrorePiantina(f"tavolo senza id o con id duplicato: {tid!r}")
            visti.add(tid)
            if not isinstance(t.get("posti"), int) or t["posti"] <= 0:
                raise ErrorePiantina(f"tavolo {tid}: posti non indicati")
            if t.get("tipo") == "blocco" and int(t.get("moduli", 0)) < 1:
                raise ErrorePiantina(f"tavolo {tid}: blocco senza numero di quadrati")
            if t.get("tipo") not in TIPI_SEMPLICI + ("blocco", "lungo"):
                raise ErrorePiantina(f"tavolo {tid}: tipo {t.get('tipo')!r} sconosciuto")
        self.per_id = {str(t["id"]): t for t in self.tavoli}

    def posti_pezzo(self, t: dict, a: int, b: int) -> int:
        k = int(t["moduli"])
        if (a, b) == (0, k - 1):
            return int(t["posti"])
        j = b - a + 1
        return 2 * j + 2 if j >= 2 else self.posti_separato

    def unita_del(self, t: dict) -> list[Unita]:
        tid = str(t["id"])
        if t["tipo"] == "lungo":
            return [Unita(f"t{tid}.g1", tid, "lungo", int(t["posti"]), gruppo=1),
                    Unita(f"t{tid}.g2", tid, "lungo", min(LUNGO_DUE_GRUPPI, int(t["posti"])), gruppo=2)]
        if t["tipo"] == "blocco":
            k = int(t["moduli"])
            if not t.get("separabile"):
                return [Unita(f"t{tid}.q0-{k - 1}", tid, "blocco", int(t["posti"]), (0, k - 1), intero=True)]
            return [Unita(f"t{tid}.q{a}-{b}", tid, "blocco", self.posti_pezzo(t, a, b), (a, b), intero=(a, b) == (0, k - 1))
                    for a in range(k) for b in range(a, k)]
        return [Unita(f"t{tid}", tid, t["tipo"], int(t["posti"]))]

    def unita(self) -> list[Unita]:
        return [u for t in self.tavoli for u in self.unita_del(t)]

    @property
    def capienza_massima(self) -> int:
        return max((u.posti for u in self.unita()), default=0)

    def capacita(self) -> list[int]:
        return sorted({u.posti for u in self.unita()})

    def max_unita(self, c: int) -> int:
        """Quante prenotazioni da almeno c coperti possono sedersi insieme in un turno, al massimo (tavoli semplici,
        due gruppi del lungo, pezzi di una partizione contigua dei blocchi)."""
        n = 0
        for t in self.tavoli:
            if t["tipo"] == "lungo":
                n += 2 if c <= LUNGO_DUE_GRUPPI else int(c <= t["posti"])
            elif t["tipo"] == "blocco" and t.get("separabile"):
                k = int(t["moduli"])
                best = [0] * (k + 1)        # best[i] = pezzi utili nei primi i quadrati
                for i in range(1, k + 1):
                    best[i] = max(best[a] + int(self.posti_pezzo(t, a, i - 1) >= c) for a in range(i))
                n += best[k]
            else:
                n += int(t["posti"] >= c)
        return n

    def posti_per_turno(self) -> int:
        return sum(int(t["posti"]) for t in self.tavoli)
