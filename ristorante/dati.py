"""Caricamento e validazione di sala e prenotazioni, conversione su griglia (spazio e tempo).

Convenzioni:
- spazio in cm, origine in alto a sinistra, x verso destra, y verso il basso;
- il solver lavora su una griglia di `griglia_cm` (10 cm): le dimensioni degli ingombri
  sono arrotondate per ECCESSO, ostacoli e corsie sono allargati verso l'esterno
  (arrotondamento conservativo: una soluzione valida sulla griglia è valida anche in cm);
- tempo in minuti dalla mezzanotte ("24:00" = 1440); il solver lavora in passi di
  `passo_orari_min` (15 min) contati dall'apertura del servizio.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ORIZZONTALE = "orizzontale"
VERTICALE = "verticale"

MOTIVO_TROPPO_GRANDE = "nessun tavolo componibile abbastanza grande"
MOTIVO_SALA_PIENA = "sala piena nella fascia richiesta"
MOTIVO_FUORI_ORARIO = "nessun orario ammesso entro la chiusura del servizio"
MOTIVO_NESSUNA_SOLUZIONE = "nessuna soluzione trovata entro il tempo limite"
# accettazione in ordine di arrivo
MOTIVO_SALA_PIENA_ACCETTATE = "sala piena nella fascia richiesta, con le prenotazioni già accettate"
MOTIVO_TEMPO_SCADUTO = "spazio non trovato entro il tempo limite"
MOTIVO_PROPOSTA_RIFIUTATA = "proposta non accettata dal cliente"
MAI, SEMPRE = "mai", "sempre"


def motivo_nessun_orario(max_min: int) -> str:
    return f"nessun orario libero entro {max_min} min"

FISSA, VARIABILE = "fissa", "variabile"
TUTTE_INSIEME, ORDINE_DI_ARRIVO = "tutte_insieme", "ordine_di_arrivo"


class ErroreDati(ValueError):
    """Dati di ingresso non validi."""


@dataclass(frozen=True)
class Rettangolo:
    nome: str
    x0: int
    y0: int
    x1: int
    y1: int


@dataclass(frozen=True)
class Forma:
    """Una forma di tavolo ammessa (blocco di k moduli in un orientamento, oppure tondo)."""
    tipo: str               # "moduli" | "tondo"
    moduli: int             # k (0 per il tondo)
    orientamento: str       # ORIZZONTALE / VERTICALE ("" per il tondo)
    larghezza_cm: int       # dimensioni del piano del tavolo
    altezza_cm: int
    capienza: int
    ingombro_l: int         # dimensioni dell'ingombro (tavolo + margine sedie) in celle di griglia
    ingombro_h: int

    @property
    def nome(self) -> str:
        if self.tipo == "tondo":
            return "tondo"
        return f"{self.moduli}{'O' if self.orientamento == ORIZZONTALE else 'V'}"


@dataclass(frozen=True)
class Prenotazione:
    id: str
    nome: str
    coperti: int
    orario_min: int         # minuti dalla mezzanotte
    note: str = ""
    prenotata_il: str = ""  # data e ora di ricezione (ISO, "2026-10-27T18:42"); "" se assente
    indice: int = 0         # posizione nel file (spareggio a parità di prenotata_il)


@dataclass
class Istanza:
    sala: dict
    serata: dict
    prenotazioni: list[Prenotazione]
    # derivati
    griglia: int = 0
    larghezza_g: int = 0
    altezza_g: int = 0
    margine: int = 0
    fissi_g: list[Rettangolo] = field(default_factory=list)   # ostacoli + corsie su griglia
    fissi_disgiunti_g: list[Rettangolo] = field(default_factory=list)  # la loro unione, in pezzi disgiunti
    forme_moduli: list[Forma] = field(default_factory=list)   # solo forme che entrano nella sala vuota
    forma_tondo: Forma | None = None                          # None se non entra o quantita 0
    posizioni: dict = field(default_factory=dict)             # nome forma -> (x ammessi, y ammessi)
    n_moduli: int = 0
    n_tondi: int = 0
    inizio_min: int = 0
    fine_min: int = 0
    passo: int = 15
    riapp_passi: int = 1
    spostamenti_min: list[int] = field(default_factory=list)
    accettazione: str = TUTTE_INSIEME
    disposizione: str = FISSA
    slot_variabile_moduli: int = 0
    slot_variabile_tondi: int = 0
    cliente_accetta_proposta: str = MAI     # "mai" | "sempre" | "entro_N_min"
    proposta_max_distanza_min: int = 120
    proposta_a_parita: str = "prima"        # a parità di distanza: "prima" | "dopo"

    # ---- tempo -------------------------------------------------------------------
    def durata_min(self, coperti: int) -> int:
        return durata_per_coperti(self.sala["durate"], coperti)

    def a_passi(self, minuti_assoluti: int) -> int:
        return (minuti_assoluti - self.inizio_min) // self.passo

    @property
    def fine_passi(self) -> int:
        return (self.fine_min - self.inizio_min) // self.passo

    @property
    def orizzonte_passi(self) -> int:
        """Fine del servizio più la riapparecchiatura finale: l'esistenza di un tavolo che resta fino
        alla chiusura termina qui (l'ultimo pasto può finire alle 24:00, la sua riapparecchiatura dopo)."""
        return self.fine_passi + self.riapp_passi

    def opzioni(self, pr: Prenotazione) -> list[tuple[int, int]]:
        """Spostamenti ammessi per la prenotazione: (spostamento_min, inizio in passi), pasto dentro il servizio."""
        d = self.durata_min(pr.coperti) // self.passo
        t = self.a_passi(pr.orario_min)
        out = []
        for sm in self.spostamenti_min:
            st = t + sm // self.passo
            if st >= 0 and st + d <= self.fine_passi:
                out.append((sm, st))
        return out

    def candidati_proposta(self, pr: Prenotazione) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
        """Orari alternativi fuori dagli spostamenti ammessi, sulla griglia, con il pasto dentro il servizio e
        a non più di `proposta_max_distanza_min` dall'orario richiesto: (prima, dopo), ciascuna lista ordinata
        dal più vicino. Elementi (spostamento_min, inizio in passi)."""
        d = self.durata_min(pr.coperti) // self.passo
        t = self.a_passi(pr.orario_min)
        ammessi = set(self.spostamenti_min)
        prima, dopo = [], []
        for k in range(1, self.proposta_max_distanza_min // self.passo + 1):
            for segno, lista in ((-1, prima), (1, dopo)):
                sm = segno * k * self.passo
                st = t + segno * k
                if sm not in ammessi and st >= 0 and st + d <= self.fine_passi:
                    lista.append((sm, st))
        return prima, dopo

    def accetta_proposta(self, distanza_min: int) -> bool:
        """Politica di simulazione del cliente davanti a una proposta a `distanza_min` dall'orario chiesto."""
        pol = self.cliente_accetta_proposta
        if pol == SEMPRE:
            return True
        if pol == MAI:
            return False
        return abs(distanza_min) <= entro_minuti(pol)

    def in_ordine_di_arrivo(self) -> list[Prenotazione]:
        return sorted(self.prenotazioni, key=lambda p: (p.prenotata_il, p.indice))

    # ---- capienze ------------------------------------------------------------------
    @property
    def capienza_massima(self) -> int:
        caps = [f.capienza for f in self.forme_moduli]
        if self.forma_tondo is not None:
            caps.append(self.forma_tondo.capienza)
        return max(caps, default=0)


def entro_minuti(politica: str) -> int:
    """'entro_60_min' -> 60."""
    parti = politica.split("_")
    if len(parti) == 3 and parti[0] == "entro" and parti[2] == "min" and parti[1].isdigit():
        return int(parti[1])
    raise ErroreDati(f"cliente_accetta_proposta {politica!r}: atteso 'mai', 'sempre' o 'entro_N_min'")


def hhmm_a_min(s: str) -> int:
    try:
        h, m = s.strip().split(":")
        h, m = int(h), int(m)
    except Exception as exc:  # noqa: BLE001
        raise ErroreDati(f"orario non valido: {s!r} (atteso HH:MM)") from exc
    if not (0 <= h <= 24 and 0 <= m < 60) or (h == 24 and m != 0):
        raise ErroreDati(f"orario fuori scala: {s!r}")
    return h * 60 + m


def min_a_hhmm(minuti: int) -> str:
    return f"{minuti // 60:02d}:{minuti % 60:02d}"


def durata_per_coperti(durate: list[dict], coperti: int) -> int:
    for riga in durate:
        soglia = riga.get("fino_a_coperti")
        if soglia is None or coperti <= soglia:
            return int(riga["minuti"])
    raise ErroreDati(f"nessuna durata definita per {coperti} coperti")


def _rett(d: dict) -> Rettangolo:
    r = Rettangolo(str(d.get("nome", "")), int(d["x0"]), int(d["y0"]), int(d["x1"]), int(d["y1"]))
    if r.x1 <= r.x0 or r.y1 <= r.y0:
        raise ErroreDati(f"rettangolo degenere: {d}")
    return r


def _celle(cm: int, g: int) -> int:
    return math.ceil(cm / g)


def _occupazione(W: int, H: int, fissi: list[Rettangolo]) -> list[list[int]]:
    occ = [[0] * W for _ in range(H)]
    for r in fissi:
        for yy in range(max(0, r.y0), min(H, r.y1)):
            riga = occ[yy]
            for xx in range(max(0, r.x0), min(W, r.x1)):
                riga[xx] = 1
    return occ


def decomponi_in_disgiunti(W: int, H: int, fissi: list[Rettangolo]) -> list[Rettangolo]:
    """Unione di ostacoli e corsie scomposta in rettangoli DISGIUNTI che la coprono esattamente.

    Serve perché NoOverlap2D vieta la sovrapposizione anche tra i rettangoli fissi: se due
    ostacoli si sovrappongono (es. il pilastro dentro la corsia centrale) il modello sarebbe
    infattibile. Metodo: tratti massimi di celle occupate per riga, fusi in verticale quando
    identici nella riga successiva."""
    occ = _occupazione(W, H, fissi)
    aperti: dict[tuple[int, int], int] = {}   # (x0, x1) -> y0
    risultato: list[Rettangolo] = []
    for yy in range(H + 1):
        tratti: set[tuple[int, int]] = set()
        if yy < H:
            xx = 0
            while xx < W:
                if occ[yy][xx]:
                    x0 = xx
                    while xx < W and occ[yy][xx]:
                        xx += 1
                    tratti.add((x0, xx))
                else:
                    xx += 1
        for chiave in list(aperti):
            if chiave not in tratti:
                y0 = aperti.pop(chiave)
                risultato.append(Rettangolo(f"fisso{len(risultato)}", chiave[0], y0, chiave[1], yy))
        for t in tratti:
            aperti.setdefault(t, yy)
    return risultato


def posizioni_libere(lg: int, hg: int, W: int, H: int, fissi: list[Rettangolo]) -> tuple[list[int], list[int]]:
    """Angoli (x, y) sulla griglia in cui un ingombro lg x hg sta nella sala senza toccare
    ostacoli/corsie, proiettati sui due assi: (x ammessi, y ammessi). Liste vuote = non entra.
    Somme prefisse 2D sull'occupazione delle celle."""
    if lg > W or hg > H:
        return [], []
    occ = _occupazione(W, H, fissi)
    pref = [[0] * (W + 1) for _ in range(H + 1)]
    for yy in range(H):
        acc = 0
        for xx in range(W):
            acc += occ[yy][xx]
            pref[yy + 1][xx + 1] = pref[yy][xx + 1] + acc
    xs, ys = set(), set()
    for y0 in range(H - hg + 1):
        for x0 in range(W - lg + 1):
            s = pref[y0 + hg][x0 + lg] - pref[y0][x0 + lg] - pref[y0 + hg][x0] + pref[y0][x0]
            if s == 0:
                xs.add(x0)
                ys.add(y0)
    return sorted(xs), sorted(ys)


def costruisci_istanza(sala: dict, serata: dict) -> Istanza:
    g = int(sala.get("griglia_cm", 10))
    if g <= 0:
        raise ErroreDati("griglia_cm deve essere positiva")
    W = int(sala["larghezza_cm"]) // g
    H = int(sala["altezza_cm"]) // g
    margine = int(sala["margine_sedie_cm"])

    fissi_cm = [_rett(o) for o in sala.get("ostacoli", [])] + [_rett(c) for c in sala.get("corsie", [])]
    fissi_g = [
        Rettangolo(r.nome, r.x0 // g, r.y0 // g, _celle(r.x1, g), _celle(r.y1, g))
        for r in fissi_cm
    ]
    fissi_disgiunti = decomponi_in_disgiunti(W, H, fissi_g)

    inv = sala["inventario"]
    mod = inv["moduli"]
    n_moduli = int(mod["quantita"])
    lato = int(mod["lato_cm"])
    kmax = min(int(mod["max_per_blocco"]), n_moduli)
    ppm = int(mod.get("posti_per_modulo", 2))
    ptest = int(mod.get("posti_testate", 2))

    forme: list[Forma] = []
    posizioni: dict[str, tuple[list[int], list[int]]] = {}
    for k in range(1, kmax + 1):
        orient = [ORIZZONTALE] if k == 1 else [ORIZZONTALE, VERTICALE]  # k=1 è un quadrato: un solo orientamento
        for o in orient:
            lw, lh = (lato * k, lato) if o == ORIZZONTALE else (lato, lato * k)
            f = Forma("moduli", k, o, lw, lh, ppm * k + ptest,
                      _celle(lw + 2 * margine, g), _celle(lh + 2 * margine, g))
            xs, ys = posizioni_libere(f.ingombro_l, f.ingombro_h, W, H, fissi_g)
            if xs:
                forme.append(f)
                posizioni[f.nome] = (xs, ys)

    tondo = inv.get("tondi", {"quantita": 0})
    n_tondi = int(tondo.get("quantita", 0))
    forma_tondo = None
    if n_tondi > 0:
        d = int(tondo["diametro_cm"])
        ft = Forma("tondo", 0, "", d, d, int(tondo["capienza"]),
                   _celle(d + 2 * margine, g), _celle(d + 2 * margine, g))
        xs, ys = posizioni_libere(ft.ingombro_l, ft.ingombro_h, W, H, fissi_g)
        if xs:
            forma_tondo = ft
            posizioni[ft.nome] = (xs, ys)

    passo = int(sala.get("passo_orari_min", 15))
    inizio = hhmm_a_min(sala["servizio"]["inizio"])
    fine = hhmm_a_min(sala["servizio"]["fine"])
    if fine <= inizio:
        raise ErroreDati("il servizio deve finire dopo l'inizio")
    if (fine - inizio) % passo:
        raise ErroreDati("la durata del servizio deve essere multipla del passo orari")
    for riga in sala["durate"]:
        if int(riga["minuti"]) % passo:
            raise ErroreDati(f"durata {riga['minuti']} non multipla del passo orari {passo}")
    riapp = int(sala.get("riapparecchiatura_min", 0))
    if riapp % passo:
        raise ErroreDati("la riapparecchiatura deve essere multipla del passo orari")
    spost = [int(s) for s in sala.get("spostamenti_ammessi_min", [0])]
    for s in spost:
        if s % passo:
            raise ErroreDati(f"spostamento {s} non multiplo del passo orari {passo}")

    accettazione = str(sala.get("accettazione", TUTTE_INSIEME))
    disposizione = str(sala.get("disposizione", FISSA))
    if accettazione not in (TUTTE_INSIEME, ORDINE_DI_ARRIVO):
        raise ErroreDati(f"accettazione {accettazione!r}: atteso {TUTTE_INSIEME!r} o {ORDINE_DI_ARRIVO!r}")
    if disposizione not in (FISSA, VARIABILE):
        raise ErroreDati(f"disposizione {disposizione!r}: atteso {FISSA!r} o {VARIABILE!r}")
    politica = str(sala.get("cliente_accetta_proposta", MAI))
    if politica not in (MAI, SEMPRE):
        entro_minuti(politica)          # valida "entro_N_min"
    prop_max = int(sala.get("proposta_max_distanza_min", 120))
    a_parita = str(sala.get("proposta_a_parita", "prima"))
    if a_parita not in ("prima", "dopo"):
        raise ErroreDati("proposta_a_parita: atteso 'prima' o 'dopo'")
    sv = sala.get("slot_variabile", {})
    slot_var_mod = int(sv.get("moduli", 2 * n_moduli))
    slot_var_tondi = int(sv.get("tondi", 2 * n_tondi))

    pren: list[Prenotazione] = []
    visti: set[str] = set()
    for indice, p in enumerate(serata["prenotazioni"]):
        pid = str(p["id"])
        if pid in visti:
            raise ErroreDati(f"id prenotazione duplicato: {pid}")
        visti.add(pid)
        cop = int(p["coperti"])
        if cop <= 0:
            raise ErroreDati(f"{pid}: coperti deve essere positivo")
        orario = hhmm_a_min(p["orario"])
        if (orario - inizio) % passo:
            raise ErroreDati(f"{pid}: orario {p['orario']} non sulla griglia di {passo} min")
        ricevuta = str(p.get("prenotata_il", "") or "")
        if ricevuta:
            try:
                ricevuta = datetime.fromisoformat(ricevuta).isoformat(timespec="minutes")
            except ValueError as exc:
                raise ErroreDati(f"{pid}: prenotata_il {ricevuta!r} non è una data ISO (AAAA-MM-GGTHH:MM)") from exc
        pren.append(Prenotazione(pid, str(p["nome"]), cop, orario, str(p.get("note", "") or ""), ricevuta, indice))

    return Istanza(
        sala=sala, serata=serata, prenotazioni=pren, griglia=g, larghezza_g=W, altezza_g=H,
        margine=margine, fissi_g=fissi_g, fissi_disgiunti_g=fissi_disgiunti, forme_moduli=forme,
        posizioni=posizioni, forma_tondo=forma_tondo,
        n_moduli=n_moduli, n_tondi=n_tondi, inizio_min=inizio, fine_min=fine, passo=passo,
        riapp_passi=riapp // passo, spostamenti_min=sorted(set(spost)),
        accettazione=accettazione, disposizione=disposizione,
        slot_variabile_moduli=slot_var_mod, slot_variabile_tondi=slot_var_tondi,
        cliente_accetta_proposta=politica, proposta_max_distanza_min=prop_max, proposta_a_parita=a_parita,
    )


def leggi_json(percorso: str | Path) -> dict:
    with open(percorso, encoding="utf-8") as fh:
        return json.load(fh)


def carica(percorso_sala: str | Path, percorso_prenotazioni: str | Path) -> Istanza:
    return costruisci_istanza(leggi_json(percorso_sala), leggi_json(percorso_prenotazioni))
