const $ = id => document.getElementById(id);

function el(tag, text, className) {
    const node = document.createElement(tag);

    if (text !== undefined) node.textContent = text;

    if (className) node.className = className;

    return node;
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function api(path, body, form) {
    const options = {};

    if (form) {
        options.method = "POST";
        options.body = form;
    }
    else if (body !== undefined) {
        options.method = "POST";
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify(body);
    }

    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));

    if (!res.ok) throw new Error(data.detail || ("Errore " + res.status));

    return data;
}

async function pollJob(id, onProgress) {
    while (true) {
        const job = await api("/api/jobs/" + id);
        onProgress(job.progress);

        if (job.state === "done") return job.result;

        if (job.state === "error") throw new Error(job.error);

        await sleep(1500);
    }
}

function fillSelect(select, values, selected) {
    select.replaceChildren();

    for (const value of values) select.add(new Option(value, value));

    if (selected !== undefined) select.value = selected;
}

function setStatus(node, text, isError) {
    node.textContent = text;
    node.classList.toggle("err", Boolean(isError));
}

function makeTable(headers, rows, currentIndex) {
    const wrap = el("div", undefined, "table-wrap");
    const table = el("table");
    const head = table.createTHead().insertRow();

    for (const h of headers) head.append(el("th", h));

    const body = table.createTBody();

    rows.forEach((cells, index) => {
        const tr = body.insertRow();

        if (index === currentIndex) tr.className = "current";

        for (const cell of cells) {
            const td = tr.insertCell();

            if (cell instanceof Node) td.append(cell);
            else td.textContent = cell;
        }
    });

    wrap.append(table);

    return wrap;
}

function badge(text, kind) {
    return el("span", text, "badge " + kind);
}

function chunkCard(chunk, state) {
    const card = el("div", undefined, "chunk" + (state ? " " + state : ""));
    const head = el("div", undefined, "chunk-head");
    head.append(el("span", chunk.source), el("span", chunk.score.toFixed(3), "score"));
    card.append(head, el("div", chunk.text, "chunk-text"));

    return card;
}

// --- schede ---
for (const tab of document.querySelectorAll(".tab")) {
    tab.onclick = () => {
        document.querySelectorAll(".tab, .page").forEach(n => n.classList.remove("on"));
        tab.classList.add("on");
        $(tab.dataset.tab).classList.add("on");

        if (tab.dataset.tab === "index") loadSources();
    };
}

// --- avvio e stato dei modelli ---
function setReady(ready) {
    document.querySelectorAll(".needs-models").forEach(button => button.disabled = !ready);
}

async function waitForModels() {
    const banner = $("banner");
    setReady(false);

    while (true) {
        try {
            const status = await api("/api/status");

            if (status.error) {
                banner.className = "banner error";
                banner.textContent = "Caricamento dei modelli fallito: " + status.error;
                banner.hidden = false;

                return;
            }

            if (status.ready) {
                banner.hidden = true;
                setReady(true);

                return;
            }

            banner.className = "banner";
            banner.textContent = "I modelli sono in caricamento: le richieste si attiveranno appena sono pronti.";
            banner.hidden = false;
        }
        catch (e) {
            // il server potrebbe non essere ancora raggiungibile: si riprova
        }

        await sleep(2000);
    }
}

async function init() {
    const cfg = await api("/api/config");
    const categories = Object.keys(cfg.categories);
    const d = cfg.defaults;

    for (const id of ["q-category", "i-category", "p-category"]) fillSelect($(id), categories, d.category);

    fillSelect($("q-mode"), cfg.modes, d.mode);
    fillSelect($("i-strategy"), cfg.strategies, d.strategy);
    fillSelect($("p-label"), cfg.labels, cfg.labels[0]);
    $("q-topk").value = d.top_k;
    $("i-dimension").value = d.dimension;
    $("i-overlap").value = d.overlap;

    waitForModels();
}

// --- Chiedi ---
async function ask() {
    $("q-go").disabled = true;
    $("q-result").hidden = false;
    $("q-answer").textContent = "Sto cercando nelle note…";
    $("q-answer").classList.remove("err");
    $("q-sources").replaceChildren();
    $("q-info").textContent = "";
    $("q-chunks").replaceChildren();

    try {
        const data = await api("/api/query", {
            text: $("q-text").value,
            category: $("q-category").value,
            mode: $("q-mode").value,
            top_k: Number($("q-topk").value),
            rerank: $("q-rerank").checked
        });
        $("q-answer").textContent = data.answer;

        for (const source of data.sources) $("q-sources").append(el("span", source, "chip"));

        const parts = [];

        if (data.usage) parts.push(`${data.usage.input} token in ingresso (${data.usage.cached} in cache), ${data.usage.output} in uscita, ${data.usage.total} totali`);

        if (data.elapsed) parts.push(data.elapsed.toFixed(1) + " s");

        $("q-info").textContent = parts.join(" · ");

        for (const chunk of data.chunks) $("q-chunks").append(chunkCard(chunk));
    }
    catch (e) {
        $("q-answer").textContent = e.message;
        $("q-answer").classList.add("err");
    }

    $("q-go").disabled = false;
}

$("q-go").onclick = ask;
$("q-text").onkeydown = e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !$("q-go").disabled) ask();
};

// --- Indicizza ---
async function loadSources() {
    const rows = await api("/api/sources");
    $("i-sources").replaceChildren();

    if (rows.length === 0) {
        $("i-sources").append(el("p", "Il database è vuoto.", "muted"));

        return;
    }

    $("i-sources").append(makeTable(["Categoria", "File", "Chunk"], rows.map(r => [r.category, r.source, r.chunks])));
}

function showSelectedFiles() {
    $("i-list").replaceChildren();

    for (const file of $("i-files").files) $("i-list").append(el("li", file.name));
}

$("i-files").onchange = showSelectedFiles;

for (const type of ["dragenter", "dragover"]) {
    $("i-drop").addEventListener(type, e => {
        e.preventDefault();
        $("i-drop").classList.add("over");
    });
}

for (const type of ["dragleave", "drop"]) {
    $("i-drop").addEventListener(type, e => {
        e.preventDefault();
        $("i-drop").classList.remove("over");
    });
}

$("i-drop").addEventListener("drop", e => {
    $("i-files").files = e.dataTransfer.files;
    showSelectedFiles();
});

function showProgress(text) {
    const match = text.match(/\[(\d+)\/(\d+)\]/);

    $("i-status").textContent = text;

    if (match) {
        $("i-progress").hidden = false;
        $("i-bar").style.width = (100 * Number(match[1]) / Number(match[2])) + "%";
    }
}

$("i-go").onclick = async () => {
    const form = new FormData();
    form.append("category", $("i-category").value);
    form.append("strategy", $("i-strategy").value);
    form.append("dimension", $("i-dimension").value);
    form.append("overlap", $("i-overlap").value);
    form.append("folder", $("i-folder").value);

    for (const file of $("i-files").files) form.append("files", file);

    $("i-go").disabled = true;
    $("i-progress").hidden = true;
    $("i-bar").style.width = "0";
    setStatus($("i-status"), "Invio dei file…");

    try {
        const { job } = await api("/api/index", undefined, form);
        const result = await pollJob(job, showProgress);
        $("i-bar").style.width = "100%";
        setStatus($("i-status"), `Fatto: ${result.indexed} file indicizzati`);
        loadSources();
    }
    catch (e) {
        setStatus($("i-status"), e.message, true);
    }

    $("i-go").disabled = false;
};

// --- Valuta: prova una domanda ---
function probeColumn(title, chunks, threshold) {
    const col = el("div");
    col.append(el("h3", `${title} (soglia ${threshold})`));
    const list = el("div", undefined, "stack");

    for (const chunk of chunks) list.append(chunkCard(chunk, chunk.score >= threshold ? "pass" : "cut"));

    col.append(list);

    return col;
}

$("p-go").onclick = async () => {
    $("p-go").disabled = true;
    $("p-out").replaceChildren();
    $("p-save").hidden = true;
    setStatus($("p-status"), "Calcolo…");

    try {
        const data = await api("/api/probe", { question: $("p-text").value, category: $("p-category").value });
        $("p-out").append(probeColumn("Coseno", data.cosine, data.min_sim), probeColumn("Re-ranking", data.rerank, data.rerank_min));
        $("p-save").hidden = false;
        setStatus($("p-status"), "");
    }
    catch (e) {
        setStatus($("p-status"), e.message, true);
    }

    $("p-go").disabled = false;
};

$("p-add").onclick = async () => {
    const sources = $("p-source").value.split(",").map(s => s.trim()).filter(Boolean);

    try {
        const r = await api("/api/questions", {
            question: $("p-text").value,
            category: $("p-category").value,
            label: $("p-label").value,
            expected_source: sources
        });
        setStatus($("p-status"), `Domanda salvata (${r.total} nel file)`);
    }
    catch (e) {
        setStatus($("p-status"), e.message, true);
    }
};

// --- Valuta: valutazione completa ---
function metric(label, value) {
    const box = el("div", undefined, "metric");
    box.append(el("small", label), el("strong", value));

    return box;
}

function renderReport(title, rep) {
    const s = rep.summary;
    const box = el("div", undefined, "report");
    box.append(el("h3", `${title} (soglia ${rep.threshold})`));

    const metrics = el("div", undefined, "metrics");

    if (s.relevant_top1_min !== undefined) metrics.append(metric(`Pertinenti (${s.n_relevant}): primo più basso`, s.relevant_top1_min.toFixed(3)));

    if (s.off_topic_max !== undefined) metrics.append(metric(`Fuori tema (${s.n_off_topic}): più alto`, s.off_topic_max.toFixed(3)));

    if (s.margin_all !== undefined) metrics.append(metric("Margine (tutti / primo)", `${s.margin_all.toFixed(3)} / ${s.margin_top1.toFixed(3)}`));

    metrics.append(metric("Soglia suggerita", s.suggested !== undefined ? s.suggested.toFixed(3) : (s.n_relevant && s.n_off_topic ? "nessuna (si sovrappongono)" : "-")));
    box.append(metrics);

    if (s.answers_lost) box.append(el("p", `Pertinenti senza chunk: ${s.answers_lost.length}/${s.n_relevant} · chunk tagliati: ${s.chunks_cut}/${s.chunks_total}`, "muted"));

    if (s.leaked) box.append(el("p", `Fuori tema che passano: ${s.leaked.length}/${s.n_off_topic}`, "muted"));

    for (const q of (s.answers_lost || [])) box.append(el("div", "persa: " + q, "err"));

    for (const q of (s.leaked || [])) box.append(el("div", "passa: " + q, "err"));

    const sweepRows = rep.sweep.map(r => [r.threshold, r.answers_lost, `${r.chunks_cut}/${r.chunks_total}`, `${r.leaked}/${r.n_off_topic} (${r.leaked_chunks} chunk)`]);
    const currentIndex = rep.sweep.findIndex(r => r.threshold === rep.threshold);
    box.append(el("p", "Soglie a confronto", "muted"));
    box.append(makeTable(["Soglia", "Pertinenti senza chunk", "Chunk tagliati", "Fuori tema che passano"], sweepRows, currentIndex));

    const order = { pertinente: 0, borderline: 1, fuori_tema: 2 };
    const results = [...rep.results].sort((a, b) => order[a.label] - order[b.label] || (b.scores[0] || 0) - (a.scores[0] || 0));
    const rows = results.map(r => {
        const top = r.scores[0];
        const last = r.scores[r.scores.length - 1];
        const passes = top !== undefined && top >= rep.threshold;
        const sourceOk = r.expected_source ? r.expected_source.includes(r.sources[0]) : null;

        return [
            r.label,
            top === undefined ? "-" : top.toFixed(3),
            last === undefined ? "-" : last.toFixed(3),
            badge(passes ? "passa" : "scartata", passes ? "ok" : "neutral"),
            sourceOk === null ? "-" : badge(sourceOk ? "ok" : "errata", sourceOk ? "ok" : "ko"),
            r.question
        ];
    });
    box.append(el("p", "Risultato per domanda", "muted"));
    box.append(makeTable(["Etichetta", "1°", "Ultimo", "Esito", "Fonte", "Domanda"], rows));

    return box;
}

$("e-go").onclick = async () => {
    $("e-go").disabled = true;
    $("e-out").replaceChildren();
    setStatus($("e-status"), "In corso…");

    try {
        const { job } = await api("/api/eval", { rerank: $("e-rerank").checked });
        const reports = await pollJob(job, p => setStatus($("e-status"), p));
        setStatus($("e-status"), "");

        for (const [category, rep] of Object.entries(reports)) {
            const card = el("div", undefined, "card");
            card.append(el("h2", "Categoria: " + category));

            if (rep.skipped) {
                card.append(el("p", "Nessun chunk indicizzato: categoria saltata.", "muted"));
            }
            else {
                card.append(renderReport("Coseno", rep.cosine));

                if (rep.rerank) card.append(renderReport("Re-ranking", rep.rerank));
            }

            $("e-out").append(card);
        }
    }
    catch (e) {
        setStatus($("e-status"), e.message, true);
    }

    $("e-go").disabled = false;
};

init().catch(e => document.body.prepend(el("p", e.message, "banner error")));
