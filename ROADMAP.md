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

## Prossimo step

- [ ] Riverificare le soglie del re-ranker con EmbeddingGemma 2 (`eval --rerank`) e decidere se resta opzionale
- [ ] Ampliare le domande di `eval` per rendere più solide le soglie (margine di circa 0.05 in `note`)
- [ ] Direzione "grande": servizio con API, utenti e collezioni separate, da collegare al social network wuxer (da definire)

## Secondari

- [ ] Costo cumulativo delle query
- [ ] Modalità interattiva (REPL) per non ricaricare il modello a ogni comando
- [ ] `sqlite-vec` per la ricerca vettoriale nel database (se il volume lo giustifica)
- [ ] Watcher sulla cartella indicizzata
- [ ] Cronologia conversazionale e streaming della risposta
- [ ] Multi-query
- [ ] Sync remoto
