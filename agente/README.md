# Agente di sala

`sala-olimpo` è un agente di Claude Code che aiuta a gestire le prenotazioni e la sala del ristorante Olimpo
partendo dai messaggi del proprietario. Non decide lui chi entra e come si dispongono i tavoli: traduce le richieste nei
comandi del motore CP-SAT del repository (`chat.py`, `prova.py`, `esegui.py`), spiega le risposte e segnala le regole di
buonsenso non rispettate.

- **Regole:** stanno in [`regole.md`](regole.md), l'unica fonte. L'agente le legge all'avvio; per cambiarle si modifica
  solo quel file.
- **Definizione dell'agente:** [`.claude/agents/sala-olimpo.md`](../.claude/agents/sala-olimpo.md).
- **Come si usa:** installare il progetto (vedi il [README](../README.md)), aprire la cartella in Claude Code e chiamare
  l'agente, ad esempio "usa sala-olimpo: Rossi 4 sabato alle 20:30". Per leggere i messaggi scritti liberamente serve la
  chiave `ANTHROPIC_API_KEY` (opzionale); senza chiave il motore capisce solo il formato compatto (`Rossi 4 sab 20:30`).
