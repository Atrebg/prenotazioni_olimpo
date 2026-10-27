"""Tabella delle disponibilità e verifica parallela per la chat.

Per ogni serata con stato, per ogni classe di coperti (stessa durata e stesse forme di tavolo ammesse) e per ogni
orario d'inizio, una cella risponde alla domanda "una prenotazione in più di questa classe a questo orario entra
insieme a tutte le accettate?": "entra" / "non entra" (dimostrato) / "da verificare".

- Il calcolo gira in background su processi separati (CP-SAT con pochi worker ciascuno) e riparte da capo a ogni
  modifica dello stato: la tabella è legata alla `versione` dello stato e una tabella vecchia non si usa mai (i
  processi interrompono da soli i calcoli di una versione superata: la versione corrente sta in memoria condivisa).
  Il file `AAAA-MM-GG.versione` la riporta per chi legge lo stato da fuori (e per il calcolo nel thread dei test).
- Le celle ovvie si chiudono subito col conteggio dei moduli e col limite geometrico della sala (quanti tavoli
  entrano insieme); la dominanza tra classi nei due versi (se a un orario non entra una prenotazione più piccola e
  più corta, non entra neanche una più grande; se entra la più grande, entrano le più piccole) chiude le altre;
  gli hint vengono dall'ultimo piano registrato.
- A turni (`turni` nella sala) le celle sono classe di coperti × turno: la durata non conta, le classi dipendono
  solo dalle forme di tavolo ammesse, conteggio e geometria si fanno per turno (in "fissa" sui tavoli comuni).
- Se la tabella non è pronta, l'orario chiesto e i candidati si verificano in parallelo con priorità sul
  background; ci si ferma appena la risposta è decisa, e dopo `attesa_max_s` si risponde con ciò che è dimostrato.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import multiprocessing as mp
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .dati import costruisci_istanza, hhmm_a_min, min_a_hhmm
from .modello import _costruisci, _impossibile_per_conteggio, _risolvi_modello, _Voce

ENTRA, NON_ENTRA, DA_VERIFICARE = "entra", "non entra", "da verificare"


# --------------------------------------------------------------------------- classi di coperti

@dataclass(frozen=True)
class Classe:
    nome: str
    minimo: int
    massimo: int
    durata_min: int
    forme: frozenset


def classi_coperti(ist) -> list[Classe]:
    """Raggruppa i coperti 1..capienza massima per (durata, forme di tavolo con capienza sufficiente): dentro una
    classe l'ammissibilità di una prenotazione in più è identica nel modello. Le classi sono intervalli contigui.
    A turni la durata non conta."""
    forme = list(ist.forme_moduli) + ([ist.forma_tondo] if ist.forma_tondo is not None else [])
    chiavi = []
    for c in range(1, ist.capienza_massima + 1):
        if ist.piantina is not None:     # sala vera: contano solo le capacità reali dei tavoli e dei pezzi
            chiavi.append((c, 0, frozenset(x for x in ist.piantina.capacita() if x >= c)))
            continue
        chiavi.append((c, 0 if ist.turni else ist.durata_min(c), frozenset(f.nome for f in forme if f.capienza >= c)))
    classi = []
    for (durata, fs), gruppo in itertools.groupby(chiavi, key=lambda k: (k[1], k[2])):
        g = list(gruppo)
        classi.append(Classe(f"{g[0][0]}-{g[-1][0]}" if len(g) > 1 else str(g[0][0]), g[0][0], g[-1][0], durata, fs))
    nomi = [k for k, _ in itertools.groupby(chiavi, key=lambda k: (k[1], k[2]))]
    if len(nomi) != len(set(nomi)):
        raise RuntimeError("classi di coperti non contigue: la tabella non è applicabile a questa sala")
    return classi


def classe_di(classi: list[Classe], coperti: int) -> Classe | None:
    return next((k for k in classi if k.minimo <= coperti <= k.massimo), None)


def dominanza_valida(classi: list[Classe]) -> bool:
    """La dominanza tra classi consecutive vale se la più grande dura almeno quanto e ammette un sottoinsieme di forme."""
    return all(b.durata_min >= a.durata_min and b.forme <= a.forme for a, b in zip(classi, classi[1:]))


# --------------------------------------------------------------------------- geometria della sala

def soglie_capienza(classi: list[Classe]) -> list[int]:
    """Coperti minimi da cui servono forme di tavolo più grandi (es. 5, 7, 9, 11)."""
    return [k.minimo for a, k in zip(classi, classi[1:]) if k.forme != a.forme]


def calcola_max_tavoli(sala: dict, richiesta: tuple, soglie: list[int], tempo_s: float, worker: int) -> int:
    """Quanti tavoli entrano al massimo NELLO STESSO MOMENTO nella sala, se almeno richiesta[i] di loro devono avere
    capienza >= soglie[i]? Limite superiore DIMOSTRATO (dal bound di CP-SAT); 0 se i tavoli grandi non entrano.
    Si risolve come: prenotazioni grandi obbligatorie + tante coppie facoltative, tutte alla stessa ora."""
    pren, grandi = [], []
    sala = {k: v for k, v in sala.items() if k != "turni"}     # pura geometria: tutti i tavoli nello stesso momento
    conteggi = list(richiesta) + [0]
    for i, c in enumerate(soglie):
        for _ in range(conteggi[i] - conteggi[i + 1]):
            grandi.append(c)
    inv = sala["inventario"]
    n_max = int(inv["moduli"]["quantita"]) + int(inv.get("tondi", {}).get("quantita", 0))
    for i, c in enumerate(grandi):
        pren.append({"id": f"G{i}", "nome": f"G{i}", "coperti": c, "orario": sala["servizio"]["inizio"]})
    for i in range(max(0, n_max - len(grandi))):
        pren.append({"id": f"P{i}", "nome": f"P{i}", "coperti": 2, "orario": sala["servizio"]["inizio"]})
    ist = costruisci_istanza(sala, {"serata": "geometria", "prenotazioni": pren})
    voci = [_Voce(p_, [(0, 0)], p_.id.startswith("G")) for p_ in ist.prenotazioni]
    try:
        mod = _costruisci(ist, voci, "fissa", obiettivo="nessuno")
    except Exception:       # una grande non ha nessun tavolo possibile
        return 0
    piccole = [av for (pid, _), av in mod.a.items() if pid.startswith("P")]
    mod.m.maximize(sum(piccole))
    stato, piano, info = _risolvi_modello(mod, tempo_s, worker, 42, False)
    if stato == "INFEASIBLE":
        return 0
    if info.get("bound") is None:
        return n_max
    return len(grandi) + int(info["bound"])


_CACHE_GEOMETRIA: dict[str, dict] = {}     # per processo: la stessa sala non si ricalcola


class Geometria:
    """Limiti geometrici del numero di tavoli contemporanei, calcolati una volta per sala e salvati su file.
    Per un vettore non ancora calcolato vale il minimo tra quelli calcolati che lui domina (il limite non cresce
    se si chiedono più tavoli grandi), quindi resta sempre un limite valido."""

    def __init__(self, cartella: str | Path, sala: dict, soglie: list[int]):
        inv = sala["inventario"]
        self.soglie = soglie
        self.n_max = int(inv["moduli"]["quantita"]) + int(inv.get("tondi", {}).get("quantita", 0))
        chiave = json.dumps({k: sala.get(k) for k in ("larghezza_cm", "altezza_cm", "griglia_cm", "ostacoli", "corsie",
                                                      "inventario", "margine_sedie_cm")}, sort_keys=True)
        self.chiave = hashlib.sha1(chiave.encode("utf-8")).hexdigest()[:16]
        self.file = Path(cartella) / f"_geometria_{self.chiave}.json"
        self.valori: dict[tuple, int] = dict(_CACHE_GEOMETRIA.get(self.chiave, {}))
        self._lock = threading.Lock()
        try:
            dati = json.loads(self.file.read_text(encoding="utf-8"))
            self.valori.update({tuple(int(x) for x in k.split(",")): v for k, v in dati["valori"].items()})
        except (OSError, ValueError, KeyError):
            pass

    def vettori_da_calcolare(self, massimi=(6, 3, 2, 1)) -> list[tuple]:
        """Vettori (tavoli con capienza >= ciascuna soglia) plausibili in una serata: non crescenti, entro `massimi`."""
        cap = [massimi[i] if i < len(massimi) else 1 for i in range(len(self.soglie))]
        out = []
        for v in itertools.product(*[range(c + 1) for c in cap]):
            if all(a >= b for a, b in zip(v, v[1:])) and v not in self.valori:
                out.append(v)
        return sorted(out, key=sum)

    def registra(self, v: tuple, valore: int) -> None:
        from .serate import scrivi_json_atomico
        with self._lock:
            self.valori[tuple(v)] = int(valore)
            _CACHE_GEOMETRIA.setdefault(self.chiave, {})[tuple(v)] = int(valore)
            try:
                scrivi_json_atomico(self.file, {"valori": {",".join(map(str, k)): x for k, x in self.valori.items()}})
            except OSError:
                pass

    def limite(self, v: tuple) -> int:
        with self._lock:
            if tuple(v) in self.valori:
                return self.valori[tuple(v)]
            dominati = [x for k, x in self.valori.items() if all(a <= b for a, b in zip(k, v))]
        return min(dominati, default=self.n_max)


def impossibile_per_geometria(ist, voci, pr, st: int, geo: Geometria | None, fissa: bool) -> bool:
    """Condizione SUFFICIENTE di impossibilità: le prenotazioni attive (con la nuova a `st`) chiedono più tavoli di
    quanti la sala ne contiene insieme, con i tavoli grandi richiesti. In disposizione fissa i tavoli sono gli stessi
    tutta la sera, quindi servono insieme il massimo nel tempo del totale e di ogni classe di capienza; in variabile
    il controllo si fa istante per istante."""
    if geo is None:
        return False
    if ist.turni:           # a turni: le prenotazioni "attive insieme" sono quelle dello stesso turno
        per_turno: dict[int, list[int]] = {}
        for v in voci:
            per_turno.setdefault(ist.turno_da_passo(v.opzioni[0][1]), []).append(v.pr.coperti)
        per_turno.setdefault(ist.turno_da_passo(st), []).append(pr.coperti)
        vettori = {k: tuple(sum(1 for c in cop if c >= s) for s in geo.soglie) for k, cop in per_turno.items()}
        if fissa:
            tot = max(len(c) for c in per_turno.values())
            v = tuple(max(x[i] for x in vettori.values()) for i in range(len(geo.soglie)))
            return tot > geo.limite(v)
        return any(len(per_turno[k]) > geo.limite(vettori[k]) for k in per_turno)
    R, Z, passo = ist.riapp_passi, ist.orizzonte_passi, ist.passo
    blocchi = [(v.opzioni[0][1], v.opzioni[0][1] + ist.durata_min(v.pr.coperti) // passo + R, v.pr.coperti)
               for v in voci]
    blocchi.append((st, st + ist.durata_min(pr.coperti) // passo + R, pr.coperti))
    tot_max, per_soglia_max = 0, [0] * len(geo.soglie)
    for tau in range(Z):
        att = [c for a, b, c in blocchi if a <= tau < b]
        if not att:
            continue
        vett = tuple(sum(1 for c in att if c >= s) for s in geo.soglie)
        if fissa:
            tot_max = max(tot_max, len(att))
            per_soglia_max = [max(a, b) for a, b in zip(per_soglia_max, vett)]
        elif len(att) > geo.limite(vett):
            return True
    return fissa and tot_max > geo.limite(tuple(per_soglia_max))


# --------------------------------------------------------------------------- istanza e risoluzione

def istanza(sala: dict, data_iso: str, accettate: list[dict], coperti: int, orario: str, escludi: str | None = None):
    """Istanza del motore con le accettate (orari congelati) più la richiesta `_richiesta_`."""
    acc = [a for a in accettate if a["id"] != escludi]
    pren = [{"id": a["id"], "nome": a["nome"], "coperti": a["coperti"], "orario": a["orario"]} for a in acc]
    pren.append({"id": "_richiesta_", "nome": "richiesta", "coperti": coperti, "orario": orario})
    ist = costruisci_istanza(sala, {"serata": data_iso, "prenotazioni": pren})
    per_id = {p.id: p for p in ist.prenotazioni}
    voci = [_Voce(per_id[a["id"]], [(0, ist.a_passi(hhmm_a_min(a["orario"])))], True) for a in acc]
    return ist, voci, per_id["_richiesta_"]


def hint_completo(mod, hint: dict | None, liberi: tuple = ()) -> bool:
    """L'hint dà un valore a ogni variabile del modello, salvo quelle il cui nome contiene una delle stringhe
    `liberi` (es. le variabili della prenotazione nuova)?"""
    return bool(hint) and all(vp.name in hint or any(s in vp.name for s in liberi) for vp in mod.m.proto.variables)


def risolvi_interrompibile(mod, tempo_s: float, worker: int, seed: int, hint: dict | None = None,
                           stop=None, primo: bool = False, fissa_hint: bool = False) -> tuple[str, dict | None]:
    """Come `modello._risolvi_modello`, ma con un osservatore che ferma la ricerca quando `stop()` restituisce un
    motivo (versione superata, richiesta annullata, priorità a una richiesta urgente). Con `fissa_hint` il solver
    parte dalle variabili fissate al valore dell'hint: è il controllo, fatto da CP-SAT con tutti i vincoli, che il
    piano proposto è ammissibile (OPTIMAL) oppure no (INFEASIBLE)."""
    from ortools.sat.python import cp_model
    m = mod.m
    m.clear_hints()
    if hint:
        for idx, vp in enumerate(m.proto.variables):
            if vp.name in hint:
                m.add_hint(m.get_int_var_from_proto_index(idx), hint[vp.name])
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tempo_s
    solver.parameters.num_workers = worker
    solver.parameters.random_seed = seed
    if primo:
        solver.parameters.stop_after_first_solution = True
    if fissa_hint:
        solver.parameters.fix_variables_to_their_hinted_value = True
    motivo = []
    fatto = threading.Event()

    def osserva():
        while not fatto.wait(0.05):
            r = stop() if stop else None
            if r:
                motivo.append(r)
                solver.stop_search()
                return

    t = threading.Thread(target=osserva, daemon=True)
    if stop:
        t.start()
    stato = solver.solve(m)
    fatto.set()
    if motivo:
        return motivo[0], None
    nome = solver.status_name(stato)
    if stato in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return nome, {vp.name: int(v) for vp, v in zip(m.proto.variables, solver.response_proto.solution)}
    return nome, None


def esegui_cella(task: dict, stop=None) -> dict:
    """Una cella: la richiesta (coperti, orario + spostamento) entra con le accettate? Usata nei processi e in locale."""
    t0 = time.perf_counter()
    ist, voci, pr = istanza(task["sala"], task["data"], task["accettate"], task["coperti"], task["orario"],
                            task.get("escludi"))
    sm = task["spostamento"]
    st = ist.a_passi(pr.orario_min + sm)
    esito = {"id": task["id"], "spostamento": sm, "piano": None}
    if _impossibile_per_conteggio(ist, voci, pr, st, task["disposizione"]):
        return esito | {"esito": NON_ENTRA, "come": "conteggio", "tempo_s": round(time.perf_counter() - t0, 3)}
    mod = _costruisci(ist, voci + [_Voce(pr, [(sm, st)], True)], task["disposizione"], obiettivo="nessuno")
    if task.get("max_tavoli"):     # ridondante, dimostrato: mai più tavoli di quanti ne entrano insieme
        m = mod.m
        if task["disposizione"] == "fissa":
            m.add(sum(sl.p for sl in mod.slots) <= int(task["max_tavoli"]))
    stato, piano = risolvi_interrompibile(mod, task["tempo_s"], task["worker"], task.get("seed", 42),
                                          task.get("hint"), stop)
    if piano is not None:
        r = {"esito": ENTRA, "come": "solver", "piano": piano}
    elif stato == "INFEASIBLE":
        r = {"esito": NON_ENTRA, "come": "solver"}
    elif stato in ("superata", "annullata", "interrotta"):
        r = {"esito": stato, "come": "stop"}
    else:
        r = {"esito": DA_VERIFICARE, "come": stato}
    return esito | r | {"tempo_s": round(time.perf_counter() - t0, 3)}


# --------------------------------------------------------------------------- processi di calcolo

def _versione_file(cartella: str, data_iso: str) -> int | None:
    """Versione corrente dello stato della serata (0 se il file non c'è ancora: serata mai modificata)."""
    p = Path(cartella, f"{data_iso}.versione")
    for _ in range(3):
        try:
            return int(p.read_text(encoding="utf-8").strip())
        except FileNotFoundError:
            return 0
        except (OSError, ValueError):        # file in sostituzione in questo istante: si riprova
            time.sleep(0.01)
    return None


def _ciclo(urgenti, fondo, risultati, taglio, urgenti_attesi, versioni, chiuso):
    """Processo di calcolo: prende prima le celle urgenti, poi quelle di background; interrompe un calcolo se la
    versione dello stato è cambiata (`versioni`, memoria condivisa scritta dal processo della chat: i processi non
    aprono mai i file dello stato, che su Windows non si potrebbero sostituire mentre sono aperti), se la richiesta
    urgente è stata chiusa o (per il background) se c'è una richiesta urgente in attesa, che passa davanti."""
    import ortools.sat.python.cp_model  # noqa: F401  (carica OR-Tools una volta sola)
    risultati.cancel_join_thread()       # alla chiusura non si resta appesi su risultati che nessuno legge più
    risultati.put({"id": "_pronto_", "pid": os.getpid()})
    while not chiuso.value:
        task = None
        try:
            task = urgenti.get_nowait()
            with urgenti_attesi.get_lock():
                urgenti_attesi.value -= 1
        except queue.Empty:
            try:
                task = fondo.get(timeout=0.05)
            except queue.Empty:
                continue
        if task is None:
            return
        urgente = task["priorita"] == "urgente"

        def stop(task=task, urgente=urgente):
            if chiuso.value:
                return "annullata"
            if task.get("slot") is not None and versioni[task["slot"]] != task["versione"]:
                return "superata"
            if urgente and task["token"] <= taglio.value:
                return "annullata"
            if not urgente and urgenti_attesi.value > 0:
                return "interrotta"
            return None

        if task.get("tipo") == "geometria":
            try:
                v = calcola_max_tavoli(task["sala"], tuple(task["vettore"]), task["soglie"], task["tempo_s"],
                                       task["worker"])
                risultati.put({"id": task["id"], "esito": "geometria", "valore": v, "vettore": task["vettore"]})
            except Exception as e:  # noqa: BLE001
                risultati.put({"id": task["id"], "esito": "errore", "come": repr(e)})
            continue
        motivo = stop()
        if motivo:
            risultati.put({"id": task["id"], "esito": motivo, "come": "stop", "piano": None, "tempo_s": 0.0})
            continue
        try:
            risultati.put(esegui_cella(task, stop))
        except Exception as e:  # noqa: BLE001  (un errore in una cella non deve fermare il processo)
            risultati.put({"id": task["id"], "esito": DA_VERIFICARE, "come": f"errore: {e!r}", "piano": None,
                           "tempo_s": 0.0})


N_SERATE = 512       # serate distinte tenute in memoria condivisa (poi gli indici si riusano)


class Calcolatore:
    """Processi persistenti (OR-Tools caricato una volta), due code con priorità, risultati via callback."""

    def __init__(self, cartella: str | Path, processi: int, worker: int):
        ctx = mp.get_context("spawn")
        self.cartella, self.processi, self.worker = str(cartella), processi, worker
        self.urgenti, self.fondo, self.risultati = ctx.Queue(), ctx.Queue(), ctx.Queue()
        for q in (self.urgenti, self.fondo, self.risultati):
            q.cancel_join_thread()     # all'uscita (anche per un errore) non si aspetta di consegnare celle in coda
        self.taglio = ctx.Value("q", 0)
        self.urgenti_attesi = ctx.Value("i", 0)
        self.chiuso = ctx.Value("b", 0)
        self.versioni = ctx.Array("q", N_SERATE)       # versione corrente di ogni serata (indice da _slot)
        self._slot: dict[str, int] = {}
        self._callback: dict[str, object] = {}
        self._lock = threading.Lock()
        self._contatore = itertools.count(1)
        self.pronti = 0
        self._evento_pronti = threading.Event()
        self.proc = [ctx.Process(target=_ciclo, args=(self.urgenti, self.fondo, self.risultati, self.taglio,
                                                      self.urgenti_attesi, self.versioni, self.chiuso), daemon=True)
                     for _ in range(processi)]
        for p in self.proc:
            p.start()
        self._ascoltatore = threading.Thread(target=self._ascolta, daemon=True)
        self._ascoltatore.start()

    def attendi_avvio(self, timeout: float = 120.0) -> bool:
        return self._evento_pronti.wait(timeout)

    def _ascolta(self):
        while True:
            try:
                r = self.risultati.get()
            except (EOFError, OSError):
                return
            if r is None:
                return
            if r.get("id") == "_pronto_":
                self.pronti += 1
                if self.pronti >= self.processi:
                    self._evento_pronti.set()
                continue
            with self._lock:
                cb = self._callback.pop(r["id"], None)
            if cb is not None:
                try:
                    cb(r)
                except Exception:  # noqa: BLE001
                    pass

    def _indice(self, data_iso: str, versione: int) -> int:
        """Indice della serata nella memoria condivisa (alla prima volta vi scrive la versione)."""
        if data_iso not in self._slot:
            self._slot[data_iso] = len(self._slot) % N_SERATE
            self.versioni[self._slot[data_iso]] = int(versione)
        return self._slot[data_iso]

    def imposta_versione(self, data_iso: str, versione: int) -> None:
        """Lo stato della serata è alla `versione`: i calcoli delle versioni precedenti si fermano da soli."""
        with self._lock:
            self.versioni[self._indice(data_iso, versione)] = int(versione)

    def invia(self, task: dict, callback, urgente: bool = False) -> str:
        task = dict(task, id=f"t{next(self._contatore)}", priorita="urgente" if urgente else "fondo",
                    worker=task.get("worker", self.worker))
        with self._lock:
            self._callback[task["id"]] = callback
            if task.get("tipo") != "geometria":
                task["slot"] = self._indice(task["data"], task["versione"])
        if urgente:
            with self.urgenti_attesi.get_lock():
                self.urgenti_attesi.value += 1
            self.urgenti.put(task)
        else:
            self.fondo.put(task)
        return task["id"]

    def annulla_urgenti_fino_a(self, token: int) -> None:
        with self.taglio.get_lock():
            self.taglio.value = max(self.taglio.value, token)

    def chiudi(self):
        """Ferma i processi (anche a metà di un calcolo) senza restare appesi: le celle ancora in coda si buttano,
        altrimenti all'uscita il thread di scrittura della coda aspetterebbe per sempre un lettore che non c'è più."""
        if self.chiuso.value:
            return
        self.chiuso.value = 1
        for q in (self.urgenti, self.fondo):
            q.cancel_join_thread()
        for _ in self.proc:
            self.urgenti.put(None)
        fine = time.monotonic() + 5
        for p in self.proc:
            p.join(timeout=max(0.1, fine - time.monotonic()))
        for p in self.proc:
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)
        self.risultati.cancel_join_thread()
        self.risultati.put(None)


class CalcolatoreLocale:
    """Stessa interfaccia, ma calcola nel thread chiamante (test e uso senza processi)."""

    def __init__(self, cartella, worker: int = 8):
        self.cartella, self.worker = str(cartella), worker
        self._contatore = itertools.count(1)

    def attendi_avvio(self, timeout: float = 0) -> bool:
        return True

    def imposta_versione(self, data_iso: str, versione: int) -> None:
        pass                    # qui la versione si legge dal file a ogni cella

    def invia(self, task, callback, urgente: bool = False) -> str:
        task = dict(task, id=f"t{next(self._contatore)}", priorita="urgente" if urgente else "fondo",
                    worker=task.get("worker", self.worker))
        if task.get("tipo") == "geometria":
            callback({"id": task["id"], "esito": "geometria", "vettore": task["vettore"],
                      "valore": calcola_max_tavoli(task["sala"], tuple(task["vettore"]), task["soglie"],
                                                   task["tempo_s"], task["worker"])})
            return task["id"]
        if _versione_file(self.cartella, task["data"]) != task["versione"]:
            callback({"id": task["id"], "esito": "superata", "come": "stop", "piano": None, "tempo_s": 0.0})
        else:
            callback(esegui_cella(task))
        return task["id"]

    def annulla_urgenti_fino_a(self, token: int) -> None:
        pass

    def chiudi(self):
        pass


# --------------------------------------------------------------------------- tabella

@dataclass
class Tabella:
    data: str
    versione: int
    classi: list
    celle: dict = field(default_factory=dict)       # (classe, inizio_passi) -> esito
    come: dict = field(default_factory=dict)        # (classe, inizio) -> conteggio | geometria | solver | dominanza
    piani: dict = field(default_factory=dict)       # (classe, inizio_passi) -> piano (in memoria)
    da_fare: int = -1                               # -1 = in preparazione (non ancora completa)
    t_inizio: float = 0.0
    t_fine: float | None = None

    @property
    def completa(self) -> bool:
        return self.da_fare == 0 and self.t_fine is not None

    def come_json(self, ist) -> dict:
        celle: dict = {}
        for (k, st), e in sorted(self.celle.items(), key=lambda x: (x[0][0], x[0][1])):
            celle.setdefault(k, {})[min_a_hhmm(ist.inizio_min + st * ist.passo)] = e
        return {"data": self.data, "versione": self.versione, "classi": [c.nome for c in self.classi],
                "completa": self.completa, "celle": celle,
                "durata_s": round((self.t_fine or time.perf_counter()) - self.t_inizio, 2)}


@dataclass
class Valutazione:
    esito: str                  # "entra" | "opzioni" | "pieno" | "troppo_grande" | "non_deciso" | "parziale"
    opzioni: list[str]          # orari proposti (o, se "parziale", gli orari dimostrati ammissibili)
    dettaglio: str = ""
    tabella_pronta: bool | None = None
    piano: dict | None = None   # piano con la richiesta all'orario chiesto (per registrare con l'hint)
    in_verifica: list[str] = field(default_factory=list)   # orari ancora da dimostrare (risposta parziale)


def _candidati(ist, pr):
    """Orario chiesto, spostamenti ammessi (dal più vicino) e orari prima/dopo entro la distanza massima."""
    t = ist.a_passi(pr.orario_min)
    ops = ist.opzioni(pr)
    esatto = (0, t) if (0, t) in ops else None
    ammessi = sorted((o for o in ops if o[0] != 0), key=lambda o: (abs(o[0]), o[0] > 0))
    prima, dopo = ist.candidati_proposta(pr)
    return esatto, ammessi, prima, dopo


def decidi(esito_di, esatto, ammessi, prima, dopo, ist, pr) -> Valutazione | None:
    """Decide la risposta dagli esiti noti delle celle; None se manca ancora qualcosa di determinante.
    `esito_di((sm, st))` -> ENTRA | NON_ENTRA | None (non ancora noto)."""
    hh = lambda sm: min_a_hhmm(pr.orario_min + sm)  # noqa: E731
    if esatto is not None:
        e = esito_di(esatto)
        if e == ENTRA:
            return Valutazione("entra", [hh(0)])
        if e is None:
            return None
    noti = {o: esito_di(o) for o in ammessi}
    if any(v == ENTRA for v in noti.values()):
        if any(v is None for v in noti.values()):
            return None            # la lista degli spostamenti ammessi deve essere completa
        return Valutazione("opzioni", sorted(hh(o[0]) for o, v in noti.items() if v == ENTRA))
    if any(v is None for v in noti.values()):
        return None
    opzioni = []
    for lista in (prima, dopo):
        for o in lista:
            e = esito_di(o)
            if e is None:
                return None        # il più vicino va trovato con tutti i più vicini dimostrati impossibili
            if e == ENTRA:
                opzioni.append(hh(o[0]))
                break
    if opzioni:
        return Valutazione("opzioni", sorted(opzioni))
    return Valutazione("pieno", [])


class Disponibilita:
    """Tabelle per serata + verifica urgente. Thread-safe; i risultati arrivano dal thread dell'ascoltatore."""

    def __init__(self, cartella: str | Path, sala: dict, calcolatore, tempo_cella_s: float = 20.0,
                 tempo_urgente_s: float = 30.0, attesa_max_s: float = 5.0, worker_urgenti: int | None = None,
                 cartella_geometria: str | Path | None = None, proposta_max_min: int | None = None):
        self.cartella, self.sala, self.calc = Path(cartella), sala, calcolatore
        self.tempo_cella_s, self.tempo_urgente_s, self.attesa_max_s = tempo_cella_s, tempo_urgente_s, attesa_max_s
        self.worker_urgenti = worker_urgenti
        # distanza massima delle proposte: quella della chat (come nella verifica diretta), non quella delle simulazioni
        self.proposta_max_min = int(proposta_max_min if proposta_max_min is not None
                                    else sala.get("chat", {}).get("proposta_max_min", 60))
        self.tabelle: dict[str, Tabella] = {}
        self._noti: dict[tuple, str] = {}     # (data, versione, classe, inizio) -> esito dimostrato da una verifica urgente
        self._ist: dict[str, object] = {}
        self._token = itertools.count(1)
        self.cond = threading.Condition(threading.RLock())
        self.disposizione = sala.get("chat", {}).get("disposizione", "fissa")
        ist0, _, _ = istanza(sala, "2000-01-01", [], 2, sala["servizio"]["inizio"])
        self.classi = classi_coperti(ist0)
        self.geo_pronta = threading.Event()
        if "piantina" in sala:          # sala vera: tavoli fermi, niente limite geometrico da calcolare
            self.geo = None
            self.geo_pronta.set()
        else:
            self.geo = Geometria(cartella_geometria or Path(__file__).resolve().parent.parent / "dati" / "cache", sala,
                                 soglie_capienza(self.classi))
            self._avvia_geometria()

    def _avvia_geometria(self) -> None:
        """Limiti geometrici mancanti: calcolati una volta per sala, in background (poi restano su file)."""
        mancanti = self.geo.vettori_da_calcolare()
        if not mancanti:
            self.geo_pronta.set()
            return
        restanti = [len(mancanti)]

        def fatto(r):
            if r.get("esito") == "geometria":
                self.geo.registra(tuple(r["vettore"]), r["valore"])
            with self.cond:
                restanti[0] -= 1
                if restanti[0] == 0:
                    self.geo_pronta.set()
                self.cond.notify_all()

        for v in mancanti:
            self.calc.invia({"tipo": "geometria", "sala": self.sala, "vettore": list(v), "soglie": self.geo.soglie,
                             "tempo_s": 60.0, "data": "geometria", "versione": 0}, fatto)

    def segnala_versione(self, stato: dict) -> None:
        """Nuova versione dello stato: i processi smettono subito di calcolare per quelle vecchie."""
        f = getattr(self.calc, "imposta_versione", None)
        if f is not None:
            f(stato["data"], int(stato.get("versione", 0)))

    def _impossibile(self, ist, voci, pr, st) -> str | None:
        if _impossibile_per_conteggio(ist, voci, pr, st, self.disposizione):
            return "conteggio"
        if impossibile_per_geometria(ist, voci, pr, st, self.geo, self.disposizione == "fissa"):
            return "geometria"
        return None

    # ------------------------------------------------------------------ tabella in background
    def _hint(self, data_iso: str) -> dict | None:
        p = self.cartella / f"{data_iso}.piano.json"
        try:
            return json.loads(p.read_text(encoding="utf-8"))["piano"]
        except (OSError, ValueError, KeyError):
            return None

    def aggiorna(self, stato: dict) -> None:
        """Riparte da capo per la versione corrente dello stato (le celle della versione vecchia si scartano)."""
        data_iso, versione = stato["data"], stato.get("versione", 0)
        accettate = [dict(a) for a in stato["accettate"]]
        ist, _, _ = istanza(self.sala, data_iso, accettate, 2, self.sala["servizio"]["inizio"])
        classi = classi_coperti(ist)
        with self.cond:
            vecchia = self.tabelle.get(data_iso)
            if vecchia is not None and vecchia.versione == versione:
                return
            if _versione_file(str(self.cartella), data_iso) != versione:
                return          # stato già superato (thread di aggiornamento arrivato in ritardo): niente tabella
            self.segnala_versione(stato)
            tab = Tabella(data_iso, versione, classi, t_inizio=time.perf_counter())
            self.tabelle[data_iso] = tab
            for chiave in [k for k in self._noti if k[0] == data_iso and k[1] != versione]:
                del self._noti[chiave]       # esiti di versioni superate: non servono più
            self._ist[data_iso] = ist
            hint = self._hint(data_iso)
        if hint is None and accettate:
            hint = self._piano_iniziale(data_iso, accettate, tab)  # fuori dal lock: qualche secondo al massimo
        # celle ovvie (conteggio, geometria), fuori dal lock: intanto le consultazioni non aspettano
        chiuse: dict[tuple, str] = {}
        celle: list[tuple] = []
        for k in classi:
            ist_k, voci_k, pr_k = istanza(self.sala, data_iso, accettate, k.massimo, self.sala["servizio"]["inizio"])
            inizi = ([ist.passo_turno(j) for j in range(len(ist.turni))] if ist.turni else
                     range(0, ist.fine_passi - k.durata_min // ist.passo + 1))
            for st in inizi:
                celle.append((k, st))
                come = self._impossibile(ist_k, voci_k, pr_k, st)
                if come:
                    chiuse[(k.nome, st)] = come
        with self.cond:
            if self.tabelle.get(data_iso) is not tab:
                return
            colonne: dict[int, list] = {}      # per ogni orario, le classi ancora aperte (dalla più piccola)
            for k, st in celle:
                chiave = (k.nome, st)
                if tab.celle.get(chiave) in (ENTRA, NON_ENTRA):
                    continue                   # già dimostrata da una verifica urgente durante la preparazione
                if chiave in chiuse:
                    tab.celle[chiave], tab.come[chiave] = NON_ENTRA, chiuse[chiave]
                else:
                    tab.celle[chiave] = None
                    colonne.setdefault(st, []).append(k)
            tab.da_fare = sum(1 for v in tab.celle.values() if v is None)
            dom = dominanza_valida(classi)
            self._dom = dom
            base = {"sala": self.sala, "data": data_iso, "versione": versione, "accettate": accettate,
                    "disposizione": self.disposizione, "tempo_s": self.tempo_cella_s, "hint": hint,
                    "max_tavoli": self.geo.limite(tuple([0] * len(self.geo.soglie))) if self.geo else None}
            if tab.da_fare == 0:
                tab.t_fine = time.perf_counter()
                self._scrivi(tab)
                self.cond.notify_all()
                return
        for st, ks in sorted(colonne.items()):
            if dom:
                self._invia_cella(tab, base, ks, st)
            else:
                for k in ks:
                    self._invia_cella(tab, base, [k], st)

    def _invia_cella(self, tab: Tabella, base: dict, ks: list, st: int, primo: bool = True) -> None:
        """Cerca la soglia della colonna `st` tra le classi `ks` (dalla più piccola) con la dominanza nei due versi:
        se entra una classe entrano anche tutte le più piccole (stesso tavolo, pasto più corto), se non entra non
        entra nessuna delle più grandi. Si prova prima la classe più grande (spesso entra e chiude la colonna con un
        solo calcolo), poi si dimezza. Un calcolo non concluso non fa inferenze: le altre classi si provano da sole."""
        with self.cond:
            if self.tabelle.get(tab.data) is not tab:
                return
            ks = [k for k in ks if tab.celle.get((k.nome, st)) is None]
        if not ks:
            return
        i = len(ks) - 1 if primo else (len(ks) - 1) // 2
        k = ks[i]
        ist = self._ist[tab.data]
        task = dict(base, coperti=k.massimo, orario=min_a_hhmm(ist.inizio_min + st * ist.passo), spostamento=0)

        def fatto(r):
            dopo: list[tuple[list, bool]] = []
            with self.cond:
                if self.tabelle.get(tab.data) is not tab:
                    return                                     # tabella superata
                e = r["esito"]
                if e == "interrotta":
                    dopo = [(ks, primo)]                       # ceduto il posto a una richiesta urgente: si rimette
                elif e == ENTRA:
                    self._segna(tab, k.nome, st, e, r["come"], r.get("piano"))
                    for k2 in ks[:i]:                          # più piccole e più corte: entrano anche loro
                        if tab.celle.get((k2.nome, st)) is None:
                            self._segna(tab, k2.nome, st, ENTRA, "dominanza", r.get("piano"))
                    dopo = [(ks[i + 1:], False)]
                elif e == NON_ENTRA:
                    self._segna(tab, k.nome, st, e, r["come"], None)
                    for k2 in ks[i + 1:]:                      # più grandi e più lunghe: non entrano neanche loro
                        if tab.celle.get((k2.nome, st)) is None:
                            self._segna(tab, k2.nome, st, NON_ENTRA, "dominanza", None)
                    dopo = [(ks[:i], False)]
                elif e == DA_VERIFICARE:
                    self._segna(tab, k.nome, st, e, r["come"], None)
                    dopo = [([k2], True) for k2 in ks if k2 is not k]
                else:
                    return
                self.cond.notify_all()
            for kk, pp in dopo:
                if kk:
                    self._invia_cella(tab, base, kk, st, pp)

        self.calc.invia(task, fatto)

    def _segna(self, tab: Tabella, k: str, st: int, esito: str, come: str, piano) -> None:
        """Registra l'esito di una cella. Durante la preparazione (da_fare = -1) si annota soltanto: il conteggio
        delle celle da fare parte dopo, e una cella già dimostrata non si ricalcola."""
        attuale = tab.celle.get((k, st))
        if attuale in (ENTRA, NON_ENTRA):
            return
        if attuale is None and (k, st) in tab.celle and tab.da_fare > 0:
            tab.da_fare -= 1
        tab.celle[(k, st)] = esito
        tab.come[(k, st)] = come
        if piano is not None:
            tab.piani[(k, st)] = piano
        if tab.da_fare == 0 and tab.t_fine is None:
            tab.t_fine = time.perf_counter()
            self._scrivi(tab)

    def _scrivi(self, tab: Tabella) -> None:
        from .serate import scrivi_json_atomico
        try:
            scrivi_json_atomico(self.cartella / f"{tab.data}.tabella.json", tab.come_json(self._ist[tab.data]))
        except OSError:
            pass

    def _piano_iniziale(self, data_iso: str, accettate: list[dict], tab: Tabella | None = None) -> dict | None:
        """Nessun piano salvato (stato importato o primo avvio): se ne calcola uno, che fa da hint a tutte le celle.
        Si interrompe se nel frattempo la tabella è superata da una versione nuova."""
        from .serate import scrivi_json_atomico
        ist = costruisci_istanza(self.sala, {"serata": data_iso, "prenotazioni": [
            {"id": a["id"], "nome": a["nome"], "coperti": a["coperti"], "orario": a["orario"]} for a in accettate]})
        voci = [_Voce(p, [(0, ist.a_passi(p.orario_min))], True) for p in ist.prenotazioni]
        mod = _costruisci(ist, voci, self.disposizione, obiettivo="nessuno")
        superata = (lambda: "superata" if self.tabelle.get(data_iso) is not tab else None) if tab is not None else None
        _, piano = risolvi_interrompibile(mod, 30.0, 4, 42, None, stop=superata, primo=True)
        if piano is not None:
            try:
                scrivi_json_atomico(self.cartella / f"{data_iso}.piano.json", {"versione": None, "piano": piano})
            except OSError:
                pass
        return piano

    def tabella_pronta(self, d: date) -> bool:
        with self.cond:
            tab = self.tabelle.get(d.isoformat())
            return tab is not None and tab.completa and _versione_file(str(self.cartella), tab.data) == tab.versione

    def attendi_tabella(self, d: date, timeout: float = 300.0) -> tuple[bool, float]:
        """Aspetta la tabella completa della versione CORRENTE dello stato (quella sul file `.versione`); restituisce
        (pronta, secondi di calcolo della tabella)."""
        fine = time.monotonic() + timeout
        with self.cond:
            while True:
                tab = self.tabelle.get(d.isoformat())
                if (tab is not None and tab.completa
                        and _versione_file(str(self.cartella), tab.data) == tab.versione):
                    return True, (tab.t_fine or time.perf_counter()) - tab.t_inizio
                resto = fine - time.monotonic()
                if resto <= 0:
                    return False, time.perf_counter() - (tab.t_inizio if tab else time.perf_counter())
                self.cond.wait(min(resto, 0.5))

    # ------------------------------------------------------------------ consultazione
    def valuta(self, stato: dict, coperti: int, orario: str, escludi: str | None = None,
               attesa_max_s: float | None = None) -> Valutazione:
        data_iso, versione = stato["data"], stato.get("versione", 0)
        ist, voci, pr = istanza(self.sala, data_iso, stato["accettate"], coperti, orario, escludi)
        ist.proposta_max_distanza_min = self.proposta_max_min
        if coperti > ist.capienza_massima:
            return Valutazione("troppo_grande", [])
        esatto, ammessi, prima, dopo = _candidati(ist, pr)
        tutti = ([esatto] if esatto else []) + ammessi + prima + dopo
        with self.cond:
            tab = self.tabelle.get(data_iso)
            usa_tab = (escludi is None and tab is not None and tab.versione == versione
                       and _versione_file(str(self.cartella), data_iso) == versione)
            classe = classe_di(tab.classi, coperti).nome if usa_tab else None
            pronta = bool(usa_tab and tab.completa)
        locali: dict = {}
        piani: dict = {}
        for o in tutti:
            if self._impossibile(ist, voci, pr, o[1]):
                locali[o] = NON_ENTRA

        classe_req = classe_di(self.classi, coperti).nome

        def esito_di(o):
            if o in locali and locali[o] in (ENTRA, NON_ENTRA):
                return locali[o]
            if usa_tab:
                e = tab.celle.get((classe, o[1]))
                if e in (ENTRA, NON_ENTRA):
                    return e
            if escludi is None:
                return self._noti.get((data_iso, versione, classe_req, o[1]))
            return None

        def piano_di(o):
            return piani.get(o) or (tab.piani.get((classe, o[1])) if usa_tab else None)

        with self.cond:
            v = decidi(esito_di, esatto, ammessi, prima, dopo, ist, pr)
        if v is not None:
            v.tabella_pronta = pronta
            v.piano = piano_di(esatto) if v.esito == "entra" else None
            v.dettaglio = "tabella" if usa_tab else "conteggio"
            return v
        # verifica urgente in parallelo delle celle ancora ignote
        token = next(self._token)
        hint = self._hint(data_iso)
        base = {"sala": self.sala, "data": data_iso, "versione": versione, "accettate": stato["accettate"],
                "escludi": escludi, "disposizione": self.disposizione, "tempo_s": self.tempo_urgente_s,
                "hint": hint, "coperti": coperti, "orario": orario, "token": token,
                "max_tavoli": self.geo.limite(tuple([0] * len(self.geo.soglie))) if self.geo else None}
        if self.worker_urgenti:
            base["worker"] = self.worker_urgenti
        attese = [o for o in tutti if esito_di(o) is None]
        self.segnala_versione(stato)          # lo stato passato qui è quello corrente (letto sotto il lock della chat)

        def arrivato(r, o):
            with self.cond:
                if r["esito"] in (ENTRA, NON_ENTRA, DA_VERIFICARE):
                    locali[o] = r["esito"]
                    if r.get("piano") is not None:
                        piani[o] = r["piano"]
                    if escludi is None and r["esito"] in (ENTRA, NON_ENTRA):
                        self._noti[(data_iso, versione, classe_req, o[1])] = r["esito"]
                    t2 = self.tabelle.get(data_iso)
                    if (escludi is None and t2 is not None and t2.versione == versione
                            and r["esito"] in (ENTRA, NON_ENTRA)):
                        k = classe_di(t2.classi, coperti).nome
                        self._segna(t2, k, o[1], r["esito"], r["come"], r.get("piano"))
                self.cond.notify_all()

        for o in attese:
            self.calc.invia(dict(base, spostamento=o[0]), lambda r, o=o: arrivato(r, o), urgente=True)
        scadenza = time.monotonic() + (self.attesa_max_s if attesa_max_s is None else attesa_max_s)
        with self.cond:
            while True:
                v = decidi(esito_di, esatto, ammessi, prima, dopo, ist, pr)
                if v is not None:
                    break
                resto = scadenza - time.monotonic()
                if resto <= 0:
                    break
                self.cond.wait(min(resto, 0.2))
        if v is not None:
            self.calc.annulla_urgenti_fino_a(token)      # risposta decisa: il resto lo fa la tabella
            v.tabella_pronta = pronta
            v.piano = piano_di(esatto) if v.esito == "entra" else None
            v.dettaglio = "verifica urgente"
            return v
        # risposta parziale: solo ciò che è dimostrato; le verifiche continuano in background
        hh = lambda sm: min_a_hhmm(pr.orario_min + sm)  # noqa: E731
        with self.cond:
            sicuri = sorted(hh(o[0]) for o in tutti if esito_di(o) == ENTRA)
            ignoti = [hh(o[0]) for o in tutti if esito_di(o) is None]
        return Valutazione("parziale", sicuri, "verifica urgente (parziale)", pronta, None, ignoti)

    def esito_noto(self, stato: dict, coperti: int, orario: str) -> str | None:
        """Esito ormai noto della cella (stato corrente), senza calcolare: per l'aggiornamento differito."""
        data_iso, versione = stato["data"], stato.get("versione", 0)
        k = classe_di(self.classi, coperti)
        if k is None:
            return None
        ist, _, _ = istanza(self.sala, data_iso, [], 2, self.sala["servizio"]["inizio"])
        st = ist.a_passi(hhmm_a_min(orario))
        with self.cond:
            tab = self.tabelle.get(data_iso)
            if tab is not None and tab.versione == versione:
                e = tab.celle.get((k.nome, st))
                if e in (ENTRA, NON_ENTRA):
                    return e
            return self._noti.get((data_iso, versione, k.nome, st))

    def chiudi(self) -> None:
        self.calc.chiudi()
