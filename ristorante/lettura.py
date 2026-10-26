"""Lettura dei messaggi del proprietario: formato compatto deterministico, LLM (Claude) con output strutturato,
controlli del codice su date e orari.

Il formato compatto si legge senza LLM: "Rossi 4 sab 20:30 [note]", "Rossi 4 31/10 20:30 seggiolone",
più "annulla Rossi sab" e "riepilogo sab"; nelle sale a turni anche "Rossi 4 sab 1t" o "Rossi 4 sab secondo turno".
Tutto il resto passa all'LLM, se c'è la chiave.
"""
from __future__ import annotations

import os
import re
import ssl
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

INTENTI = ("nuova", "modifica", "annulla", "conferma_proposta", "disponibilita", "riepilogo", "non_capito")

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
GIORNI_BREVI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
_ALIAS_GIORNI = {
    "lun": 0, "lunedi": 0, "lunedì": 0, "mar": 1, "martedi": 1, "martedì": 1, "mer": 2, "mercoledi": 2,
    "mercoledì": 2, "gio": 3, "giovedi": 3, "giovedì": 3, "ven": 4, "venerdi": 4, "venerdì": 4,
    "sab": 5, "sabato": 5, "dom": 6, "domenica": 6,
}
_MESI = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7,
         "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
         "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9, "ott": 10,
         "nov": 11, "dic": 12}

FORMATO_COMPATTO = "Rossi 4 sab 20:30 [note]  (oppure: Rossi 4 31/10 20:30)"


# --------------------------------------------------------------------------- schema dell'LLM

class LetturaLLM(BaseModel):
    """Campi estratti dal messaggio. Nulla va inventato: ciò che non c'è resta null e finisce in campi_mancanti."""
    intento: Literal["nuova", "modifica", "annulla", "conferma_proposta", "disponibilita", "riepilogo", "non_capito"]
    nome: Optional[str] = Field(None, description="cognome o nome della prenotazione; per modifica il nuovo nome, se cambia")
    coperti: Optional[int] = Field(None, description="numero di persone (per modifica: il nuovo numero)")
    data: Optional[str] = Field(None, description="data della serata in formato AAAA-MM-GG")
    orario: Optional[str] = Field(None, description="orario HH:MM, sera: 'alle 8' = 20:00 (per modifica: il nuovo orario)")
    note: Optional[str] = Field(None, description="richieste particolari: seggiolone, compleanno, allergie...")
    riferimento_nome: Optional[str] = Field(None, description="modifica/annulla: nome della prenotazione esistente")
    riferimento_data: Optional[str] = Field(None, description="modifica/annulla: data AAAA-MM-GG della prenotazione esistente, se detta")
    scelta: Optional[str] = Field(None, description="conferma_proposta: orario scelto HH:MM oppure posizione 1/2/3")
    turno: Optional[int] = Field(None, description="solo se il messaggio chiede un turno ('primo turno', '1t', "
                                                   "'al secondo turno'): 1 = primo, 2 = secondo; altrimenti null")
    campi_mancanti: list[str] = Field(default_factory=list, description="campi necessari non presenti nel messaggio")
    ambiguita: list[str] = Field(default_factory=list, description="dubbi di lettura, in italiano")
    testo_data: Optional[str] = Field(None, description="le parole della data come scritte: 'sabato', 'domani sera', '31/10'")


# --------------------------------------------------------------------------- lettura normalizzata

@dataclass
class Lettura:
    intento: str
    origine: str                         # "compatto" | "llm" | "conferma" | "completamento"
    nome: str | None = None
    coperti: int | None = None
    data: date | None = None
    orario: str | None = None            # HH:MM sulla griglia
    note: str | None = None
    riferimento_nome: str | None = None
    riferimento_data: date | None = None
    scelta: str | None = None
    testo_data: str | None = None
    turno: int | None = None             # turno chiesto esplicitamente (1 = primo), sale a turni
    orario_chiesto: str | None = None    # sale a turni: orario scritto, prima di metterlo nel turno più vicino
    turno_lontano: int | None = None     # sale a turni: indice del turno più vicino se l'orario è lontano da tutti
    campi_mancanti: list[str] = field(default_factory=list)
    ambiguita: list[str] = field(default_factory=list)
    domande: list[str] = field(default_factory=list)   # da chiedere al proprietario prima di agire
    avvisi: list[str] = field(default_factory=list)    # da dire nella risposta (es. arrotondamenti)
    data_llm: str | None = None          # data proposta dall'LLM, se diversa da quella ricalcolata


def normalizza(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def nome_proprio(s: str) -> str:
    return " ".join(p[:1].upper() + p[1:] for p in s.strip().split())


def etichetta_data(d: date) -> str:
    return f"{GIORNI_BREVI[d.weekday()]} {d:%d/%m}"


# --------------------------------------------------------------------------- date

def risolvi_data(testo: str | None, oggi: date) -> tuple[date | None, list[str], bool]:
    """Risolve le espressioni di data più comuni. Restituisce (data, domande, capita): `capita` = l'espressione è
    stata riconosciuta (anche se genera una domanda). Il giorno della settimana citato insieme a una data
    deve coincidere; "sabato" scritto di sabato è ambiguo (stasera o sabato prossimo?)."""
    if not testo:
        return None, [], False
    t = normalizza(testo)
    domande: list[str] = []
    if re.search(r"\b(stasera|oggi)\b", t):
        return oggi, domande, True
    if re.search(r"\bdopodomani\b", t):
        return oggi + timedelta(days=2), domande, True
    if re.search(r"\bdomani\b", t):
        return oggi + timedelta(days=1), domande, True
    giorno_citato = None
    for parola in re.findall(r"[a-z]+", t):
        if parola in _ALIAS_GIORNI and not (parola == "mar" and re.search(r"\bmar(zo)?\b\s*\d", t)):
            giorno_citato = _ALIAS_GIORNI[parola]
    data_esplicita = None
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", t)
    if m:
        g, me, a = int(m.group(1)), int(m.group(2)), m.group(3)
        anno = (int(a) + 2000 if len(a) == 2 else int(a)) if a else oggi.year
        try:
            data_esplicita = date(anno, me, g)
        except ValueError:
            return None, [f"la data {m.group(0)} non esiste"], True
        if not a and data_esplicita < oggi:
            try:
                data_esplicita = date(anno + 1, me, g)
            except ValueError:
                pass
    else:
        m = re.search(r"\b(\d{1,2})\s+(" + "|".join(sorted(_MESI, key=len, reverse=True)) + r")\b", t)
        if m:
            try:
                data_esplicita = date(oggi.year, _MESI[m.group(2)], int(m.group(1)))
            except ValueError:
                return None, [f"la data {m.group(0)} non esiste"], True
            if data_esplicita < oggi:
                data_esplicita = data_esplicita.replace(year=oggi.year + 1)
    if data_esplicita is not None:
        if giorno_citato is not None and data_esplicita.weekday() != giorno_citato:
            domande.append(f"il {data_esplicita:%d/%m} è {GIORNI[data_esplicita.weekday()]}, non "
                           f"{GIORNI[giorno_citato]}: quale dei due?")
        return data_esplicita, domande, True
    if giorno_citato is not None:
        delta = (giorno_citato - oggi.weekday()) % 7
        if "prossim" in t:
            delta = delta or 7
        elif delta == 0:
            domande.append(f"{GIORNI[giorno_citato]}: stasera o {GIORNI[giorno_citato]} prossimo?")
        return oggi + timedelta(days=delta), domande, True
    return None, [], False


# --------------------------------------------------------------------------- orari

def leggi_ora(testo: str) -> tuple[int, int] | None:
    """'20:30', '20.30', '20', '8', '8 e mezza', '8 e un quarto', '9 meno un quarto' -> (ore, minuti)."""
    t = normalizza(testo)
    m = re.fullmatch(r"(?:alle\s+|verso\s+le\s+|per\s+le\s+|ore\s+)?(\d{1,2})(?:[:.](\d{2}))?"
                     r"(?:\s+e\s+(mezza|mezzo|un\s+quarto|tre\s+quarti))?(?:\s+meno\s+un\s+quarto)?", t)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    extra = (m.group(3) or "").replace(" ", "")
    mi += {"mezza": 30, "mezzo": 30, "unquarto": 15, "trequarti": 45}.get(extra, 0)
    if "meno un quarto" in t:
        h, mi = (h - 1) % 24, 45
    if h > 24 or mi > 59:
        return None
    return h, mi


def normalizza_orario(h: int, mi: int, inizio_min: int, fine_min: int, passo: int = 15,
                      serale: bool = True) -> tuple[str | None, list[str]]:
    """Regole del servizio serale ("alle 8" = 20:00) e arrotondamento al passo, con avvisi per la risposta."""
    avvisi = []
    tot = h * 60 + mi
    if serale and tot < inizio_min and inizio_min <= (h + 12) * 60 + mi <= fine_min:
        tot = (h + 12) * 60 + mi
    resto = tot % passo
    if resto:
        arrot = tot - resto + (passo if resto * 2 >= passo else 0)
        avvisi.append(f"orario arrotondato al quarto d'ora: {tot // 60:02d}:{tot % 60:02d} → {arrot // 60:02d}:{arrot % 60:02d}")
        tot = arrot
    if not (inizio_min <= tot <= fine_min):
        return None, [f"le {tot // 60:02d}:{tot % 60:02d} sono fuori dal servizio ({inizio_min // 60:02d}:{inizio_min % 60:02d}"
                      f"–{fine_min // 60:02d}:{fine_min % 60:02d})"]
    return f"{tot // 60:02d}:{tot % 60:02d}", avvisi


# --------------------------------------------------------------------------- turni

_ORDINALI_TURNO = {"primo": 1, "secondo": 2, "terzo": 3, "quarto": 4, "1o": 1, "2o": 2, "3o": 3, "1°": 1, "2°": 2,
                   "3°": 3}
_RE_TURNO = r"(?:[1-9]\s*t(?:urno)?|[1-9]°\s*turno|(?:primo|secondo|terzo|quarto)\s+turno|turno\s+[1-9])"


def leggi_turno(testo: str, nudo: bool = False) -> int | None:
    """'1t', '2 t', '1° turno', 'primo turno', 'turno 2' -> 1, 2 (numero del turno, da 1). Con `nudo` anche le
    risposte brevi a una proposta: 'il secondo', 'primo'."""
    t = normalizza(testo).strip(" .!?")
    t = re.sub(r"\b(il|al|nel|ok|si|va bene|allora|meglio)\b", " ", t).strip(" ,")
    m = re.fullmatch(r"([1-9])\s*t(?:urno)?|([1-9])°\s*turno|turno\s+([1-9])", t)
    if m:
        return int(m.group(1) or m.group(2) or m.group(3))
    m = re.fullmatch(r"(primo|secondo|terzo|quarto|1o|2o|3o)\s+turno" + (r"|(primo|secondo|terzo|quarto)" if nudo else ""), t)
    if m:
        return _ORDINALI_TURNO[m.group(1) or m.group(2)]
    return None


# --------------------------------------------------------------------------- formato compatto

_RE_GIORNO = (r"(?:oggi|stasera|domani|dopodomani|lun|mar|mer|gio|ven|sab|dom|luned[iì]|marted[iì]|mercoled[iì]|"
              r"gioved[iì]|venerd[iì]|sabato|domenica|\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?)")
_RE_COMPATTO = re.compile(
    r"^\s*(?P<nome>[^\W\d_][\w'’ .-]*?)\s+(?P<coperti>\d{1,2})\s+(?P<giorno>" + _RE_GIORNO + r")\s+"
    r"(?:(?P<turno>" + _RE_TURNO + r")|(?P<ora>\d{1,2}(?:[:.]\d{2})?))(?:\s+\[?(?P<note>[^\]]*?)\]?)?\s*$", re.IGNORECASE)
_RE_ANNULLA = re.compile(r"^\s*annulla\s+(?P<nome>[^\W\d_][\w'’ .-]*?)\s+(?P<giorno>" + _RE_GIORNO + r")\s*$", re.IGNORECASE)
_RE_RIEPILOGO = re.compile(r"^\s*riepilogo(?:\s+(?P<giorno>" + _RE_GIORNO + r"))?\s*$", re.IGNORECASE)


_PAROLE_FUNZIONE = {"i", "il", "la", "le", "lo", "gli", "l", "di", "del", "della", "dei", "degli", "per", "a", "da",
                    "in", "con", "su", "e", "che", "tutti", "tutto"}


def _nome_plausibile(nome: str) -> bool:
    """Un nome del formato compatto non contiene parole funzione scritte in minuscolo ('i Rossi di' non è un nome,
    'Di Maio' e 'De Luca' sì)."""
    return all(not (p.lower() in _PAROLE_FUNZIONE and p.islower()) for p in re.split(r"[\s']+", nome.strip()) if p)


def leggi_compatto(testo: str) -> Lettura | None:
    """Messaggi che corrispondono PER INTERO al formato compatto; altrimenti None (si passa all'LLM)."""
    m = _RE_COMPATTO.match(testo)
    if m and not _nome_plausibile(m.group("nome")):
        m = None
    if m:
        note = (m.group("note") or "").strip() or None
        if m.group("turno"):
            return Lettura("nuova", "compatto", nome=nome_proprio(m.group("nome")), coperti=int(m.group("coperti")),
                           turno=leggi_turno(m.group("turno")), note=note, testo_data=m.group("giorno"))
        ora = leggi_ora(m.group("ora"))
        if ora is None:
            return None
        return Lettura("nuova", "compatto", nome=nome_proprio(m.group("nome")), coperti=int(m.group("coperti")),
                       orario=f"{ora[0]:02d}:{ora[1]:02d}", note=note, testo_data=m.group("giorno"))
    m = _RE_ANNULLA.match(testo)
    if m and _nome_plausibile(m.group("nome")):
        return Lettura("annulla", "compatto", riferimento_nome=nome_proprio(m.group("nome")), testo_data=m.group("giorno"))
    m = _RE_RIEPILOGO.match(testo)
    if m:
        return Lettura("riepilogo", "compatto", testo_data=m.group("giorno") or "stasera")
    return None


# --------------------------------------------------------------------------- LLM (Claude)

class LLMNonDisponibile(Exception):
    """La lettura via LLM non è possibile (chiave assente, rete, rifiuto, risposta incompleta)."""


def trova_chiave() -> str | None:
    """ANTHROPIC_API_KEY del processo; altrimenti dalle variabili utente di Windows (HKCU\\Environment), letta
    dentro questo processo. La chiave non viene mai stampata né scritta."""
    chiave = os.environ.get("ANTHROPIC_API_KEY")
    if chiave:
        return chiave
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            valore, _ = winreg.QueryValueEx(k, "ANTHROPIC_API_KEY")
            return str(valore) or None
    except (ImportError, OSError):
        return None


def _errore_ssl(exc: BaseException) -> bool:
    e: BaseException | None = exc
    while e is not None:
        if isinstance(e, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
            return True
        e = e.__cause__ or e.__context__
    return False


def prompt_sistema(oggi: datetime, inizio: str, fine: str) -> str:
    return (
        "Leggi i messaggi che il proprietario di un ristorante scrive in chat per gestire le prenotazioni della "
        "cena ed estrai i campi richiesti dallo schema. Non inventare nulla: un campo che il messaggio non dice "
        "resta null ed è elencato in campi_mancanti (per una nuova prenotazione servono nome, coperti, data e "
        "orario). Copia in testo_data le parole della data così come sono scritte.\n"
        f"Oggi è {GIORNI[oggi.weekday()]} {oggi:%d/%m/%Y}, il messaggio è arrivato alle {oggi:%H:%M}. "
        f"Il servizio è solo serale, dalle {inizio} alle {fine}: 'alle 8' significa 20:00, 'alle 9' 21:00.\n"
        "Intenti: nuova (una prenotazione nuova); modifica (cambia coperti, orario o data di una prenotazione "
        "esistente: riferimento_nome e, se detta, riferimento_data la identificano, nome/coperti/orario/data "
        "contengono i NUOVI valori); annulla (riferimento_nome, riferimento_data); conferma_proposta (risponde a "
        "una proposta di orario: scelta = orario HH:MM o posizione 1/2/3); disponibilita (chiede se c'è posto, "
        "senza prenotare); riepilogo (chiede chi è prenotato in una serata); non_capito (tutto ciò che non è una "
        "di queste cose, per esempio un promemoria). Le ambiguità vanno in ambiguita, in italiano."
    )


class LettoreAnthropic:
    """Lettura con Claude tramite l'SDK ufficiale `anthropic` e output strutturato (`messages.parse`)."""

    def __init__(self, modello: str = "claude-haiku-5-5", effort: str = "low", max_tokens: int = 2048,
                 client=None, timeout_s: float = 30.0):
        self.modello, self.effort, self.max_tokens, self.timeout_s = modello, effort, max_tokens, timeout_s
        self._client = client
        self._truststore = False
        self.ultimo_uso = None

    @property
    def disponibile(self) -> bool:
        return self._client is not None or trova_chiave() is not None

    def _crea_client(self):
        if self._client is None:
            chiave = trova_chiave()
            if not chiave:
                raise LLMNonDisponibile("manca la chiave ANTHROPIC_API_KEY")
            import anthropic
            self._client = anthropic.Anthropic(api_key=chiave, timeout=self.timeout_s, max_retries=2)
        return self._client

    def leggi(self, testo: str, ricevuto_il: datetime, inizio: str, fine: str, contesto: str = "") -> LetturaLLM:
        import anthropic
        client = self._crea_client()
        contenuto = testo if not contesto else f"{contesto}\n\nMessaggio del proprietario:\n{testo}"
        richiesta = dict(model=self.modello, max_tokens=self.max_tokens, output_config={"effort": self.effort},
                         system=prompt_sistema(ricevuto_il, inizio, fine),
                         messages=[{"role": "user", "content": contenuto}], output_format=LetturaLLM)
        for tentativo in range(2):
            try:
                risposta = client.messages.parse(**richiesta)
                break
            except ValidationError as e:     # JSON non conforme allo schema
                raise LLMNonDisponibile("risposta non conforme allo schema") from e
            except anthropic.BadRequestError as e:
                raise LLMNonDisponibile(f"richiesta non valida ({e.status_code})") from e
            except anthropic.AuthenticationError as e:
                raise LLMNonDisponibile("chiave non valida") from e
            except anthropic.PermissionDeniedError as e:
                raise LLMNonDisponibile("chiave senza permessi per il modello") from e
            except anthropic.NotFoundError as e:
                raise LLMNonDisponibile(f"modello {self.modello} non trovato") from e
            except anthropic.RateLimitError as e:
                raise LLMNonDisponibile("troppe richieste, riprova tra poco") from e
            except anthropic.APIStatusError as e:
                raise LLMNonDisponibile(f"errore del servizio ({e.status_code})") from e
            except anthropic.APITimeoutError as e:
                raise LLMNonDisponibile("il servizio non ha risposto in tempo") from e
            except anthropic.APIConnectionError as e:
                # proxy con ispezione TLS: si passa allo store certificati di Windows (truststore), mai senza verifica
                if tentativo == 0 and _errore_ssl(e) and not self._truststore:
                    import truststore
                    truststore.inject_into_ssl()
                    self._truststore = True
                    self._client = None
                    client = self._crea_client()
                    continue
                raise LLMNonDisponibile("errore di rete") from e
            except anthropic.AnthropicError as e:
                raise LLMNonDisponibile(f"errore dell'SDK: {type(e).__name__}") from e
        if risposta.stop_reason == "refusal":
            raise LLMNonDisponibile("il modello ha rifiutato di leggere il messaggio")
        if risposta.stop_reason == "max_tokens":
            raise LLMNonDisponibile("risposta incompleta (limite di token)")
        self.ultimo_uso = getattr(risposta, "usage", None)
        lettura = risposta.parsed_output
        if lettura is None:
            raise LLMNonDisponibile("risposta senza campi leggibili")
        return lettura
