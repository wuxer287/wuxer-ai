# Personal AI Knowledge

Sistema RAG (Retrieval-Augmented Generation) per indicizzare note personali e documenti e interrogarli in linguaggio naturale. L'indicizzazione e la ricerca semantica girano in locale; la risposta finale viene generata da un modello linguistico via API (attualmente DeepSeek), a cui vengono passati solo i frammenti di testo recuperati per quella domanda.

## Indice

- [Personal AI Knowledge](#personal-ai-knowledge)
  - [Indice](#indice)
  - [Caratteristiche](#caratteristiche)
  - [Come funziona](#come-funziona)
  - [Requisiti](#requisiti)
  - [Installazione](#installazione)
  - [Configurazione](#configurazione)
  - [Utilizzo](#utilizzo)
    - [Indicizzare documenti](#indicizzare-documenti)
    - [Fare domande](#fare-domande)
    - [Modalità di risposta](#modalità-di-risposta)
    - [Output](#output)
    - [Valutare le soglie](#valutare-le-soglie)
  - [Struttura del progetto](#struttura-del-progetto)
  - [Dettagli tecnici](#dettagli-tecnici)
    - [Chunking](#chunking)
    - [Embedding per categoria](#embedding-per-categoria)
    - [Retrieval](#retrieval)
    - [Re-ranking](#re-ranking)
    - [Calibrazione della soglia](#calibrazione-della-soglia)
    - [Generazione](#generazione)
    - [Log](#log)
  - [Privacy](#privacy)
  - [Limiti noti](#limiti-noti)
  - [Roadmap](#roadmap)

## Caratteristiche

- Indicizzazione di file **Markdown (.md)** e **PDF (.pdf)**
- Chunking per frasi (non spezza le frasi a metà) con overlap configurabile, oppure per numero fisso di parole
- Embedding multilingua locale con **EmbeddingGemma 2** e **categorie di contenuto** (`note`, `programma`) con raccolte e soglie separate
- Storage locale su **SQLite**
- Ricerca semantica per similarità coseno con **soglia minima calibrata per categoria** (modificabile da riga di comando)
- Opzione `--show-chunks` per vedere i chunk recuperati e i loro punteggi
- **Re-ranking opzionale** (`--rerank`) con un cross-encoder multilingua, per filtrare meglio i risultati fuori tema
- **Tre modalità di risposta** (`strict`, `standard`, `full`) che regolano quanto il modello può uscire dalle fonti indicizzate
- Elenco delle fonti consultate per ogni risposta
- Log strutturato di ogni query (modalità, fonti, token, tempi) e risposta salvata su file di testo

## Come funziona

**Indicizzazione** (`index`):

```
File (.md/.pdf) → lettura → chunking → embedding → SQLite
```

**Interrogazione** (`query`):

```
Domanda → embedding → ricerca per similarità (top-k, soglia) → LLM → risposta + fonti + log
```

## Requisiti

- Python 3.12+
- Un account DeepSeek con API key, o un altro provider con API compatibile OpenAI (da adattare in `generation.py`)
- Una **GPU è consigliata per l'indicizzazione**: su una GPU T4 (Google Colab) EmbeddingGemma 2 indicizza circa 140 chunk di `note` in 3,5 secondi e circa 410 chunk di `programma` in 19 secondi. Il re-ranking opzionale (`--rerank`) è più lento senza GPU.

Dipendenze Python principali: `sentence-transformers`, `numpy`, `pypdf`, `openai`, `python-dotenv`.

## Installazione

```bash
git clone https://github.com/wuxer287/wuxer-ai.git
cd wuxer-ai

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Configurazione

Copia `.env.example` in `.env` e compila i valori:

```
DEEPSEEK_API_KEY=la-tua-api-key
DEEPSEEK_MODEL=deepseek-flash
```

`DEEPSEEK_MODEL` è opzionale (il default nel codice è lo stesso valore di `.env.example`).

## Utilizzo

### Indicizzare documenti

```bash
python src/cli.py index <cartella> [opzioni]
```

| Opzione | Default | Descrizione |
|---|---|---|
| `folder` | (obbligatorio) | Cartella con i file `.md` e/o `.pdf` da indicizzare (non ricorsivo) |
| `--category` | `note` | Categoria del contenuto: raccolta separata, con le proprie soglie |
| `--strategy` | `sentence` | `sentence`: raggruppa frasi intere; `word`: taglia ogni N parole |
| `--dimension` | `40` | Tetto di parole per chunk (vedi [Chunking](#chunking)) |
| `--overlap` | `1` | Sovrapposizione tra chunk: frasi con `sentence`, parole con `word` |

Esempio:

```bash
python src/cli.py index ./documenti/programma --category programma --dimension 150 --overlap 1
```

Rilanciare `index` su una cartella già indicizzata è sicuro: i chunk di ogni file vengono cancellati e ricreati, senza duplicati.

### Fare domande

```bash
python src/cli.py query "<domanda>" [opzioni]
```

| Opzione | Default | Descrizione |
|---|---|---|
| `text` | (obbligatorio) | La domanda |
| `--category` | `note` | Categoria su cui cercare, la stessa usata in indicizzazione |
| `--top-k` | `5` | Numero massimo di chunk passati al modello |
| `--min-sim` | per categoria (`note` 0.735, `programma` 0.65) | Soglia minima di similarità: se indicata sostituisce quella della categoria (vedi [Calibrazione](#calibrazione-della-soglia)) |
| `--rerank` | disattivato | Riordina i candidati con il cross-encoder `BAAI/bge-reranker-v2-m3` e scarta quelli sotto `--rerank-min`; con questa opzione `--min-sim` è ignorato (vedi [Re-ranking](#re-ranking)) |
| `--rerank-min` | per categoria (`note` 0.06, `programma` 0.03) | Soglia (0-1) sul punteggio del re-ranker. Non è confrontabile con `--min-sim` |
| `--pool` | `20` | Con `--rerank`: numero di candidati presi dalla ricerca e passati al re-ranker |
| `--mode` | `strict` | Modalità di risposta (vedi sotto) |
| `--show-chunks` | disattivato | Stampa i chunk recuperati con testo, punteggio e fonte prima della risposta |
| `--temperature` | per modalità (`strict` 0.0, `standard` 0.3, `full` 0.6) | Temperatura di generazione: più bassa = risposte più stabili. Se indicata sostituisce quella della modalità |

Esempio:

```bash
python src/cli.py query "Cosa propone il programma sul lavoro?" --category programma --top-k 7 --mode strict
```

### Modalità di risposta

| Modalità | Comportamento | Quando usarla |
|---|---|---|
| `strict` | Risponde solo con le informazioni recuperate. Se non bastano, lo dice. Se nessun chunk supera la soglia, **non chiama nemmeno il modello** | Quando serve fedeltà alla fonte, per esempio riportare cosa dice un documento |
| `standard` | Parte dalle fonti, può integrare con conoscenza generale ma deve **segnalarlo sempre** (es. "Per contesto generale, ...") | Approfondire mantenendo chiaro cosa viene dalla fonte |
| `full` | Usa le fonti come base preferenziale e integra liberamente, senza obbligo di distinguere | Spiegazioni e note personali, **sconsigliata** per riportare fedelmente testi di altri |

Con `standard` e `full`, se la ricerca non trova chunk sopra soglia il modello viene comunque interrogato, senza contesto: `FONTI CONSULTATE` risulterà `[nessuna]`.

### Output

Ogni risposta mostra il testo generato, le fonti consultate e il consumo di token (input, cache, output, reasoning, totale).

### Valutare le soglie

```bash
python src/cli.py eval eval/questions.json [--top-k 5] [--verbose] [--rerank] [--pool 20] [--rerank-min 0.5]
```

Non chiama l'LLM: fa solo la ricerca. Va lanciato dalla cartella che contiene `test.db`. Ogni domanda del file JSON ha:

| Campo | Descrizione |
|---|---|
| `question` | La domanda |
| `category` | Categoria su cui cercare (`note` o `programma`) |
| `label` | `pertinente`, `fuori_tema` oppure `borderline` (vicina per tema ma senza risposta nel testo: viene mostrata ma non entra nel calcolo) |
| `expected_source` | Facoltativo: file, o lista di file, da cui ci si aspetta il primo risultato |

Per ogni categoria il comando stampa i punteggi per domanda, i margini tra pertinenti e fuori tema, una soglia suggerita, una tabella che confronta soglie vicine (pertinenti senza chunk, chunk pertinenti tagliati, fuori tema che passano) e cosa succede con la soglia attuale. Con `--rerank` ripete il report anche con il re-ranking (sezione `[re-ranking]`), con una tabella di soglie adatta ai suoi punteggi, così si confrontano i due metodi sulle stesse domande. Conviene rilanciarlo quando cambiano il corpus, il chunking o il modello.

## Struttura del progetto

```
personal-ai-knowledge/
├── src/
│   ├── cli.py          # entry point, argomenti, orchestrazione
│   ├── chunking.py     # chunking per parole o per frasi
│   ├── embedding.py    # caricamento modelli, prefissi, generazione embedding
│   ├── storage.py      # SQLite: chunk, log delle query, salvataggio risposte
│   ├── search.py       # similarità coseno e ranking
│   ├── reranking.py    # re-ranking con cross-encoder
│   ├── generation.py   # client API, system prompt delle tre modalità
│   ├── evaluation.py   # calcolo e report per il comando eval
│   └── readers.py      # lettura di .md e .pdf
├── eval/
│   └── questions.json  # domande etichettate per calibrare le soglie
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── ROADMAP.md
└── run.sh
```

I database `test.db` (chunk) e `logs_v2.db` (log delle query) vengono creati nella cartella da cui si lancia il comando.

## Dettagli tecnici

### Chunking

- **`word`**: taglia ogni `--dimension` parole, con overlap in parole. Semplice, ma può spezzare le frasi.
- **`sentence`** (default): divide il testo in frasi con una regex sulla punteggiatura e le accumula finché si supera `--dimension` parole. La frase che fa superare il tetto viene inclusa per intero, quindi il chunk può eccederlo. L'overlap è il numero di frasi ripetute all'inizio del chunk successivo.

La divisione in frasi è basata su regex: abbreviazioni come "Dott." possono produrre tagli imprecisi.

### Embedding per categoria

Tutte le categorie usano `google/embeddinggemma-2` (768 dimensioni, contesto fino a 8192 token, open-weight con licenza Apache 2.0, eseguito in locale). I testi non lasciano la macchina in questa fase. Il modello usa prompt dedicati, applicati automaticamente: `SearchQuery` per le domande e `Document` per i chunk.

| Categoria | Modello | Soglia (`min_sim`) | Chunking usato |
|---|---|---|---|
| `note` | `google/embeddinggemma-2` | 0.735 | predefinito (`--dimension 40 --overlap 1`) |
| `programma` | `google/embeddinggemma-2` | 0.65 | `--dimension 150 --overlap 1` |

Modello e soglie di ogni categoria sono definiti nel dizionario `CATEGORY_MODELS` in `cli.py`. Ogni chunk viene salvato con il nome del modello e la categoria; la ricerca legge solo i chunk della categoria richiesta. Se si cambia modello, bisogna reindicizzare tutta la categoria: embedding di modelli diversi non sono confrontabili, nemmeno a parità di dimensione del vettore. I modelli precedenti (`paraphrase-multilingual-mpnet-base-v2` e `intfloat/multilingual-e5-large`) restano gestiti in `embedding.py`.

Ogni modello tronca **in silenzio** il testo oltre il proprio limite di token. Con EmbeddingGemma 2 il limite (8192) è molto più alto dei chunk usati (circa 350 token nel `programma`), quindi il problema non si pone con questi dati.

### Retrieval

Similarità coseno tra domanda e chunk della categoria, ordinamento decrescente, scarto dei risultati sotto la soglia (quella della categoria o `--min-sim`), primi `--top-k`. Il confronto è calcolato in Python su tutti i chunk della categoria.

### Re-ranking

Con `--rerank` la ricerca per coseno non decide più cosa passare al modello: prende un gruppo più ampio di candidati (`--pool`, default 20), un cross-encoder (`BAAI/bge-reranker-v2-m3`) legge domanda e chunk insieme e assegna un punteggio tra 0 e 1, si tengono i primi `--top-k` e si scartano quelli sotto `--rerank-min`. Il modello pesa circa 2 GB, si scarica al primo uso ed è molto più veloce con una GPU. Si ricarica a ogni esecuzione.

Risultati sulle stesse 55 domande, misurati con i modelli di embedding precedenti (mpnet ed e5). Con EmbeddingGemma 2 i candidati scelti dalla ricerca cambiano: le soglie del re-ranker vanno riverificate con `eval --rerank`.

| Categoria | Pertinenti (1° chunk) | Fuori tema (chunk più alto) | Soglia scelta |
|---|---|---|---|
| `note` | 0.094 – 1.000 | fino a 0.040 | **0.06**: nessuna risposta persa, nessun fuori tema passa (con il coseno 5 su 11) |
| `programma` | 0.079 – 0.989 | fino a 0.001 | **0.03**: nessuna risposta persa, nessun fuori tema passa, nessuna borderline passa |

I punteggi del re-ranker sono molto polarizzati (vicini a 0 o a 1), quindi le soglie sono basse e il margine, soprattutto in `note` (0.040 contro 0.094), è stretto. Le domande ampie come "Cosa dice il programma sull'Unione Europea?" ottengono punteggi bassi anche se pertinenti. I chunk in coda alle domande pertinenti hanno spesso punteggi bassi perché non rispondono: con il re-ranking il contesto passato al modello è più corto e più mirato. Il vantaggio è netto su `note`; su `programma` il coseno separava già bene.

### Calibrazione della soglia

I punteggi di similarità non hanno lo stesso significato in modelli diversi, quindi la soglia si calibra per categoria e si rifà se cambia il modello. Si usa il comando `eval` (vedi [Valutare le soglie](#valutare-le-soglie)), che legge domande etichettate come pertinenti, fuori tema o borderline e confronta i punteggi di **tutti** i chunk recuperati.

Risultati con EmbeddingGemma 2 su 55 domande (15 + 11 + 4 per `note`, 14 + 7 + 4 per `programma`):

| Categoria | Pertinenti (1° chunk) | Fuori tema (chunk più alto) | Soglia scelta |
|---|---|---|---|
| `note` | 0.759 – 0.878 | fino a 0.707 | **0.735**: nessuna risposta persa, nessun fuori tema passa, 13 chunk su 75 tagliati |
| `programma` | 0.725 – 0.842 | fino a 0.611 | **0.65**: nessuna risposta persa, nessun chunk pertinente tagliato, nessun fuori tema passa |

Con i modelli precedenti la separazione era peggiore: in `note` (mpnet) pertinenti e fuori tema si sovrapponevano (pertinenti da 0.534, fuori tema fino a 0.571) e in `programma` (e5) tutti i punteggi stavano in una fascia di pochi centesimi.

Le domande borderline (vicine per tema ma senza risposta nel testo) superano comunque la soglia (3 su 4 in `note`, 4 su 4 in `programma`): il coseno non distingue "stesso tema" da "il testo risponde", quindi in `strict` decide il prompt, oppure si può usare il re-ranking. Il margine in `note` è di circa 0.05 sul primo risultato e il campione di calibrazione è piccolo, quindi la soglia va riverificata se cambiano il corpus o il chunking.

### Generazione

I chunk recuperati vengono passati al modello dentro un blocco `<context>`, insieme a un system prompt diverso per ogni modalità. La thinking mode del provider è disattivata. La temperatura dipende dalla modalità (0.0 in `strict` per la fedeltà alla fonte, più alta nelle altre per lasciare spazio all'integrazione) e si può sovrascrivere con `--temperature`. Il modello non ha accesso a file, database o web: vede solo quei frammenti.

### Log

Ogni query viene registrata in `logs_v2.db`, tabella `query_log`: modello di embedding, timestamp (UTC), domanda, categoria, numero di risultati, fonti, modalità, modello API, token (input, input in cache, output, reasoning, totale) e tempo di esecuzione. Il tempo misura ricerca e generazione, non il caricamento del modello di embedding.

Il log è in un database separato da quello dei chunk, così si può ricreare `test.db` per sperimentare sull'indicizzazione senza perdere lo storico. Ogni risposta viene salvata anche in `log_data_answer/`, con domanda, risposta, fonti, modalità e categoria.

## Privacy

Indicizzazione e ricerca avvengono in locale, ma per generare la risposta il testo dei chunk recuperati e la domanda vengono **inviati al provider API**. Non indicizzare con questo strumento contenuti che non vuoi condividere con il provider oppure usa un modello locale al posto dell'API.

## Limiti noti

- **Le soglie di similarità non sono confrontabili tra modelli** e vanno calibrate per ciascuno (vedi [Calibrazione](#calibrazione-della-soglia)). Cambiando modello bisogna reindicizzare e rifare la calibrazione.
- **La similarità coseno non separa nettamente** contenuti rilevanti e irrilevanti. In `note` una domanda fuori tema come "Come si prepara il tè?" arriva a 0.707, contro 0.759 della pertinente più debole: il margine è di circa 0.05. Le domande vicine per tema ma senza risposta nel testo (borderline) superano la soglia. Il filtro è grezzo: il re-ranking (`--rerank`) le gestiva meglio con i modelli precedenti (da riverificare con Gemma), altrimenti il secondo controllo è il prompt di `strict`.
- **`standard` e `full` possono trattare chunk poco pertinenti come fonti valide**, e le fonti elencate non garantiscono che ogni affermazione della risposta derivi da esse. In `full` testo e interpretazione del modello possono fondersi.
- **Risposte non identiche tra una esecuzione e l'altra**: la temperatura è bassa o nulla in `strict` e `standard`, quindi le risposte sono molto simili, ma il provider non garantisce un output uguale parola per parola. In `full` la variazione è voluta.
- Nessuna memoria tra le domande: ogni query è indipendente.
- I PDF scansionati (immagini) non sono supportati; l'estrazione del testo da PDF può produrre interruzioni di riga irregolari.
- Con molte migliaia di chunk la ricerca in Python puro rallenterà.

## Roadmap

Lo stato del progetto e i prossimi passi sono in [ROADMAP.md](ROADMAP.md).
