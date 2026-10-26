import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

_SALA_ESEMPIO = json.loads((RADICE / "dati" / "sala_esempio.json").read_text(encoding="utf-8"))


def sala_esempio() -> dict:
    return copy.deepcopy(_SALA_ESEMPIO)


def sala_piccola(larghezza=600, altezza=400, moduli=5, max_blocco=5, tondi=0, durate=None,
                 riapp=15, tempo=10, ostacoli=None, corsie=None, proposta="mai", proposta_max=120) -> dict:
    """Sala di prova senza ostacoli (o con quelli passati), stessi pesi e regole della sala di esempio.
    Di default senza proposte di orario ("mai"): i test delle proposte lo impostano esplicitamente."""
    s = sala_esempio()
    s["cliente_accetta_proposta"] = proposta
    s["proposta_max_distanza_min"] = proposta_max
    s.update(nome="Sala di prova", larghezza_cm=larghezza, altezza_cm=altezza,
             ostacoli=ostacoli or [], corsie=corsie or [], riapparecchiatura_min=riapp)
    s["inventario"]["moduli"]["quantita"] = moduli
    s["inventario"]["moduli"]["max_per_blocco"] = max_blocco
    s["inventario"]["tondi"]["quantita"] = tondi
    if durate is not None:
        s["durate"] = durate
    s["solver"]["tempo_limite_s"] = tempo
    return s


def serata(*prenotazioni) -> dict:
    """prenotazioni: tuple (id, nome, coperti, "HH:MM"[, note])."""
    out = []
    for p in prenotazioni:
        d = {"id": p[0], "nome": p[1], "coperti": p[2], "orario": p[3]}
        if len(p) > 4:
            d["note"] = p[4]
        out.append(d)
    return {"serata": "prova", "prenotazioni": out}


@pytest.fixture(scope="session")
def verificatore():
    """Il verificatore caricato dal file, come modulo a sé (non fa parte del pacchetto `ristorante`)."""
    spec = importlib.util.spec_from_file_location("verifica", RADICE / "verifica.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verifica"] = mod      # le dataclass del modulo lo cercano in sys.modules
    spec.loader.exec_module(mod)
    return mod


def esiti_per_nome(esiti) -> dict:
    return {e.nome: e for e in esiti}
