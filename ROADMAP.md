# Roadmap

Stato del progetto e prossimi passi. Per cosa fa oggi il sistema e come si usa vedi il [README](README.md).

## Completato

- [x] Chunking per parole e per frasi
- [x] Storage SQLite e retrieval con soglia minima
- [x] Generazione con elenco delle fonti
- [x] Supporto PDF
- [x] Embedding multi-modello per categoria
- [x] Tre modalità di risposta (`strict`, `standard`, `full`)
- [x] Log strutturato delle query e salvataggio delle risposte
- [x] Flag `--show-chunks` per vedere testo e punteggio dei chunk recuperati
- [x] Calibrazione su domande pertinenti e fuori tema per ogni categoria
- [x] `min_sim` di default legato alla categoria, con `--min-sim` come override
- [x] Temperatura legata alla modalità, con `--temperature` come override
- [x] Comando `eval` per calibrare le soglie su domande etichettate
- [x] Re-ranking opzionale con cross-encoder (`--rerank`), con soglie per categoria calibrate con `eval --rerank`
- [x] EmbeddingGemma 2 al posto di mpnet ed e5, con colonna `category` nello storage e soglie ricalibrate
- [x] Soglie del re-ranker riverificate con EmbeddingGemma 2 (`note` 0.06, `programma` 0.03)
- [x] `sqlite-vec` per la ricerca vettoriale nel database (tabella `chunk_vectors` partizionata per categoria) con punteggi e soglie invariati
- [x] `service.py` e `consts.py`: la riga di comando e il sito usano lo stesso codice, costanti e variabili d'ambiente in un solo file
- [x] Interfaccia web (FastAPI e pagina statica) con le schede Chiedi, Indicizza e Valuta e accesso con password
- [x] Modelli caricati una sola volta all'avvio del sito con avviso e pulsanti disattivati finché non sono pronti
- [x] Risposta in markdown, statistiche (token e tempo) e chunk recuperati nella pagina, barre di avanzamento per indicizzazione e valutazione
- [x] Valuta dal sito: prova di una domanda con coseno e re-ranking affiancati, salvataggio in `eval/questions.json` e valutazione completa per categoria
- [x] Controlli sui file caricati (nome, contenuto, dimensione e numero)

## Prossimo step

- [ ] Decidere se il re-ranking resta opzionale (utile in `note`, poco in `programma`), confrontando coseno e re-ranking dalla scheda Valuta
- [ ] Ampliare le domande di `eval`, anche dalla scheda Valuta, per rendere più solide le soglie (margine di circa 0.05 in `note`)
- [ ] Direzione "grande": servizio con API, utenti e collezioni separate, da collegare al social network wuxer (da definire)

## Secondari

- [ ] Eliminare un documento indicizzato dalla scheda Indicizza
- [ ] Test automatici per `service.py` e per le rotte del sito
- [ ] Costo cumulativo delle query
- [ ] Modalità interattiva (REPL) per non ricaricare il modello a ogni comando
- [ ] Watcher sulla cartella indicizzata
- [ ] Cronologia conversazionale e streaming della risposta
- [ ] Multi-query
- [ ] Sync remoto
