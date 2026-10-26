"""Stato delle serate per la chat: un file per serata `AAAA-MM-GG.json` più `_mittenti.json` (bozze e scelte in
corso per mittente). Ogni scrittura è atomica: file temporaneo nella stessa cartella, fsync, poi `os.replace`."""
from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import date
from pathlib import Path


def _sostituisci(tmp: str, percorso: Path, attesa_max_s: float = 8.0) -> None:
    """`os.replace` con ritenti: su Windows l'antivirus apre per un attimo il file appena scritto (con la CPU
    piena anche per più di un secondo) e intanto la sostituzione fallisce con "accesso negato"."""
    fine = time.monotonic() + attesa_max_s
    pausa = 0.02
    while True:
        try:
            os.replace(tmp, percorso)
            return
        except PermissionError:
            if time.monotonic() >= fine:
                raise
            time.sleep(pausa)
            pausa = min(pausa * 2, 0.25)


def scrivi_json_atomico(percorso: Path, dati) -> None:
    """Scrive `dati` in `percorso` senza mai lasciare un file a metà: se qualcosa va storto resta il vecchio."""
    percorso = Path(percorso)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{percorso.name}.", suffix=".tmp", dir=percorso.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dati, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        _sostituisci(tmp, percorso)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def scrivi_testo_atomico(percorso: Path, testo: str) -> None:
    percorso = Path(percorso)
    fd, tmp = tempfile.mkstemp(prefix=f".{percorso.name}.", suffix=".tmp", dir=percorso.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(testo)
        _sostituisci(tmp, percorso)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def serata_vuota(d: date) -> dict:
    return {"data": d.isoformat(), "versione": 0, "accettate": [], "rifiuti": [], "annullate": [],
            "proposte_in_sospeso": [], "messaggi": [], "contatore": 0}


class Archivio:
    def __init__(self, cartella: str | Path):
        self.cartella = Path(cartella)

    def percorso(self, d: date) -> Path:
        return self.cartella / f"{d.isoformat()}.json"

    def carica(self, d: date) -> dict:
        p = self.percorso(d)
        if not p.exists():
            return serata_vuota(d)
        return json.loads(p.read_text(encoding="utf-8"))

    def salva(self, stato: dict) -> None:
        """Stato della serata più `AAAA-MM-GG.versione`: i processi di calcolo lo leggono per capire se il loro
        lavoro è superato (la versione cambia a ogni nuova, conferma, modifica o annullamento)."""
        d = date.fromisoformat(stato["data"])
        scrivi_json_atomico(self.percorso(d), stato)
        scrivi_testo_atomico(self.cartella / f"{d.isoformat()}.versione", str(int(stato.get("versione", 0))))

    def date(self, dal: date | None = None, al: date | None = None) -> list[date]:
        out = []
        for p in sorted(self.cartella.glob("????-??-??.json")):
            try:
                d = date.fromisoformat(p.stem)
            except ValueError:
                continue
            if (dal is None or d >= dal) and (al is None or d <= al):
                out.append(d)
        return out

    def mittenti(self) -> dict:
        p = self.cartella / "_mittenti.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def salva_mittenti(self, dati: dict) -> None:
        scrivi_json_atomico(self.cartella / "_mittenti.json", dati)
