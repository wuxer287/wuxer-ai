import sys
import argparse
from pathlib import Path
from storage import createConnection, createTableChunk, countChunksByCategory
from embedding import loadModel
from generation import createClient
from evaluation import loadQuestions, groupByCategory, scoreQuestions, summarize, printReport
from reranking import loadReranker
from service import Engine, EmptyCategoryError, listIndexableFiles, indexFiles, answerQuestion
from consts import (
    CATEGORY_MODELS,
    DB_PATH,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    MODES,
    STRATEGIES,
    RERANK_SWEEP,
    DEFAULT_CATEGORY,
    DEFAULT_MODE,
    DEFAULT_TOP_K,
    DEFAULT_POOL,
    DEFAULT_DIMENSION,
    DEFAULT_OVERLAP,
    DEFAULT_STRATEGY
)

parser = argparse.ArgumentParser(description="Wuxer AI - indicizza le tue note e fai domande basate sul loro contenuto.")
subparsers = parser.add_subparsers(dest="command", help="Comando da eseguire.")

#
# index command
#
index_parser = subparsers.add_parser(
    "index",
    help="Indicizza i file .md e .pdf di una cartella: li divide in chunk, genera gli embedding e li salva nel database.",
    description="Indicizza i file .md e .pdf di una cartella: li divide in chunk, genera gli embedding e li salva nel database.",
)

index_parser.add_argument(
    "folder",
    help="Percorso della cartella contenente i file .md e/o .pdf da indicizzare.",
)

index_parser.add_argument(
    "--dimension",
    type=int,
    default=DEFAULT_DIMENSION,
    help="Dimensione del chunk. Con --strategy=word: numero esatto di parole per chunk. "
         "Con --strategy=sentence: numero massimo di parole per chunk (il chunk può superare leggermente questo limite "
         "per includere l'ultima frase intera)."
)

index_parser.add_argument(
    "--overlap",
    type=int,
    default=DEFAULT_OVERLAP,
    help="Sovrapposizione tra chunk consecutivi, per non prendere contesto ai margini. "
         "Con --strategy=word: espresso in numero di parole. "
         "Con --strategy=sentence: espresso in numero di frasi."
)

index_parser.add_argument(
    "--strategy",
    choices=STRATEGIES,
    default=DEFAULT_STRATEGY,
    help="Metodo di chunking: 'word' taglia per numero fisso di parole (più semplice, può spezzare le frasi); "
         "'sentence' raggruppa frasi intere fino al limite di parole, senza spezzarle (default, consigliato per note in prosa)."
)

index_parser.add_argument(
    "--category",
    choices=list(CATEGORY_MODELS.keys()),
    default=DEFAULT_CATEGORY,
    help="Categoria del contenuto: determina il modello di embedding usato per indicizzare i file "
         "(note: testi brevi in prosa; programma: documenti lunghi, come un programma politico). "
         "Usa la stessa categoria in fase di query (default: note)."
)

#
# query command
#
query_parser = subparsers.add_parser(
    "query",
    help="Cerca nelle note indicizzate e genera una risposta basata sui chunk più pertinenti.",
    description="Cerca nelle note indicizzate e genera una risposta basata sui chunk più pertinenti."
)

query_parser.add_argument(
    "text",
    help="La domanda da porre, basata sulle note indicizzate."
)

query_parser.add_argument(
    "--top-k",
    type=int,
    default=DEFAULT_TOP_K,
    help="Numero massimo di chunk da recuperare e passare al modello come contesto (default: 5)."
)

query_parser.add_argument(
    "--mode",
    choices=MODES,
    default=DEFAULT_MODE,
    help="Quanto la risposta può discostarsi dalle informazioni fornite: 'strict' usa solo quelle, "
         "'standard' le integra con conoscenza generale segnalandolo sempre, "
         "'full' integra liberamente senza distinzioni esplicite."
)

query_parser.add_argument(
    "--min-sim",
    type=float,
    default=None,
    help="Soglia minima di similarità (0-1) sotto la quale un chunk viene scartato prima di essere passato al modello. "
         "Se omessa, si usa quella calibrata per la categoria. "
         "Indica 0 per vedere tutti i risultati, utile con --show-chunks per calibrare. "
         "Le soglie vanno calibrate per ogni categoria."
)

query_parser.add_argument(
    "--category",
    choices=list(CATEGORY_MODELS.keys()),
    default=DEFAULT_CATEGORY,
    help="Categoria su cui cercare: deve coincidere con quella usata in fase di indicizzazione, "
         "perché la ricerca avviene solo tra i chunk di quella categoria (default: note)."
)

query_parser.add_argument(
    "--show-chunks",
    action="store_true",
    help="Stampa i chunks recuperati (testo, punteggio di similarità e fonte) prima della risposta. "
         "Utile per verificare cosa riceve il modello e per calibrare --min-sim."
)

query_parser.add_argument(
    "--temperature",
    type=float,
    default=None,
    help="Temperatura di generazione (0 = risposte più stabili e ripetibili, valori più alti = più variabili). "
         "Se omessa, dipende dalla modalità: strict 0.0, standard 0.3, full 0.6."
)

query_parser.add_argument(
    "--rerank",
    action="store_true",
    help="Riordina i candidati con un cross-encoder (BAAI/bge-reranker-v2-m3) e scarta quelli sotto --rerank-min. "
         "Più preciso ma più lento. "
         "Con questa opzione --min-sim viene ignorato."
)

query_parser.add_argument(
    "--rerank-min",
    type=float,
    default=None,
    help="Soglia minima (0-1) sul punteggio del re-ranker. Se omessa, si usa quella calibrata per la categoria. "
         "Indica 0 per vedere tutti i risultati. Non è confrontabile con --min-sim."
)

query_parser.add_argument(
    "--pool",
    type=int,
    default=DEFAULT_POOL,
    help="Con --rerank: numero di candidati recuperati dalla ricerca e passati al re-ranker (default: 20)."
)


#
# eval command
#
eval_parser = subparsers.add_parser(
    "eval",
    help="Valuta le soglie di similarità su un insieme di domande etichettate senza chiamare l'LLM.",
    description="Per ogni domanda del file JSON cerca i chunks più simili e riassume come si separano le domande pertinenti da quelle fuori tema, "
         "per verificare o calibrare la soglia di ogni categoria. Non usa l'api: serve solo per la ricerca."
)

eval_parser.add_argument(
    "file",
    help="Percorso del file JSON con le domande. Ogni elemento ha: question, category, label (pertinente, borderline o fuori_tema) "
         "e, facoltativo, expected_source (file da cui ci si aspetta il primo risultato)."
)

eval_parser.add_argument(
    "--top-k",
    type=int,
    default=DEFAULT_TOP_K,
    help="Numero di chunk analizzati per ogni domanda: tutti i loro punteggi entrano nel riepilogo (default: 5)."
)

eval_parser.add_argument(
    "--verbose",
    action="store_true",
    help="Stampa anche punteggio e fonte di ogni chunk recuperato per ogni domanda."
)

eval_parser.add_argument(
    "--rerank",
    action="store_true",
    help="Dopo il report normale, ripete la valutazione con il re-ranking (cross-encoder) per confrontare i risultati."
)

eval_parser.add_argument(
    "--pool",
    type=int,
    default=DEFAULT_POOL,
    help="Numero di candidati presi dalla ricerca e passati al re-ranker (default: 20)."
)

eval_parser.add_argument(
    "--rerank-min",
    type=float,
    default=None,
    help="Soglia sul punteggio del re-ranker (0-1) usata nel report (default: quella della categoria)."
)


args = parser.parse_args()

if args.command == "index":
    folder = Path(args.folder)

    if not folder.exists():
        print("La cartella non esiste")

        sys.exit(1)

    if not folder.is_dir():
        print("Non è una cartella")

        sys.exit(1)

    files = listIndexableFiles(folder)

    if len(files) == 0:
        print("Non ci sono file da indicizzare")

        sys.exit(1)

    def printProgress(number, total, name):
        print(f"[{number}/{total}] file indexed ({name})")

    indexFiles(Engine(), files, args.category, args.dimension, args.overlap, args.strategy, printProgress)

    print("DONE")
elif args.command == "query":
    if DEEPSEEK_API_KEY is None:
        print("Manca l'api key")

        sys.exit(1)

    try:
        res = answerQuestion(Engine(), createClient(DEEPSEEK_API_KEY), DEEPSEEK_MODEL, args.text, args.category, args.mode, args.temperature, top_k=args.top_k, min_sim=args.min_sim, use_rerank=args.rerank, rerank_min=args.rerank_min, pool=args.pool)
    except EmptyCategoryError:
        print("Non ci sono valori per questa ricerca")

        sys.exit(0)

    if args.show_chunks:
        print(res["chunks"])

    usage = res["usage"]

    print(f"\n{res["answer"]}")

    if usage is None:
        sys.exit(0)

    print(f"\nFONTI CONSULTATE: [{", ".join(res["sources"]) if res["sources"] else "nessuna"}]")
    print("\n=====")
    print(f"INPUT = {usage["input"]} token (CACHED = {usage["cached"]} token)\nOUTPUT = {usage["output"]} token (REASONING = {usage["reasoning"]} token)\nTOTAL = {usage["total"]} token")
    print("=====")
elif args.command == "eval":
    try:
        questions = loadQuestions(args.file, list(CATEGORY_MODELS.keys()))
    except (OSError, ValueError) as e:
        print(f"Impossibile leggere le domande: {e}")

        sys.exit(1)

    conn_chunk = createConnection(DB_PATH, vector=True)

    reranker = loadReranker() if args.rerank else None
    models = {}

    for category, group in groupByCategory(questions).items():
        hf_model_name = CATEGORY_MODELS[category]["model"]
        threshold = CATEGORY_MODELS[category]["min_sim"]

        if hf_model_name not in models:
            models[hf_model_name] = loadModel(hf_model_name)

        model = models[hf_model_name]
        createTableChunk(conn_chunk, model.get_embedding_dimension())

        if countChunksByCategory(conn_chunk, category) == 0:
            print(f"Categoria {category}: nessun chunk indicizzato, viene saltato")

            continue

        results = scoreQuestions(conn_chunk, model, hf_model_name, category, group, args.top_k)
        summary = summarize(results, threshold)
        printReport(category, results, summary, args.verbose)

        if reranker is not None:
            rr_results = scoreQuestions(conn_chunk, model, hf_model_name, category, group, args.top_k, reranker, args.pool)
            rr_threshold = args.rerank_min if args.rerank_min is not None else CATEGORY_MODELS[category]["rerank_min"]
            rr_summary = summarize(rr_results, rr_threshold)
            printReport(category, rr_results, rr_summary, args.verbose, RERANK_SWEEP, "re-ranking")
else:
    parser.print_help()
