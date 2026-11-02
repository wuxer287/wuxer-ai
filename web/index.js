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
    const text = el("div", chunk.text, "chunk-text");
    text.title = "Clicca per espandere";
    text.onclick = () => text.classList.toggle("open");
    card.append(head, text);

    return card;
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";

    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";

    return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

const INLINE = /`([^`]+)`|\*\*(.+?)\*\*|\*(?=[^\s*])(.+?)\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/;
const LIST_ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const TABLE_SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function renderInline(parent, text) {
    while (text) {
        const match = INLINE.exec(text);

        if (!match) {
            parent.append(text);

            return;
        }

        if (match.index > 0) parent.append(text.slice(0, match.index));

        let node;

        if (match[1] !== undefined) {
            node = el("code", match[1]);
        }
        else if (match[2] !== undefined) {
            node = el("strong");
            renderInline(node, match[2]);
        }
        else if (match[3] !== undefined) {
            node = el("em");
            renderInline(node, match[3]);
        }
        else {
            node = el("a");
            node.href = match[5];
            node.target = "_blank";
            node.rel = "noopener noreferrer";
            renderInline(node, match[4]);
        }

        parent.append(node);
        text = text.slice(match.index + match[0].length);
    }
}

function splitRow(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(cell => cell.trim());
}

function renderList(root, items) {
    const stack = [];

    for (const item of items) {
        const ordered = /\d/.test(item.marker);

        while (stack.length && item.indent < stack[stack.length - 1].indent) stack.pop();

        let top = stack[stack.length - 1];

        if (!top || item.indent > top.indent) {
            const list = el(ordered ? "ol" : "ul");

            if (top) top.last.append(list);
            else root.append(list);

            top = { indent: item.indent, list, last: null };
            stack.push(top);
        }

        const li = el("li");
        renderInline(li, item.text);
        top.list.append(li);
        top.last = li;
    }
}

function renderMarkdown(root, source) {
    const lines = source.replace(/\r\n?/g, "\n").split("\n");
    let paragraph = [];
    let i = 0;

    function flush() {
        if (paragraph.length === 0) return;

        const p = el("p");

        paragraph.forEach((line, index) => {
            if (index > 0) p.append(el("br"));

            renderInline(p, line.trim());
        });
        root.append(p);
        paragraph = [];
    }

    root.replaceChildren();

    while (i < lines.length) {
        const line = lines[i];
        let match;

        if (/^\s*```/.test(line)) {
            flush();
            const code = [];
            i++;

            while (i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i++]);

            i++;
            const pre = el("pre");
            pre.append(el("code", code.join("\n")));
            root.append(pre);
        }
        else if (line.trim() === "") {
            flush();
            i++;
        }
        else if ((match = /^(#{1,6})\s+(.*)$/.exec(line))) {
            flush();
            const heading = el("h" + Math.min(match[1].length + 2, 6));
            renderInline(heading, match[2].replace(/\s+#+\s*$/, ""));
            root.append(heading);
            i++;
        }
        else if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
            flush();
            root.append(el("hr"));
            i++;
        }
        else if (/^\s*>/.test(line)) {
            flush();
            const quote = [];

            while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ""));

            const block = el("blockquote");
            renderMarkdown(block, quote.join("\n"));
            root.append(block);
        }
        else if (LIST_ITEM.test(line)) {
            flush();
            const items = [];

            while (i < lines.length) {
                const item = LIST_ITEM.exec(lines[i]);

                if (item) {
                    items.push({ indent: item[1].length, marker: item[2], text: item[3] });
                }
                else if (lines[i].trim() === "" && i + 1 < lines.length && LIST_ITEM.test(lines[i + 1])) {
                    // riga vuota tra due voci: la lista continua
                }
                else if (/^\s+\S/.test(lines[i]) && items.length) {
                    items[items.length - 1].text += " " + lines[i].trim();
                }
                else {
                    break;
                }

                i++;
            }

            renderList(root, items);
        }
        else if (line.includes("|") && i + 1 < lines.length && TABLE_SEPARATOR.test(lines[i + 1])) {
            flush();
            const rows = [];
            const header = splitRow(line);
            i += 2;

            while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") rows.push(splitRow(lines[i++]));

            const wrap = el("div", undefined, "table-wrap");
            const table = el("table");
            const head = table.createTHead().insertRow();

            for (const cell of header) {
                const th = el("th");
                renderInline(th, cell);
                head.append(th);
            }

            const body = table.createTBody();

            for (const cells of rows) {
                const tr = body.insertRow();

                for (const cell of cells) renderInline(tr.insertCell(), cell);
            }

            wrap.append(table);
            root.append(wrap);
        }
        else {
            paragraph.push(line);
            i++;
        }
    }

    flush();
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

for (const tab of document.querySelectorAll(".subtab")) {
    tab.onclick = () => {
        document.querySelectorAll(".subtab, .subpage").forEach(n => n.classList.remove("on"));
        tab.classList.add("on");
        $(tab.dataset.sub).classList.add("on");
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
function metaItem(label, value) {
    const item = el("span", undefined, "meta-item");
    item.append(el("span", label), el("strong", value));

    return item;
}

async function ask() {
    $("q-go").disabled = true;
    $("q-result").hidden = false;
    $("q-chunks-card").hidden = true;
    $("q-info").replaceChildren();
    $("q-sources").replaceChildren();
    $("q-chunks").replaceChildren();
    $("q-answer").replaceChildren(el("span", "Sto cercando nelle note…", "muted"));

    try {
        const data = await api("/api/query", {
            text: $("q-text").value,
            category: $("q-category").value,
            mode: $("q-mode").value,
            top_k: Number($("q-topk").value),
            rerank: $("q-rerank").checked
        });
        renderMarkdown($("q-answer"), data.answer);

        for (const source of data.sources) $("q-sources").append(el("span", source, "chip"));

        if (data.usage) {
            const input = data.usage.cached ? `${data.usage.input} (${data.usage.cached} in cache)` : String(data.usage.input);
            $("q-info").append(metaItem("input token", input), metaItem("output token", String(data.usage.output)), metaItem("total token", String(data.usage.total)));
        }

        if (data.elapsed) $("q-info").append(metaItem("tempo", data.elapsed.toFixed(1) + " s"));

        for (const chunk of data.chunks) $("q-chunks").append(chunkCard(chunk));

        $("q-count").textContent = data.chunks.length || "";
        $("q-chunks-card").hidden = data.chunks.length === 0;
    }
    catch (e) {
        $("q-answer").replaceChildren(el("span", e.message, "err"));
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
    const groups = new Map();
    $("i-sources").replaceChildren();

    if (rows.length === 0) {
        $("i-total").textContent = "";
        $("i-sources").append(el("p", "Nessun documento indicizzato.", "muted"));

        return;
    }

    for (const row of rows) {
        if (!groups.has(row.category)) groups.set(row.category, []);

        groups.get(row.category).push(row);
    }

    $("i-total").textContent = rows.length;

    for (const [category, docs] of groups) {
        const group = el("div", undefined, "group");
        const chunks = docs.reduce((sum, doc) => sum + doc.chunks, 0);
        const head = el("div", undefined, "group-head");
        head.append(el("span", category), el("span", `${docs.length} file · ${chunks} chunk`));
        group.append(head);

        for (const doc of docs) {
            const item = el("div", undefined, "doc");
            item.append(el("span", doc.source), el("span", `${doc.chunks} chunk`));
            group.append(item);
        }

        $("i-sources").append(group);
    }
}

let selected = [];

function showSelectedFiles() {
    const count = selected.length;
    $("i-list").replaceChildren();
    $("i-selected").hidden = count === 0;
    $("i-count").textContent = count === 1 ? "1 file selezionato" : `${count} file selezionati`;
    $("i-go").textContent = count ? `Indicizza ${count} file` : "Indicizza";

    selected.forEach((file, index) => {
        const item = el("li");
        const remove = el("button", "×", "remove");
        remove.type = "button";
        remove.title = "Rimuovi " + file.name;
        remove.onclick = () => {
            selected.splice(index, 1);
            showSelectedFiles();
        };
        item.append(el("span", file.name.split(".").pop().toUpperCase(), "ext"), el("span", file.name, "file-name"), el("span", formatSize(file.size), "file-size"), remove);
        $("i-list").append(item);
    });
}

function addFiles(files) {
    const rejected = [];

    for (const file of files) {
        if (!/\.(md|pdf)$/.test(file.name)) {
            rejected.push(file.name);

            continue;
        }

        const index = selected.findIndex(f => f.name === file.name);

        if (index >= 0) selected[index] = file;
        else selected.push(file);
    }

    showSelectedFiles();
    setStatus($("i-status"), rejected.length ? "Ignorati (sono ammessi solo .md e .pdf): " + rejected.join(", ") : "", rejected.length > 0);
}

$("i-files").onchange = () => {
    addFiles($("i-files").files);
    $("i-files").value = "";
};
$("i-clear").onclick = () => {
    selected = [];
    showSelectedFiles();
};

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

$("i-drop").addEventListener("drop", e => addFiles(e.dataTransfer.files));

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

    for (const file of selected) form.append("files", file);

    $("i-go").disabled = true;
    $("i-progress").hidden = true;
    $("i-bar").style.width = "0";
    setStatus($("i-status"), "Invio dei file…");

    try {
        const { job } = await api("/api/index", undefined, form);
        const result = await pollJob(job, showProgress);
        $("i-bar").style.width = "100%";
        setStatus($("i-status"), `Fatto: ${result.indexed} file indicizzati`);
        selected = [];
        showSelectedFiles();
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
    const passed = chunks.filter(chunk => chunk.score >= threshold).length;
    col.append(el("h3", `${title} · soglia ${threshold} · ${passed}/${chunks.length} sopra`));
    const list = el("div", undefined, "stack");

    for (const chunk of chunks) list.append(chunkCard(chunk, chunk.score >= threshold ? "pass" : "cut"));

    col.append(list);

    return col;
}

$("p-go").onclick = async () => {
    $("p-go").disabled = true;
    $("p-out").replaceChildren();
    $("p-result").hidden = true;
    $("p-save").hidden = true;
    setStatus($("p-status"), "Calcolo…");

    try {
        const data = await api("/api/probe", { question: $("p-text").value, category: $("p-category").value });
        $("p-out").append(probeColumn("Coseno", data.cosine, data.min_sim), probeColumn("Re-ranking", data.rerank, data.rerank_min));
        $("p-result").hidden = false;
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
