"""Chat 1:1 con il proprietario: legge un messaggio, aggiorna lo stato della serata e risponde.

Punto d'ingresso: `gestisci_messaggio(testo, ricevuto_il, mittente, cartella_stato) -> str` (domani lo chiamerà il
webhook WhatsApp). Le decisioni usano il motore esistente (`valuta`/`_primo_ammissibile` di `modello.py`) con la
semantica "chi prenota prima resta dentro": le prenotazioni registrate hanno l'orario congelato e non vengono mai
spostate per farne entrare una nuova. Un orario diverso da quello chiesto non si registra mai da solo: si propone,
e si registra solo quando il proprietario conferma (dopo aver ricontrollato che ci sia ancora posto).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from .dati import ErroreDati, costruisci_istanza, hhmm_a_min, leggi_json, min_a_hhmm
from .lettura import (
    FORMATO_COMPATTO,
    GIORNI,
    LettoreAnthropic,
    Lettura,
    LLMNonDisponibile,
    etichetta_data,
    leggi_compatto,
    leggi_ora,
    nome_proprio,
    normalizza,
    normalizza_orario,
    risolvi_data,
)
from .modello import (_Voce, _cfg_solver, _costruisci, _estrai, _impossibile_per_conteggio, _parametri,
                      _risolvi_modello, calcola_componenti)
from .disponibilita import (NON_ENTRA, ENTRA, Calcolatore, CalcolatoreLocale, Disponibilita, Valutazione,
                            hint_completo, risolvi_interrompibile)
from .serate import Archivio

RADICE = Path(__file__).resolve().parent.parent
SALA_DEFAULT = RADICE / "dati" / "sala_esempio.json"

CHAT_DEFAULT = {"modello": "claude-haiku-5-5", "effort": "low", "max_tokens": 2048, "timeout_s": 30,
                "proposta_max_min": 60, "scadenza_proposta_min": 15, "giorni_max": 90, "servizio_serale": True,
                "tempo_verifica_s": 30, "disposizione": "fissa", "processi": 6, "worker_per_processo": 2,
                "tempo_cella_s": 20, "attesa_max_s": 5}

DOMANDE_CAMPI = {"nome": "a che nome", "coperti": "quante persone", "data": "per quale giorno", "orario": "a che ora"}
ORDINALI = {"prima": 0, "primo": 0, "1": 0, "seconda": 1, "secondo": 1, "2": 1, "terza": 2, "terzo": 2, "3": 2}

_lettore_condiviso: LettoreAnthropic | None = None
_DISP: Disponibilita | None = None        # tabella delle disponibilità in background (se avviata)
_LOCK = threading.RLock()                 # un messaggio alla volta: lo stato resta coerente


class _LettoreAssente:
    disponibile = False


def avvia_disponibilita(cartella_stato: str | Path, sala: dict | None = None, processi: int | None = None,
                        worker: int | None = None, locale: bool = False,
                        cartella_geometria: str | Path | None = None, oggi: date | None = None) -> Disponibilita:
    """Avvia i processi di calcolo e le tabelle delle serate già presenti (da `oggi` in poi). Una sola istanza per
    processo; `locale=True` calcola nel thread chiamante (test)."""
    global _DISP
    sala = sala if sala is not None else leggi_json(SALA_DEFAULT)
    c = cfg_chat(sala)
    processi = int(processi or c["processi"])
    worker = int(worker or c["worker_per_processo"])
    if _DISP is not None:
        _DISP.chiudi()
    calc = CalcolatoreLocale(cartella_stato, worker) if locale else Calcolatore(cartella_stato, processi, worker)
    calc.attendi_avvio(180)
    _DISP = Disponibilita(cartella_stato, sala, calc, tempo_cella_s=float(c["tempo_cella_s"]),
                          tempo_urgente_s=float(c["tempo_verifica_s"]), attesa_max_s=float(c["attesa_max_s"]),
                          cartella_geometria=cartella_geometria, proposta_max_min=int(c["proposta_max_min"]))
    _DISP.geo_pronta.wait(600)        # limiti geometrici della sala: una volta sola, poi restano su file
    archivio = Archivio(cartella_stato)
    for d in archivio.date(oggi or date.today()):
        _aggiorna_in_background(_DISP, archivio.carica(d))
    return _DISP


def ferma_disponibilita() -> None:
    global _DISP
    if _DISP is not None:
        _DISP.chiudi()
        _DISP = None


def _aggiorna_in_background(disp: Disponibilita, stato: dict) -> None:
    """La tabella riparte da capo per la nuova versione; il lavoro di preparazione non ritarda la risposta."""
    disp.segnala_versione(stato)         # subito: i calcoli della versione vecchia si fermano
    if isinstance(disp.calc, CalcolatoreLocale):
        disp.aggiorna(stato)
    else:
        threading.Thread(target=disp.aggiorna, args=(stato,), daemon=True).start()


def cfg_chat(sala: dict) -> dict:
    return {**CHAT_DEFAULT, **sala.get("chat", {})}


def lettore_predefinito(sala: dict) -> LettoreAnthropic:
    """Un lettore per processo (client HTTP riusato tra i messaggi)."""
    global _lettore_condiviso
    if _lettore_condiviso is None:
        c = cfg_chat(sala)
        _lettore_condiviso = LettoreAnthropic(modello=c["modello"], effort=c["effort"], max_tokens=c["max_tokens"],
                                              timeout_s=c["timeout_s"])
    return _lettore_condiviso


def gestisci_messaggio(testo: str, ricevuto_il: datetime, mittente: str, cartella_stato: str | Path,
                       *, sala: dict | None = None, lettore=None) -> str:
    """Gestisce un messaggio del proprietario e restituisce la risposta (testo breve, senza markdown)."""
    t0 = time.perf_counter()
    arrivo = time.monotonic()
    sala = sala if sala is not None else leggi_json(SALA_DEFAULT)
    with _LOCK:
        disp = _DISP if (_DISP is not None and Path(_DISP.cartella).resolve() == Path(cartella_stato).resolve()) else None
        conv = _Conversazione(Archivio(cartella_stato), sala,
                              lettore if lettore is not None else lettore_predefinito(sala), ricevuto_il, mittente, disp,
                              arrivo)
        risposta, data_rif, origine = conv.gestisci(testo.strip())
        conv.registra_messaggio(testo, risposta, data_rif, origine, round(time.perf_counter() - t0, 3))
        if disp is not None:
            for stato in conv.cambiati.values():
                _aggiorna_in_background(disp, stato)
    return risposta


def lettura_da_llm(r) -> Lettura:
    """Dalla risposta strutturata dell'LLM alla lettura normalizzata (i controlli veri li fa `_valida`)."""
    lett = Lettura(r.intento, "llm", nome=nome_proprio(r.nome) if r.nome else None, coperti=r.coperti,
                   orario=r.orario, note=r.note,
                   riferimento_nome=nome_proprio(r.riferimento_nome) if r.riferimento_nome else None,
                   scelta=r.scelta, testo_data=r.testo_data, campi_mancanti=list(r.campi_mancanti),
                   ambiguita=list(r.ambiguita), data_llm=r.data)
    for campo, valore in (("data", r.data), ("riferimento_data", r.riferimento_data)):
        if valore:
            try:
                setattr(lett, campo, date.fromisoformat(valore))
            except ValueError:
                lett.domande.append(f"non capisco la data {valore}")
    return lett


class _Conversazione:
    def __init__(self, archivio: Archivio, sala: dict, lettore, ricevuto_il: datetime, mittente: str,
                 disp: Disponibilita | None = None, arrivo: float | None = None):
        self.archivio, self.sala, self.lettore, self.disp = archivio, sala, lettore, disp
        self.arrivo = time.monotonic() if arrivo is None else arrivo    # per stare nei tempi di risposta promessi
        self.cambiati: dict[str, dict] = {}       # serate con una nuova versione (la tabella va ricalcolata)
        self.ora, self.mittente = ricevuto_il, mittente
        self.oggi = ricevuto_il.date()
        self.cfg = cfg_chat(sala)
        self.inizio = hhmm_a_min(sala["servizio"]["inizio"])
        self.fine = hhmm_a_min(sala["servizio"]["fine"])

    # ------------------------------------------------------------------ ingresso
    def gestisci(self, testo: str) -> tuple[str, date | None, str]:
        prefisso = self._aggiornamento_verifiche()
        risposta, d, origine = self._gestisci(testo)
        return (prefisso + "\n" + risposta if prefisso else risposta), d, origine

    def _aggiornamento_verifiche(self) -> str:
        """Una verifica rimasta a metà (risposta parziale) si è chiusa in background? Lo si dice ora."""
        if self.disp is None:
            return ""
        mitt = self.archivio.mittenti()
        io = mitt.get(self.mittente, {})
        v = io.get("verifica")
        if not v:
            return ""
        if datetime.fromisoformat(v["scade_il"]) < self.ora:
            io.pop("verifica")
            self._salva_mittente(mitt, io)
            return ""
        stato = self.archivio.carica(date.fromisoformat(v["data"]))
        e = self.disp.esito_noto(stato, v["coperti"], v["orario"]) if v.get("id_prenotazione") is None else None
        if e is None:
            return ""
        io.pop("verifica")
        self._salva_mittente(mitt, io)
        campi = f"{v['nome']} · {v['coperti']} persone · {etichetta_data(date.fromisoformat(v['data']))}"
        if e == NON_ENTRA:
            return f"Aggiornamento: {campi}, alle {v['orario']} non c'è posto."
        prop = next((p for p in stato["proposte_in_sospeso"] if p["mittente"] == self.mittente), None)
        opzioni = sorted({v["orario"], *(prop["opzioni"] if prop else [])})
        scade = self.ora + timedelta(minutes=int(self.cfg["scadenza_proposta_min"]))
        nuova = {"mittente": self.mittente, "tipo": "nuova", "id_prenotazione": None, "opzioni": opzioni,
                 "richiesta": {"nome": v["nome"], "coperti": v["coperti"], "orario": v["orario"], "note": v.get("note"),
                               "data": v["data"]},
                 "creata_il": self.ora.isoformat(timespec="seconds"), "scade_il": scade.isoformat(timespec="seconds")}
        stato["proposte_in_sospeso"] = [p for p in stato["proposte_in_sospeso"] if p["mittente"] != self.mittente] + [nuova]
        self.archivio.salva(stato)
        return f"Aggiornamento: {campi}, alle {v['orario']} c'è posto: rispondi «{v['orario']}» per registrarla."

    def _gestisci(self, testo: str) -> tuple[str, date | None, str]:
        mitt = self.archivio.mittenti()
        io = mitt.get(self.mittente, {})
        for chiave in ("bozza", "scelta", "omonimo"):
            if chiave in io and datetime.fromisoformat(io[chiave]["scade_il"]) < self.ora:
                io.pop(chiave)
        # 1) risposta a una proposta in sospeso
        attiva = self._proposta(tutte=True)
        if attiva is not None:
            stato, prop = attiva
            scelta = self._interpreta_conferma(testo, prop["opzioni"])
            if scelta is not None:
                if datetime.fromisoformat(prop["scade_il"]) < self.ora:
                    self._togli_proposta(stato)
                    return (f"La proposta per {prop['richiesta']['nome']} ({', '.join(prop['opzioni'])}) è scaduta: "
                            f"rimandami la richiesta.", date.fromisoformat(stato["data"]), "conferma")
                self._salva_mittente(mitt, io)
                risposta, d = self._conferma(stato, prop, scelta)
                return risposta, d, "conferma"
        # 2) risposta alla domanda "c'è già Rossi: è un'altra prenotazione o la sposto?"
        if "omonimo" in io:
            t = normalizza(testo)
            altra = re.search(r"\b(altra|altro|nuova|diversa|un altra|un'altra|seconda prenotazione)\b", t)
            sposta = re.search(r"\b(sposta\w*|sposto|modifica\w*|cambia\w*|stessa|stesso|lei|quella|si|ok)\b", t)
            if altra or sposta:
                om = io.pop("omonimo")
                self._salva_mittente(mitt, io)
                r = om["lettura"]
                lett = Lettura("nuova", "omonimo", nome=r["nome"], coperti=r["coperti"], orario=r["orario"],
                               note=r.get("note"), data=date.fromisoformat(r["data"]))
                if altra:
                    return self._nuova(lett, forza_nuova=True), lett.data, "omonimo"
                lett.intento = "modifica"
                return self._esegui_su_prenotazione("modifica", lett, lett.data, om["id"]) + ("omonimo",)
        # 3) scelta tra prenotazioni omonime
        if "scelta" in io:
            idx = self._interpreta_scelta(testo, io["scelta"]["candidati"])
            if idx is not None:
                sc = io.pop("scelta")
                self._salva_mittente(mitt, io)
                lett = Lettura(**{k: v for k, v in sc["lettura"].items()})
                lett.data = date.fromisoformat(sc["lettura"]["data"]) if sc["lettura"].get("data") else None
                cand = sc["candidati"][idx]
                return self._esegui_su_prenotazione(sc["azione"], lett, date.fromisoformat(cand["data"]), cand["id"]) \
                    + ("scelta",)
        # 3) completamento di una bozza (campi mancanti chiesti prima)
        lett = None
        if "bozza" in io:
            lett = self._completa_bozza(io["bozza"], testo)
        # 4) formato compatto
        if lett is None:
            lett = leggi_compatto(testo)
        # 5) LLM
        if lett is None:
            lett = self._leggi_llm(testo, io)
            if isinstance(lett, str):
                return lett, None, "llm non disponibile"
        io.pop("bozza", None)
        self._valida(lett)
        if lett.domande or lett.campi_mancanti:
            if lett.intento in ("nuova", "disponibilita"):
                io["bozza"] = self._bozza(lett)
            self._salva_mittente(mitt, io)
            return self._chiedi(lett), lett.data, lett.origine
        self._salva_mittente(mitt, io)
        return self._esegui(lett) + (lett.origine,)

    def _salva_mittente(self, mitt: dict, io: dict) -> None:
        if io:
            mitt[self.mittente] = io
        else:
            mitt.pop(self.mittente, None)
        self.archivio.salva_mittenti(mitt)

    # ------------------------------------------------------------------ lettura
    def _leggi_llm(self, testo: str, io: dict) -> Lettura | str:
        if not getattr(self.lettore, "disponibile", False):
            return (f"Lettura automatica disattivata (manca la chiave ANTHROPIC_API_KEY). Scrivi nel formato: "
                    f"{FORMATO_COMPATTO}")
        contesto = []
        attiva = self._proposta(tutte=False)
        if attiva:
            prop = attiva[1]
            contesto.append(f"Proposta in sospeso: {prop['richiesta']['nome']} · {prop['richiesta']['coperti']} persone · "
                            f"{prop['richiesta']['data']}, orari proposti {', '.join(prop['opzioni'])}.")
        if "bozza" in io:
            b = io["bozza"]
            contesto.append(f"Prenotazione in corso ({b['intento']}): nome {b.get('nome')}, coperti {b.get('coperti')}, "
                            f"data {b.get('data')}, orario {b.get('orario')}; mancano {', '.join(b['mancano'])}.")
        try:
            r = self.lettore.leggi(testo, self.ora, self.sala["servizio"]["inizio"], self.sala["servizio"]["fine"],
                                   "\n".join(contesto))
        except LLMNonDisponibile as e:
            return f"Lettura automatica non riuscita ({e}). Scrivi nel formato: {FORMATO_COMPATTO}"
        lett = lettura_da_llm(r)
        if "bozza" in io and lett.intento in ("nuova", "non_capito", io["bozza"]["intento"]):
            b = io["bozza"]
            lett.intento = b["intento"]
            for campo in ("nome", "coperti", "orario", "note"):
                if getattr(lett, campo) is None and b.get(campo) is not None:
                    setattr(lett, campo, b[campo])
            if lett.data is None and lett.testo_data is None and b.get("data"):
                lett.data = date.fromisoformat(b["data"])
            lett.campi_mancanti = [c for c in lett.campi_mancanti if getattr(lett, c, None) is None]
        if lett.intento == "conferma_proposta":
            lett.scelta = lett.scelta or testo
        return lett

    def _completa_bozza(self, bozza: dict, testo: str) -> Lettura | None:
        """Risposte brevi alle domande ("4", "x 4", "alle 21", "Bianchi", "domani") senza LLM."""
        t = normalizza(testo)
        trovati: dict = {}
        resto = t
        d, _, capita = risolvi_data(testo, self.oggi)
        if capita and "data" in bozza["mancano"]:
            trovati["testo_data"] = testo
            resto = re.sub(r"\b(oggi|stasera|domani|dopodomani|sera|prossimo|prossima|lun\w*|mar\w*|mer\w*|gio\w*|"
                           r"ven\w*|sab\w*|dom\w*|\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?)\b", " ", resto)
        m = re.search(r"\b(?:x|per|in|siamo)\s*(\d{1,2})\b(?!\s*[:.]\d)|\b(\d{1,2})\s*(?:pax|persone|coperti)\b", resto)
        if m and "coperti" in bozza["mancano"]:
            trovati["coperti"] = int(m.group(1) or m.group(2))
            resto = resto.replace(m.group(0), " ")
        m = re.search(r"\b(?:alle|verso le|per le|ore)\s+(\d{1,2}(?:[:.]\d{2})?(?:\s+e\s+(?:mezza|mezzo|un quarto))?)"
                      r"|\b(\d{1,2}[:.]\d{2})\b", resto)
        if m and "orario" in bozza["mancano"]:
            trovati["orario"] = m.group(1) or m.group(2)
            resto = resto.replace(m.group(0), " ")
        nudo = re.fullmatch(r"\s*(\d{1,2})\s*", resto)
        if nudo:
            mancano_num = [c for c in ("coperti", "orario") if c in bozza["mancano"] and c not in trovati]
            if len(mancano_num) == 1:
                trovati[mancano_num[0]] = int(nudo.group(1)) if mancano_num[0] == "coperti" else nudo.group(1)
                resto = ""
        resto = re.sub(r"\b(ok|sono|siamo|e|a|al|alle|nome|di|il|la|i|per|grazie)\b", " ", resto).strip(" ,.;!")
        if resto and "nome" in bozza["mancano"] and re.fullmatch(r"[a-z' ]{2,40}", resto) and len(resto.split()) <= 3:
            trovati["nome"] = nome_proprio(resto)
            resto = ""
        if not trovati or resto:
            return None
        lett = Lettura(bozza["intento"], "completamento", nome=bozza.get("nome"), coperti=bozza.get("coperti"),
                       orario=bozza.get("orario"), note=bozza.get("note"),
                       data=date.fromisoformat(bozza["data"]) if bozza.get("data") else None)
        for campo, valore in trovati.items():
            if campo == "orario":
                ora = leggi_ora(str(valore))
                lett.orario = f"{ora[0]:02d}:{ora[1]:02d}" if ora else None
            else:
                setattr(lett, campo, valore)
        return lett

    def _valida(self, lett: Lettura) -> None:
        """Controlli del codice: data (ricalcolata dalle parole, non passata, entro N giorni, giorno coerente),
        orario (servizio serale, griglia), campi obbligatori."""
        if lett.testo_data:
            d, domande, capita = risolvi_data(lett.testo_data, self.oggi)
            if capita:
                if d is not None and lett.data is not None and d != lett.data:
                    lett.avvisi.append(f"data ricalcolata da '{lett.testo_data}': {etichetta_data(d)}")
                lett.data = d if d is not None else lett.data
                if domande:              # data ambigua o incoerente: va richiesta, non indovinata
                    lett.domande += domande
                    lett.data = None
        for campo in ("data", "riferimento_data"):
            d = getattr(lett, campo)
            if d is None:
                continue
            if d < self.oggi:
                lett.domande.append(f"il {d:%d/%m/%Y} è già passato")
                setattr(lett, campo, None)
            elif d > self.oggi + timedelta(days=int(self.cfg["giorni_max"])):
                lett.domande.append(f"il {d:%d/%m/%Y} è oltre {self.cfg['giorni_max']} giorni: confermi la data?")
        if lett.orario:
            ora = leggi_ora(lett.orario)
            if ora is None:
                lett.domande.append(f"non capisco l'orario '{lett.orario}'")
                lett.orario = None
            else:
                o, avvisi = normalizza_orario(ora[0], ora[1], self.inizio, self.fine,
                                              self.sala.get("passo_orari_min", 15), self.cfg["servizio_serale"])
                if o is None:
                    lett.domande += avvisi
                lett.orario = o
                lett.avvisi += [a for a in avvisi if o is not None]
        if lett.coperti is not None and lett.coperti <= 0:
            lett.domande.append("quante persone?")
            lett.coperti = None
        obbligatori = {"nuova": ("nome", "coperti", "data", "orario"), "disponibilita": ("coperti", "data", "orario"),
                       "riepilogo": ("data",)}.get(lett.intento, ())
        lett.campi_mancanti = [c for c in obbligatori if getattr(lett, c) is None]
        if lett.intento in ("modifica", "annulla") and not (lett.riferimento_nome or lett.nome):
            lett.campi_mancanti.append("nome")
        if lett.ambiguita and lett.intento in ("nuova", "modifica", "annulla"):
            lett.domande += [a for a in lett.ambiguita if a not in lett.domande]

    def _bozza(self, lett: Lettura) -> dict:
        return {"intento": lett.intento, "nome": lett.nome, "coperti": lett.coperti, "orario": lett.orario,
                "note": lett.note, "data": lett.data.isoformat() if lett.data else None,
                "mancano": lett.campi_mancanti or [c for c in ("data", "orario") if getattr(lett, c) is None],
                "scade_il": (self.ora + timedelta(minutes=int(self.cfg["scadenza_proposta_min"]))).isoformat()}

    def _campi(self, lett: Lettura) -> str:
        persone = f"{lett.coperti} persone" if lett.coperti else "? persone"
        return " · ".join([lett.nome or "?", persone, etichetta_data(lett.data) if lett.data else "?", lett.orario or "?"])

    def _chiedi(self, lett: Lettura) -> str:
        domande = list(dict.fromkeys(lett.domande))
        mancano = [c for c in lett.campi_mancanti
                   if not (c == "data" and any(k in d for d in domande for k in ("giorno", "stasera", "/")))]
        if mancano:
            domande.append(", ".join(DOMANDE_CAMPI[c] for c in mancano) + "?")
        elif lett.campi_mancanti and domande and not domande[-1].endswith("?"):
            domande[-1] += ": per quale giorno?"
        testa = (self._campi(lett) if lett.intento in ("nuova", "disponibilita") else
                 "Riepilogo" if lett.intento == "riepilogo" else (lett.riferimento_nome or lett.nome or "?"))
        return f"{testa} — " + " ".join(d[:1].upper() + d[1:] for d in domande)

    # ------------------------------------------------------------------ esecuzione
    def _esegui(self, lett: Lettura) -> tuple[str, date | None]:
        if lett.intento == "nuova":
            return self._nuova(lett), lett.data
        if lett.intento == "disponibilita":
            return self._disponibilita(lett), lett.data
        if lett.intento == "riepilogo":
            return self._riepilogo(lett.data), lett.data
        if lett.intento in ("modifica", "annulla"):
            return self._cerca_e_esegui(lett.intento, lett)
        if lett.intento == "conferma_proposta":
            attiva = self._proposta(tutte=True)
            if attiva is None:
                return "Non ho proposte in sospeso per te.", None
            stato, prop = attiva
            scelta = self._interpreta_conferma(lett.scelta or "", prop["opzioni"])
            if scelta is None:
                return f"Quale orario? {' o '.join(prop['opzioni'])}", date.fromisoformat(stato["data"])
            return self._conferma(stato, prop, scelta)
        return ("Non è una prenotazione: non registro niente. Per prenotare scrivi per esempio "
                f"{FORMATO_COMPATTO}"), None

    # istanza del motore con le accettate (orari congelati) più la richiesta
    def _istanza(self, stato: dict, coperti: int, orario: str, escludi: str | None = None):
        acc = [a for a in stato["accettate"] if a["id"] != escludi]
        pren = [{"id": a["id"], "nome": a["nome"], "coperti": a["coperti"], "orario": a["orario"]} for a in acc]
        pren.append({"id": "_richiesta_", "nome": "richiesta", "coperti": coperti, "orario": orario})
        ist = costruisci_istanza(self.sala, {"serata": stato["data"], "prenotazioni": pren})
        per_id = {p.id: p for p in ist.prenotazioni}
        voci = [_Voce(per_id[a["id"]], [(0, ist.a_passi(hhmm_a_min(a["orario"])))], True) for a in acc]
        ist.proposta_max_distanza_min = int(self.cfg["proposta_max_min"])
        return ist, voci, per_id["_richiesta_"]

    def _valuta(self, stato: dict, coperti: int, orario: str, escludi: str | None = None) -> Valutazione:
        if self.disp is not None:
            # l'attesa massima vale dall'arrivo del messaggio, non da qui; 1 s resta per risposta e salvataggi
            resto = self.disp.attesa_max_s - (time.monotonic() - self.arrivo) - 1.0
            return self.disp.valuta(stato, coperti, orario, escludi, attesa_max_s=max(0.3, resto))
        return self._valuta_diretta(stato, coperti, orario, escludi)

    def _valuta_diretta(self, stato: dict, coperti: int, orario: str, escludi: str | None = None) -> Valutazione:
        """Verifica senza tabella, nel processo corrente: un modello per l'orario chiesto, uno per gli spostamenti
        ammessi (ripetuto finché ne trova), uno per il più vicino prima e uno per il più vicino dopo."""
        ist, voci, pr = self._istanza(stato, coperti, orario, escludi)
        if coperti > ist.capienza_massima:
            return Valutazione("troppo_grande", [])
        disp = self.cfg["disposizione"]
        tempo = float(self.cfg["tempo_verifica_s"])
        worker, seed = _parametri(ist, None, None)
        esiti = []

        piani: dict = {}

        def gruppo(candidati: list[tuple[int, int]]) -> tuple[int | None, bool]:
            """Un solo modello con tutti gli orari candidati: c'è un orario ammissibile? Si minimizza |spostamento|,
            quindi l'orario trovato è il più vicino se il solver chiude (OPTIMAL). Gli orari esclusi dal conteggio
            dei moduli (condizione sufficiente) non entrano nel modello. Restituisce (spostamento | None, deciso)."""
            cand = [c for c in candidati if not _impossibile_per_conteggio(ist, voci, pr, c[1])]
            etichetta = "/".join(f"{c[0]:+d}" for c in candidati) + "′"
            if not cand:
                esiti.append(f"{etichetta} CONTEGGIO")
                return None, True
            mod = _costruisci(ist, voci + [_Voce(pr, cand, True)], disp, obiettivo="nessuno")
            if len(cand) > 1:
                mod.m.minimize(sum(abs(sm) * ov for (pid, sm), ov in mod.o.items() if pid == pr.id))
            st, piano, _ = _risolvi_modello(mod, tempo, worker, seed, False)
            esiti.append(f"{etichetta} {st if piano is None else 'AMMISSIBILE'}")
            if piano is None:
                return None, st == "INFEASIBLE"
            sm = next(s_ for (pid, s_), ov in mod.o.items() if pid == pr.id and piano[ov.name])
            piani[sm] = piano
            return sm, True

        ops = ist.opzioni(pr)
        tutti_decisi = True
        t = ist.a_passi(pr.orario_min)
        if (0, t) in ops:
            sm, dec = gruppo([(0, t)])
            if sm is not None:
                return Valutazione("entra", [orario], " · ".join(esiti), piano=piani.get(0))
            tutti_decisi &= dec
        # prima gli spostamenti ammessi (tutti quelli che entrano, dal più vicino), poi il più vicino prima e dopo
        resto = [o for o in ops if o[0] != 0]
        ammessi = []
        while resto:
            sm, dec = gruppo(resto)
            tutti_decisi &= dec
            if sm is None:
                break
            ammessi.append(min_a_hhmm(pr.orario_min + sm))
            resto = [o for o in resto if o[0] != sm]
        if ammessi:
            return Valutazione("opzioni", sorted(ammessi), " · ".join(esiti))
        prima, dopo = ist.candidati_proposta(pr)
        opzioni = []
        for lista in (prima, dopo):
            if not lista:
                continue
            sm, dec = gruppo(lista)
            tutti_decisi &= dec
            if sm is not None:
                opzioni.append(min_a_hhmm(pr.orario_min + sm))
        if opzioni:
            return Valutazione("opzioni", sorted(opzioni), " · ".join(esiti))
        return Valutazione("pieno" if tutti_decisi else "non_deciso", [], " · ".join(esiti))

    def _nuova(self, lett: Lettura, stato: dict | None = None, forza_nuova: bool = False) -> str:
        stato = stato or self.archivio.carica(lett.data)
        avvisi = f" ({'; '.join(lett.avvisi)})" if lett.avvisi else ""
        if not forza_nuova:
            gia = next((a for a in sorted(stato["accettate"], key=lambda a: a["orario"])
                        if normalizza(a["nome"]) == normalizza(lett.nome)), None)
            if gia is not None:
                return self._chiedi_omonimo(gia, lett) + avvisi
        v = self._valuta(stato, lett.coperti, lett.orario)
        if v.esito == "entra":
            a = self._registra_con_piano(stato, lett.nome, lett.coperti, lett.orario, lett.note, lett.orario, v.piano)
            if a is None:
                return (f"{lett.nome} · {lett.coperti} persone · {etichetta_data(lett.data)} · {lett.orario}: non riesco "
                        f"a confermarlo in tempo, riprova tra poco. Non ho registrato niente.")
            return self._conferma_testo(a, stato["data"]) + avvisi
        return self._risposta_non_entra(stato, v, lett, "nuova", None) + avvisi

    def _chiedi_omonimo(self, gia: dict, lett: Lettura) -> str:
        mitt = self.archivio.mittenti()
        io = mitt.get(self.mittente, {})
        io["omonimo"] = {"id": gia["id"], "lettura": {"nome": lett.nome, "coperti": lett.coperti, "orario": lett.orario,
                                                      "note": lett.note, "data": lett.data.isoformat()},
                         "scade_il": (self.ora + timedelta(minutes=int(self.cfg["scadenza_proposta_min"]))).isoformat()}
        self._salva_mittente(mitt, io)
        if (lett.coperti, lett.orario) == (gia["coperti"], gia["orario"]):
            cosa = "è la stessa"
        elif lett.coperti == gia["coperti"]:
            cosa = f"la sposto alle {lett.orario}"
        elif lett.orario == gia["orario"]:
            cosa = f"la porto a {lett.coperti} persone"
        else:
            cosa = f"la cambio in {lett.coperti} persone alle {lett.orario}"
        return (f"C'è già {gia['nome']} alle {gia['orario']} per {gia['coperti']} persone "
                f"({etichetta_data(lett.data)}): è un'altra prenotazione o {cosa}?")

    def _risposta_non_entra(self, stato, v: Valutazione, lett: Lettura, tipo: str, id_pren: str | None,
                            prefisso: str = "") -> str:
        campi = f"{lett.nome} · {lett.coperti} persone · {etichetta_data(lett.data)}"
        if v.esito == "troppo_grande":
            self._rifiuto(stato, lett, "nessun tavolo componibile abbastanza grande")
            self.archivio.salva(stato)
            return f"{campi}: per {lett.coperti} persone non ho un tavolo abbastanza grande."
        if v.esito == "opzioni":
            self._salva_proposta(stato, lett, tipo, id_pren, v.opzioni)
            return (f"{prefisso}{campi}: alle {lett.orario} sono pieno. Posso alle {' o alle '.join(v.opzioni)}. Quale?"
                    + (" (la prenotazione attuale resta valida finché non confermi)" if tipo == "modifica" else ""))
        if v.esito == "parziale":
            self._ricorda_verifica(stato, lett, id_pren)
            if v.opzioni:
                self._salva_proposta(stato, lett, tipo, id_pren, v.opzioni)
                return (f"{prefisso}{campi}: alle {lett.orario} sto ancora verificando; di sicuro posso alle "
                        f"{' o alle '.join(v.opzioni)}. Quale?")
            return f"{prefisso}{campi}: alle {lett.orario} sto ancora verificando, ti scrivo appena so. Non ho registrato niente."
        if v.esito == "non_deciso":
            return f"{campi} · {lett.orario}: non riesco a verificarlo in tempo, riprova tra poco. Non ho registrato niente."
        self._rifiuto(stato, lett, f"nessun orario libero entro {self.cfg['proposta_max_min']} min")
        self.archivio.salva(stato)
        return f"{prefisso}{campi}: sono pieno dalle {lett.orario} fino a {self.cfg['proposta_max_min']} minuti prima e dopo."

    def _salva_proposta(self, stato, lett: Lettura, tipo: str, id_pren: str | None, opzioni: list[str]) -> None:
        scade = self.ora + timedelta(minutes=int(self.cfg["scadenza_proposta_min"]))
        prop = {"mittente": self.mittente, "tipo": tipo, "id_prenotazione": id_pren, "opzioni": opzioni,
                "richiesta": {"nome": lett.nome, "coperti": lett.coperti, "orario": lett.orario, "note": lett.note,
                              "data": stato["data"]},
                "creata_il": self.ora.isoformat(timespec="seconds"), "scade_il": scade.isoformat(timespec="seconds")}
        stato["proposte_in_sospeso"] = [p for p in stato["proposte_in_sospeso"] if p["mittente"] != self.mittente] + [prop]
        self.archivio.salva(stato)

    def _ricorda_verifica(self, stato, lett: Lettura, id_pren: str | None) -> None:
        mitt = self.archivio.mittenti()
        io = mitt.get(self.mittente, {})
        io["verifica"] = {"data": stato["data"], "nome": lett.nome, "coperti": lett.coperti, "orario": lett.orario,
                          "note": lett.note, "id_prenotazione": id_pren,
                          "scade_il": (self.ora + timedelta(minutes=int(self.cfg["scadenza_proposta_min"]))).isoformat()}
        self._salva_mittente(mitt, io)

    def _conferma(self, stato: dict, prop: dict, scelta) -> tuple[str, date | None]:
        d = date.fromisoformat(stato["data"])
        if scelta == "nessuna":
            self._togli_proposta(stato)
            return "Ok, non registro niente.", d
        if scelta == "quale":
            return f"Quale orario? {' o '.join(prop['opzioni'])}", d
        r = prop["richiesta"]
        lett = Lettura(prop["tipo"], "conferma", nome=r["nome"], coperti=r["coperti"], orario=scelta,
                       note=r.get("note"), data=d)
        v = self._valuta(stato, r["coperti"], scelta, escludi=prop.get("id_prenotazione"))
        if v.esito == "entra":
            self._togli_proposta(stato, salva=False)
            if prop["tipo"] == "modifica":
                return self._applica_modifica(stato, prop["id_prenotazione"], r["coperti"], scelta, v.piano), d
            a = self._registra_con_piano(stato, r["nome"], r["coperti"], scelta, r.get("note"), r["orario"], v.piano)
            if a is None:
                return f"{r['nome']} · {scelta}: non riesco a confermarlo in tempo, riprova tra poco.", d
            return self._conferma_testo(a, stato["data"]), d
        # lo stato è cambiato: si ricalcola la proposta sull'orario chiesto all'inizio
        self._togli_proposta(stato, salva=False)
        lett.orario = r["orario"]
        v2 = self._valuta(stato, r["coperti"], r["orario"], escludi=prop.get("id_prenotazione"))
        if v2.esito == "entra":
            v2 = Valutazione("opzioni", [r["orario"]])
        elif v2.esito == "parziale" and not v2.opzioni:
            v2 = Valutazione("parziale", [], in_verifica=v2.in_verifica)
        return self._risposta_non_entra(stato, v2, lett, prop["tipo"], prop.get("id_prenotazione"),
                                        prefisso=f"Le {scelta} non sono più libere. "), d

    def _disponibilita(self, lett: Lettura) -> str:
        stato = self.archivio.carica(lett.data)
        v = self._valuta(stato, lett.coperti, lett.orario)
        q = f"{etichetta_data(lett.data)} alle {lett.orario} per {lett.coperti}"
        if v.esito == "parziale":
            if v.opzioni:
                return f"{q[:1].upper()}{q[1:]}: sto ancora verificando; di sicuro posso alle {' o alle '.join(v.opzioni)}."
            return f"{q[:1].upper()}{q[1:]}: sto ancora verificando, riprova tra poco."
        return self._testo_disponibilita(lett, v, q)

    def _testo_disponibilita(self, lett: Lettura, v: Valutazione, q: str) -> str:
        if v.esito == "entra":
            return f"Sì, {q} c'è posto."
        if v.esito == "troppo_grande":
            return f"{q}: per {lett.coperti} persone non ho un tavolo abbastanza grande."
        if v.esito == "opzioni":
            return f"{q[:1].upper()}{q[1:]}: sono pieno. Posso alle {' o alle '.join(v.opzioni)}."
        if v.esito == "non_deciso":
            return f"{q}: non riesco a verificarlo in tempo, riprova tra poco."
        return f"{q[:1].upper()}{q[1:]}: sono pieno fino a {self.cfg['proposta_max_min']} minuti prima e dopo."

    def _riepilogo(self, d: date) -> str:
        stato = self.archivio.carica(d)
        acc = sorted(stato["accettate"], key=lambda a: (a["orario"], a["nome"]))
        if not acc:
            return f"{etichetta_data(d)}: nessuna prenotazione."
        righe = [f"{etichetta_data(d)} · {len(acc)} {'prenotazione' if len(acc) == 1 else 'prenotazioni'} · {sum(a['coperti'] for a in acc)} coperti"]
        righe += [f"{a['orario']} {a['nome']} {a['coperti']}" + (f" ({a['note']})" if a.get("note") else "") for a in acc]
        return "\n".join(righe)

    # ------------------------------------------------------------------ modifica e annullamento
    def _cerca_e_esegui(self, azione: str, lett: Lettura) -> tuple[str, date | None]:
        nome = lett.riferimento_nome or lett.nome
        dal = lett.riferimento_data or self.oggi
        al = lett.riferimento_data or (self.oggi + timedelta(days=int(self.cfg["giorni_max"])))
        if azione == "annulla" and lett.data and not lett.riferimento_data:
            dal = al = lett.data
        candidati = []
        for d in self.archivio.date(dal, al):
            for a in self.archivio.carica(d)["accettate"]:
                if normalizza(a["nome"]) == normalizza(nome):
                    candidati.append({"data": d.isoformat(), "id": a["id"], "orario": a["orario"], "coperti": a["coperti"]})
        if not candidati:
            return f"Non trovo prenotazioni a nome {nome}" + (f" per {etichetta_data(dal)}." if dal == al else "."), None
        if len(candidati) > 1:
            mitt = self.archivio.mittenti()
            io = mitt.get(self.mittente, {})
            ld = {k: getattr(lett, k) for k in ("intento", "origine", "nome", "coperti", "orario", "note", "riferimento_nome")}
            ld["data"] = lett.data.isoformat() if lett.data else None
            io["scelta"] = {"azione": azione, "candidati": candidati, "lettura": ld,
                            "scade_il": (self.ora + timedelta(minutes=int(self.cfg["scadenza_proposta_min"]))).isoformat()}
            self._salva_mittente(mitt, io)
            elenco = "; ".join(f"{i + 1}) {etichetta_data(date.fromisoformat(c['data']))} {c['orario']} · {c['coperti']} persone"
                               for i, c in enumerate(candidati))
            return f"Ho {len(candidati)} prenotazioni a nome {nome}: {elenco}. Quale?", None
        c = candidati[0]
        return self._esegui_su_prenotazione(azione, lett, date.fromisoformat(c["data"]), c["id"])

    def _esegui_su_prenotazione(self, azione: str, lett: Lettura, d: date, id_pren: str) -> tuple[str, date]:
        stato = self.archivio.carica(d)
        a = next(x for x in stato["accettate"] if x["id"] == id_pren)
        if azione == "annulla":
            stato["accettate"] = [x for x in stato["accettate"] if x["id"] != id_pren]
            stato["annullate"].append({**a, "annullata_il": self.ora.isoformat(timespec="seconds")})
            self._nuova_versione(stato)
            return f"✗ Annullata {a['nome']} · {etichetta_data(d)} · {a['orario']}", d
        nuovi_coperti = lett.coperti or a["coperti"]
        nuovo_orario = lett.orario or a["orario"]
        if lett.data and lett.data != d:
            return (f"{a['nome']} · {etichetta_data(d)} · {a['orario']}: per spostare a un altro giorno annulla e "
                    f"riprenota (il cambio di data non è ancora gestito)."), d
        if (nuovi_coperti, nuovo_orario) == (a["coperti"], a["orario"]):
            return f"Nessuna modifica: {a['nome']} · {a['coperti']} persone · {etichetta_data(d)} · {a['orario']}", d
        v = self._valuta(stato, nuovi_coperti, nuovo_orario, escludi=id_pren)
        if v.esito == "entra":
            return self._applica_modifica(stato, id_pren, nuovi_coperti, nuovo_orario, v.piano), d
        l2 = Lettura("modifica", lett.origine, nome=a["nome"], coperti=nuovi_coperti, orario=nuovo_orario,
                     note=a.get("note"), data=d)
        return self._risposta_non_entra(stato, v, l2, "modifica", id_pren), d

    def _applica_modifica(self, stato: dict, id_pren: str, coperti: int, orario: str, piano: dict | None = None) -> str:
        a = next(x for x in stato["accettate"] if x["id"] == id_pren)
        prima = f"prima {a['coperti']} persone alle {a['orario']}"
        a.update(coperti=coperti, orario=orario, modificata_il=self.ora.isoformat(timespec="seconds"))
        self._nuova_versione(stato, {k.replace("_richiesta_", id_pren): v for k, v in piano.items()} if piano else None)
        return f"✓ Modificata {a['nome']} · {coperti} persone · {etichetta_data(date.fromisoformat(stato['data']))} · {orario} ({prima})"

    # ------------------------------------------------------------------ stato
    def _nuova_versione(self, stato: dict, piano: dict | None = None) -> None:
        """Lo stato è cambiato: nuova versione (la tabella vecchia non vale più), piano come hint, salvataggio."""
        stato["versione"] = int(stato.get("versione", 0)) + 1
        if piano is not None:
            from .serate import scrivi_json_atomico
            scrivi_json_atomico(self.archivio.cartella / f"{stato['data']}.piano.json",
                                {"versione": stato["versione"], "piano": piano})
        self.archivio.salva(stato)
        self.cambiati[stato["data"]] = stato

    def _registra_con_piano(self, stato, nome, coperti, orario, note, orario_richiesto, piano_cella) -> dict | None:
        """Registra solo dopo un solve che restituisce il piano con la nuova prenotazione (veloce: hint dal piano
        della cella o dall'ultimo piano registrato). Se il solve non trova un piano, non registra."""
        a = self._registra(stato, nome, coperti, orario, note, orario_richiesto, salva=False)
        hint = ({k.replace("_richiesta_", a["id"]): v for k, v in piano_cella.items()} if piano_cella else
                self._piano_salvato(stato["data"]))
        ist = costruisci_istanza(self.sala, {"serata": stato["data"], "prenotazioni": [
            {"id": x["id"], "nome": x["nome"], "coperti": x["coperti"], "orario": x["orario"]} for x in stato["accettate"]]})
        voci = [_Voce(p, [(0, ist.a_passi(p.orario_min))], True) for p in ist.prenotazioni]
        mod = _costruisci(ist, voci, self.cfg["disposizione"], obiettivo="nessuno")
        piano = None
        # piano della cella: tavoli e altre prenotazioni fissati come nel piano, CP-SAT sistema solo la nuova (e il
        # picco cucina, che dipende dai suoi coperti) controllando tutti i vincoli; centesimi di secondo
        fisse = ({k: v for k, v in piano_cella.items() if "_richiesta_" not in k and not k.startswith("picco_")}
                 if piano_cella else None)
        if fisse and hint_completo(mod, fisse, liberi=(a["id"], "picco_")):
            _, piano = risolvi_interrompibile(mod, 5.0, 1, 42, fisse, primo=True, fissa_hint=True)
        if piano is None:                # hint parziale o piano non valido: ricerca vera, partendo dall'hint
            _, piano = risolvi_interrompibile(mod, float(self.cfg["tempo_verifica_s"]), 8, 42, hint, primo=True)
        if piano is None:
            stato["accettate"].remove(a)
            stato["contatore"] -= 1
            return None
        self._nuova_versione(stato, piano)
        return a

    def _piano_salvato(self, data_iso: str) -> dict | None:
        try:
            return json.loads((self.archivio.cartella / f"{data_iso}.piano.json").read_text(encoding="utf-8"))["piano"]
        except (OSError, ValueError, KeyError):
            return None

    def _registra(self, stato, nome, coperti, orario, note, orario_richiesto, salva: bool = False) -> dict:
        stato["contatore"] += 1
        a = {"id": f"C{stato['data'].replace('-', '')}-{stato['contatore']:03d}", "nome": nome, "coperti": coperti,
             "orario": orario, "orario_richiesto": orario_richiesto, "note": note or "",
             "prenotata_il": self.ora.isoformat(timespec="seconds"), "mittente": self.mittente}
        stato["accettate"].append(a)
        return a

    def _rifiuto(self, stato, lett: Lettura, motivo: str) -> None:
        stato["rifiuti"].append({"nome": lett.nome, "coperti": lett.coperti, "orario_richiesto": lett.orario,
                                 "motivo": motivo, "ricevuto_il": self.ora.isoformat(timespec="seconds"),
                                 "mittente": self.mittente})

    def _conferma_testo(self, a: dict, data_iso: str) -> str:
        note = f" · {a['note']}" if a.get("note") else ""
        return f"✓ {a['nome']} · {a['coperti']} persone · {etichetta_data(date.fromisoformat(data_iso))} · {a['orario']}{note}"

    def _proposta(self, tutte: bool) -> tuple[dict, dict] | None:
        """Ultima proposta in sospeso per questo mittente (anche scaduta se `tutte`), nelle serate da oggi in poi."""
        migliore = None
        for d in self.archivio.date(self.oggi):
            stato = self.archivio.carica(d)
            for p in stato["proposte_in_sospeso"]:
                if p["mittente"] != self.mittente:
                    continue
                if not tutte and datetime.fromisoformat(p["scade_il"]) < self.ora:
                    continue
                if migliore is None or p["creata_il"] > migliore[1]["creata_il"]:
                    migliore = (stato, p)
        return migliore

    def _togli_proposta(self, stato: dict, salva: bool = True) -> None:
        stato["proposte_in_sospeso"] = [p for p in stato["proposte_in_sospeso"] if p["mittente"] != self.mittente]
        if salva:
            self.archivio.salva(stato)

    def _interpreta_conferma(self, testo: str, opzioni: list[str]):
        """'21', '21:00', 'ok 20:15', 'la seconda', 'sì' (una sola opzione), 'no' -> orario | 'quale' | 'nessuna' | None."""
        t = normalizza(testo).strip(" .!?")
        if re.fullmatch(r"(no|nessuna|nessuno|lascia stare|lascia perdere|annulla)( grazie)?", t):
            return "nessuna"
        t2 = re.sub(r"\b(ok|okay|si|va bene|vada per|perfetto|allora|meglio|facciamo|prendo|confermo|grazie)\b", " ", t)
        t2 = re.sub(r"\b(la|le|alle|quella delle|quella|delle|ore)\b", " ", t2).strip(" ,.!")
        if not t2:
            return opzioni[0] if len(opzioni) == 1 and t else ("quale" if t else None)
        if t2 in ORDINALI:
            if re.fullmatch(r"\d", t2) and leggi_ora(t2) is not None and int(t2) > len(opzioni):
                pass
            elif ORDINALI[t2] < len(opzioni):
                return opzioni[ORDINALI[t2]]
        ora = leggi_ora(t2)
        if ora is None:
            return None
        o, _ = normalizza_orario(ora[0], ora[1], self.inizio, self.fine, self.sala.get("passo_orari_min", 15),
                                 self.cfg["servizio_serale"])
        if o is None:
            return None
        if o in opzioni:
            return o
        # un orario che non era tra le proposte: lo si prova come scelta (verrà ricontrollato)
        cand = [x for x in opzioni if x.startswith(o[:2])] if ":" not in t2 and "." not in t2 else []
        return cand[0] if len(cand) == 1 else o

    def _interpreta_scelta(self, testo: str, candidati: list[dict]) -> int | None:
        t = normalizza(testo).strip(" .!?")
        t = re.sub(r"\b(la|quella|delle|del|di|ok)\b", " ", t).strip()
        if t in ORDINALI and ORDINALI[t] < len(candidati):
            return ORDINALI[t]
        ora = leggi_ora(t)
        if ora:
            o, _ = normalizza_orario(ora[0], ora[1], self.inizio, self.fine, self.sala.get("passo_orari_min", 15),
                                     self.cfg["servizio_serale"])
            idx = [i for i, c in enumerate(candidati) if c["orario"] == o]
            if len(idx) == 1:
                return idx[0]
        d, _, capita = risolvi_data(testo, self.oggi)
        if capita and d:
            idx = [i for i, c in enumerate(candidati) if c["data"] == d.isoformat()]
            if len(idx) == 1:
                return idx[0]
        return None

    def registra_messaggio(self, testo, risposta, data_rif: date | None, origine: str, durata: float) -> None:
        voce = {"ricevuto_il": self.ora.isoformat(timespec="seconds"), "mittente": self.mittente, "testo": testo,
                "risposta": risposta, "lettura": origine, "durata_s": durata}
        if data_rif is not None:
            stato = self.archivio.carica(data_rif)
            stato["messaggi"].append(voce)
            self.archivio.salva(stato)
        else:
            mitt = self.archivio.mittenti()
            io = mitt.setdefault(self.mittente, {})
            io.setdefault("storico", []).append(voce)
            io["storico"] = io["storico"][-200:]
            self.archivio.salva_mittenti(mitt)


# --------------------------------------------------------------------------- piantina della serata

def piantina_serata(cartella_stato: str | Path, d: date, sala: dict | None = None, out: str | Path | None = None,
                    tempo_s: float | None = None) -> tuple[dict, Path, Path]:
    """Disposizione dei tavoli per le prenotazioni accettate di una serata (orari congelati), con il modello
    esistente. Scrive prenotazioni.json, soluzione.json e serata.html; il chiamante può lanciare verifica.py."""
    from .mappa import scrivi_html
    sala = sala if sala is not None else leggi_json(SALA_DEFAULT)
    stato = Archivio(cartella_stato).carica(d)
    pren = {"serata": f"{GIORNI[d.weekday()].capitalize()} {d:%d/%m/%Y}",
            "prenotazioni": [{"id": a["id"], "nome": a["nome"], "coperti": a["coperti"], "orario": a["orario"],
                              "prenotata_il": a["prenotata_il"][:16], **({"note": a["note"]} if a.get("note") else {})}
                             for a in stato["accettate"]]}
    ist = costruisci_istanza(sala, pren)
    disp = cfg_chat(sala)["disposizione"]
    voci = [_Voce(p, [(0, ist.a_passi(p.orario_min))], True) for p in ist.prenotazioni]
    worker, seed = _parametri(ist, None, None)
    mod = _costruisci(ist, voci, disp)
    stato_solver, piano, info = _risolvi_modello(mod, float(tempo_s or _cfg_solver(ist, "tempo_piantina_s", 300)),
                                                 worker, seed, False)
    if piano is None:
        raise RuntimeError(f"piantina non trovata ({stato_solver})")
    tavoli, assegnazioni, _ = _estrai(ist, mod, piano)
    comp = calcola_componenti(ist, tavoli, assegnazioni, [])
    sol = {"sala": sala.get("nome", ""), "serata": pren["serata"],
           "modalita": {"accettazione": "chat (orari congelati alla conferma)", "disposizione": disp},
           "solver": info, "obiettivo_componenti": comp, "tavoli": tavoli, "assegnazioni": assegnazioni,
           "non_sistemate": []}
    out = Path(out) if out else RADICE / "out" / "serate" / d.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    p_pren, p_sol = out / "prenotazioni.json", out / "soluzione.json"
    p_pren.write_text(json.dumps(pren, ensure_ascii=False, indent=1), encoding="utf-8")
    p_sol.write_text(json.dumps(sol, ensure_ascii=False, indent=1), encoding="utf-8")
    scrivi_html(sala, pren, sol, out / "serata.html")
    return sol, p_pren, p_sol
