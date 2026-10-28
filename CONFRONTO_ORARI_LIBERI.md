# Prototipo di confronto a orari liberi

Questo confronto è isolato: non usa né modifica le prenotazioni della chat. La chat e l'agente
esistenti continuano a usare il vecchio modello a turni; **non usare questo prototipo per accettare
prenotazioni reali**. L'integrazione con chat, proposte, stato, mappa e verificatore esistenti resta da fare.

La piantina predefinita è `olimpo/piantina.html`. Il servizio ipotizzato è 19:00–24:00, come nella
configurazione esistente. Gli arrivi possono essere a qualsiasi minuto; il pasto deve finire entro
la chiusura. Durata standard: 90 minuti per tutti; riapparecchiatura zero.
La durata è in `ristorante/orari_liberi.py`. Le prenotazioni già accettate mantengono l'orario,
ma il tavolo può cambiare nel piano successivo.

Il prototipo assume valide le posizioni dei tavoli della piantina; **non controlla geometricamente
passaggi, sedie o ostacoli**. Parti di un blocco che condividono quadrati non possono essere occupate
contemporaneamente. Il lungo ospita un gruppo fino a 20 o due gruppi fino a 8 ciascuno. Non si
accostano tavoli diversi. L'agente propone un piano completo; un controllo separato lo verifica
prima di accettarlo. Se l'agente dice che non entra, il solver tenta di dimostrare o smentire il
rifiuto; un timeout non è una prova di impossibilità.

La funzione `valuta_con_uscita_anticipata` verifica prima i 90 minuti, poi cerca una permanenza
più breve e restituisce una proposta con l'ora di uscita. Non registra nulla: l'interfaccia dovrà
ottenere una conferma esplicita e ripetere il calcolo sullo stato aggiornato prima di registrare,
conservando la durata concordata. Non è ancora integrata nella chat né nel confronto CLI, che
continuano a valutare esclusivamente richieste da 90 minuti. Non è stata definita una permanenza
minima: la funzione può proporre qualsiasi durata positiva.

Installare le dipendenze dal README, poi eseguire dalla radice:

```sh
python confronto_orari_liberi.py --metodo python --prenotazioni dati/olimpo_venerdi.json
python confronto_orari_liberi.py --metodo entrambi --modello NOME_MODELLO --prenotazioni dati/olimpo_venerdi.json
```

La seconda prova richiede un modello Anthropic disponibile e `ANTHROPIC_API_KEY` nell'ambiente.
Non inserire la chiave nei file o nei comandi. Le richieste inviate all'API contengono ID, orari,
coperti e unità della sala, senza nomi. Gli esiti di ciascun metodo hanno uno stato separato e possono
divergere; il confronto dei rifiuti usa le prenotazioni accettate da quel metodo fino a quel punto.
`secondi_decisione` misura la chiamata all'agente; `secondi` include anche la verifica del rifiuto.
Il modello potrebbe non restituire JSON valido, rifiutare, andare in errore o non trovare una soluzione:
questi casi sono registrati e non vengono presentati come prenotazioni accettate.

Test: `python -m pytest -q tests/test_orari_liberi.py`.
