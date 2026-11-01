const $ = id => document.getElementById(id);

function el(tag, text, className) {
    const node = document.createElement(tag);

    if (text !== undefined) node.textContent = text;

    if (className) node.className = className;

    return node;
}

function addRow(table, cells, className) {
    const tr = table.insertRow();

    if (className) tr.className = className;

    for (const c of cells) tr.insertCell().textContent = c;

    return tr;
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

        await new Promise(r => setTimeout(r, 1500));
    }
}

// schede
for (const b of document.querySelectorAll("nav button")) {
    b.onclick = () => {
        document.querySelectorAll("nav button, section").forEach(n => n.classList.remove("on"));
        b.classList.add("on");
        $(b.dataset.tab).classList.add("on");

        if (b.dataset.tab === "index") loadSources();
    };
}

let thresholds = {};

async function init() {
    const cfg = await api("/api/config");
    thresholds = cfg.categories;

    for (const id of ["q-category", "i-category", "p-category"]) {
        for (const name of Object.keys(thresholds)) $(id).add(new Option(name));
    }
}

// --- Chiedi ---
$("q-go").onclick = async () => {
    $("q-go").disabled = true;
    $("q-answer").textContent = "…";
    $("q-answer").className = "pre";
    $("q-info").textContent = "";
    $("q-chunks").replaceChildren();

    try {
        const data = await api("/api/query", {
            text: $("q-text").value, category: $("q-category").value, mode: $("q-mode").value,
            top_k: Number($("q-topk").value), rerank: $("q-rerank").checked
        });
        $("q-answer").textContent = data.answer;
        const parts = ["Fonti: " + (data.sources.join(", ") || "nessuna")];

        if (data.usage) parts.push(`token: ${data.usage.input} in (${data.usage.cached} cached), ${data.usage.output} out, ${data.usage.total} totali`);

        if (data.elapsed) parts.push(data.elapsed.toFixed(1) + " s");

        $("q-info").textContent = parts.join(" · ");
        addRow($("q-chunks"), ["punteggio", "fonte", "testo"]);

        for (const c of data.chunks) addRow($("q-chunks"), [c.score.toFixed(3), c.source, c.text]);
    }
    catch (e) {
        $("q-answer").textContent = e.message;
        $("q-answer").className = "pre err";
    }

    $("q-go").disabled = false;
};

// --- Indicizza ---
async function loadSources() {
    const rows = await api("/api/sources");
    $("i-sources").replaceChildren();
    addRow($("i-sources"), ["categoria", "file", "chunk"]);

    for (const r of rows) addRow($("i-sources"), [r.category, r.source, r.chunks]);
}

$("i-go").onclick = async () => {
    const form = new FormData();
    form.append("category", $("i-category").value);
    form.append("strategy", $("i-strategy").value);
    form.append("dimension", $("i-dimension").value);
    form.append("overlap", $("i-overlap").value);
    form.append("folder", $("i-folder").value);

    for (const f of $("i-files").files) form.append("files", f);

    $("i-go").disabled = true;
    $("i-status").className = "muted";
    $("i-status").textContent = "invio dei file…";

    try {
        const { job } = await api("/api/index", undefined, form);
        const result = await pollJob(job, p => $("i-status").textContent = p);
        $("i-status").textContent = `Fatto: ${result.indexed} file indicizzati`;
        loadSources();
    }
    catch (e) {
        $("i-status").className = "err";
        $("i-status").textContent = e.message;
    }

    $("i-go").disabled = false;
};

// --- Valuta: prova una domanda ---
function renderProbeColumn(title, chunks, threshold) {
    const col = el("div");
    col.append(el("strong", `${title} (soglia ${threshold})`));
    const table = el("table");
    addRow(table, ["punteggio", "fonte", "testo"]);

    for (const c of chunks) addRow(table, [c.score.toFixed(3), c.source, c.text], c.score >= threshold ? "pass" : "cut");

    col.append(table);

    return col;
}

$("p-go").onclick = async () => {
    $("p-go").disabled = true;
    $("p-status").className = "muted";
    $("p-status").textContent = "…";
    $("p-out").replaceChildren();
    $("p-save").style.display = "none";

    try {
        const data = await api("/api/probe", { question: $("p-text").value, category: $("p-category").value });
        $("p-out").append(renderProbeColumn("Coseno", data.cosine, data.min_sim), renderProbeColumn("Re-ranking", data.rerank, data.rerank_min));
        $("p-status").textContent = "";
        $("p-save").style.display = "flex";
    }
    catch (e) {
        $("p-status").className = "err";
        $("p-status").textContent = e.message;
    }

    $("p-go").disabled = false;
};

$("p-add").onclick = async () => {
    const sources = $("p-source").value.split(",").map(s => s.trim()).filter(Boolean);

    try {
        const r = await api("/api/questions", {
            question: $("p-text").value, category: $("p-category").value, label: $("p-label").value, expected_source: sources
        });
        $("p-status").className = "muted";
        $("p-status").textContent = `Salvata (${r.total} domande nel file)`;
    }
    catch (e) {
        $("p-status").className = "err";
        $("p-status").textContent = e.message;
    }
};

// --- Valuta: eval completo ---
function renderReport(title, rep) {
    const box = el("div");
    const s = rep.summary;
    box.append(el("h4", `${title} (soglia ${rep.threshold})`));
    const lines = [];

    if (s.relevant_top1_min !== undefined) lines.push(`Pertinenti (${s.n_relevant}): primo risultato più basso ${s.relevant_top1_min.toFixed(3)}, chunk più basso ${s.relevant_all_min.toFixed(3)}`);

    if (s.off_topic_max !== undefined) lines.push(`Fuori tema (${s.n_off_topic}): chunk più alto ${s.off_topic_max.toFixed(3)}`);

    if (s.margin_all !== undefined) lines.push(`Margine (tutti i chunk): ${s.margin_all.toFixed(3)} · (solo primo): ${s.margin_top1.toFixed(3)}`);

    if (s.suggested !== undefined) lines.push(`Soglia suggerita: ${s.suggested.toFixed(3)}`);
    else if (s.n_relevant && s.n_off_topic) lines.push("Soglia suggerita: nessuna, i punteggi si sovrappongono");

    if (s.answers_lost) lines.push(`Pertinenti senza chunk: ${s.answers_lost.length}/${s.n_relevant} · chunk tagliati: ${s.chunks_cut}/${s.chunks_total}`);

    if (s.leaked) lines.push(`Fuori tema che passano: ${s.leaked.length}/${s.n_off_topic}`);

    for (const l of lines) box.append(el("div", l));

    for (const q of (s.answers_lost || [])) box.append(el("div", "persa: " + q, "err"));

    for (const q of (s.leaked || [])) box.append(el("div", "passa: " + q, "err"));

    const sw = el("table");
    addRow(sw, ["soglia", "pertinenti senza chunk", "chunk tagliati", "fuori tema che passano"]);

    for (const r of rep.sweep) addRow(sw, [r.threshold, r.answers_lost, `${r.chunks_cut}/${r.chunks_total}`, `${r.leaked}/${r.n_off_topic} (${r.leaked_chunks} chunk)`], r.threshold === rep.threshold ? "pass" : "");

    box.append(sw);

    const order = { pertinente: 0, borderline: 1, fuori_tema: 2 };
    const rows = [...rep.results].sort((a, b) => order[a.label] - order[b.label] || (b.scores[0] || 0) - (a.scores[0] || 0));
    const t = el("table");
    addRow(t, ["etichetta", "1°", "ultimo", "esito", "fonte", "domanda"]);

    for (const r of rows) {
        const top = r.scores[0], last = r.scores[r.scores.length - 1];
        const source = r.expected_source ? (r.expected_source.includes(r.sources[0]) ? "ok" : "ERRATA") : "-";
        addRow(t, [r.label, top === undefined ? "-" : top.toFixed(3), last === undefined ? "-" : last.toFixed(3), top >= rep.threshold ? "passa" : "scartata", source, r.question]);
    }

    box.append(t);

    return box;
}

$("e-go").onclick = async () => {
    $("e-go").disabled = true;
    $("e-status").className = "muted";
    $("e-out").replaceChildren();

    try {
        const { job } = await api("/api/eval", { rerank: $("e-rerank").checked });
        const reports = await pollJob(job, p => $("e-status").textContent = p);
        $("e-status").textContent = "";

        for (const [category, rep] of Object.entries(reports)) {
            $("e-out").append(el("h3", "Categoria: " + category));

            if (rep.skipped) {
                $("e-out").append(el("div", "nessun chunk indicizzato, saltata"));

                continue;
            }

            $("e-out").append(renderReport("Coseno", rep.cosine));

            if (rep.rerank) $("e-out").append(renderReport("Re-ranking", rep.rerank));
        }
    }
    catch (e) {
        $("e-status").className = "err";
        $("e-status").textContent = e.message;
    }

    $("e-go").disabled = false;
};

init().catch(e => document.body.prepend(el("p", e.message, "err")));
