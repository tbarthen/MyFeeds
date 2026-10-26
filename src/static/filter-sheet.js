document.addEventListener("DOMContentLoaded", function() {
    var overlay = document.getElementById("filterSheetOverlay");
    var sheet = document.getElementById("filterSheet");
    if (!overlay || !sheet) return;

    var closeBtn = document.getElementById("filterSheetClose");
    var filterSelect = document.getElementById("filterSelect");
    var filterNewForm = document.getElementById("filterNewForm");
    var newFilterNameInput = document.getElementById("newFilterName");
    var newFilterTarget = document.getElementById("newFilterTarget");
    var termSource = document.getElementById("termSource");
    var termAddBtn = document.getElementById("termAddBtn");
    var termChips = document.getElementById("termChips");
    var termFreeInput = document.getElementById("termFreeInput");
    var wholeWordToggle = document.getElementById("wholeWordToggle");
    var pluralToggle = document.getElementById("pluralToggle");
    var saveBtn = document.getElementById("testSaveBtn");
    var testResult = document.getElementById("testResult");
    var testMatchCount = document.getElementById("testMatchCount");
    var testPatternDisplay = document.getElementById("testPatternDisplay");
    var testError = document.getElementById("testError");

    var NEW_FILTER_VALUE = "__new__";
    var LAST_FILTER_KEY = "myfeeds.lastFilterId";
    var LONG_PRESS_MS = 500;
    var MOVE_TOLERANCE = 10;
    var COUNT_DEBOUNCE_MS = 300;

    var state = {
        articleTitle: "",
        articleSummary: "",
        filters: [],
        chips: [],
        selectedWords: []
    };

    var longPressGhost = false;

    // ── Regex helpers ──

    var REGEX_META = /[.*+?^${}()|[\]\\]/;
    var POSSESSIVE_SUFFIX = /['’]s$/i;
    var LEADING_PUNCT = /^['"(\[‘“«]+/;
    var TRAILING_PUNCT = /['"),.;:!?\]’”»]+$/;

    function escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function hasRegexMeta(str) {
        return REGEX_META.test(str);
    }

    function cleanSelectedWord(word) {
        return word
            .replace(LEADING_PUNCT, "")
            .replace(TRAILING_PUNCT, "")
            .replace(POSSESSIVE_SUFFIX, "");
    }

    function isSimpleSPlural(text) {
        var lastWord = text.split(/\s+/).pop();
        return lastWord.length >= 3 && lastWord.endsWith("s") && !lastWord.endsWith("ss") && !lastWord.endsWith("us");
    }

    function splitTerms(pattern) {
        return pattern ? pattern.split("|").filter(function(t) { return t.trim(); }) : [];
    }

    function makeChip(text) {
        text = text.trim().toLowerCase();
        return { text: text, isRegex: hasRegexMeta(text) };
    }

    function chipToTerm(chip) {
        if (chip.isRegex) return chip.text;
        var term = escapeRegex(chip.text);
        if (pluralToggle.checked && isSimpleSPlural(chip.text)) {
            term = term.slice(0, -1) + "s?";
        }
        if (wholeWordToggle.checked) term = "\\b" + term + "\\b";
        return term;
    }

    function escapeHtml(str) {
        var div = document.createElement("div");
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // ── Opening the sheet ──

    document.querySelectorAll(".article-item").forEach(function(article) {
        var timer = null;
        var startX = 0;
        var startY = 0;
        var pressTouchId = null;

        function trackedTouch(touchList) {
            for (var i = 0; i < touchList.length; i++) {
                if (touchList[i].identifier === pressTouchId) return touchList[i];
            }
            return null;
        }

        function cancelPress() {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
            pressTouchId = null;
            article.classList.remove("long-pressing");
        }

        article.addEventListener("touchstart", function(e) {
            if (timer && trackedTouch(e.touches)) return;
            cancelPress();
            var touch = e.changedTouches[0];
            pressTouchId = touch.identifier;
            startX = touch.clientX;
            startY = touch.clientY;
            article.classList.add("long-pressing");
            timer = setTimeout(function() {
                timer = null;
                article.classList.remove("long-pressing");
                if ("vibrate" in navigator) navigator.vibrate(50);
                longPressGhost = true;
                openSheet(article);
            }, LONG_PRESS_MS);
        }, { passive: true });

        article.addEventListener("touchmove", function(e) {
            if (!timer) return;
            var touch = trackedTouch(e.changedTouches);
            if (!touch) return;
            var dx = touch.clientX - startX;
            var dy = touch.clientY - startY;
            if (Math.sqrt(dx * dx + dy * dy) > MOVE_TOLERANCE) cancelPress();
        }, { passive: true });

        article.addEventListener("touchend", cancelPress);
        article.addEventListener("touchcancel", cancelPress);

        article.addEventListener("contextmenu", function(e) {
            e.preventDefault();
            openSheet(article);
        });

        article.addEventListener("click", function(e) {
            if (longPressGhost) {
                e.preventDefault();
                e.stopPropagation();
                longPressGhost = false;
            }
        }, true);
    });

    document.querySelectorAll(".btn-kebab").forEach(function(btn) {
        btn.addEventListener("click", function(e) {
            e.stopPropagation();
            var article = btn.closest(".article-item");
            if (article) openSheet(article);
        });
    });

    function openSheet(articleEl) {
        var titleEl = articleEl.querySelector(".article-title");
        var summaryEl = articleEl.querySelector(".article-summary");
        state.articleTitle = titleEl ? (titleEl.textContent || "").trim() : "";
        state.articleSummary = summaryEl ? (summaryEl.textContent || "").trim() : "";
        state.chips = [];
        state.selectedWords = [];

        termFreeInput.value = "";
        newFilterNameInput.value = "";
        wholeWordToggle.checked = false;
        pluralToggle.checked = false;
        testError.style.display = "none";
        saveBtn.textContent = "Save";

        renderTermSource();
        renderChips();
        loadFilters();

        overlay.classList.add("active");
        closeBtn.focus();
    }

    function closeSheet() {
        longPressGhost = false;
        overlay.classList.remove("active");
    }

    closeBtn.addEventListener("click", closeSheet);
    overlay.addEventListener("click", function(e) {
        if (e.target === overlay) closeSheet();
    });

    // ── Filter picker ──

    function loadFilters() {
        filterSelect.innerHTML = "";
        fetch("/api/filters")
            .then(function(r) {
                if (!r.ok) throw new Error("Failed to load filters");
                return r.json();
            })
            .then(function(filters) {
                state.filters = filters;
                renderFilterSelect(filters);
                refreshPreview();
            })
            .catch(function() {
                state.filters = [];
                renderFilterSelect([]);
                showError("Could not load filters.");
            });
    }

    function renderFilterSelect(filters) {
        filterSelect.innerHTML = "";
        filters.forEach(function(f) {
            var opt = document.createElement("option");
            opt.value = String(f.id);
            opt.textContent = f.name + " (" + splitTerms(f.pattern).length + " terms)";
            filterSelect.appendChild(opt);
        });
        var newOpt = document.createElement("option");
        newOpt.value = NEW_FILTER_VALUE;
        newOpt.textContent = "+ New filter…";
        filterSelect.appendChild(newOpt);

        var remembered = readLastFilterId();
        var hasRemembered = filters.some(function(f) { return String(f.id) === remembered; });
        filterSelect.value = hasRemembered ? remembered : (filters.length ? String(filters[0].id) : NEW_FILTER_VALUE);
        syncNewFilterForm();
    }

    function readLastFilterId() {
        try { return localStorage.getItem(LAST_FILTER_KEY); } catch (e) { return null; }
    }

    function rememberFilterId(id) {
        try { localStorage.setItem(LAST_FILTER_KEY, String(id)); } catch (e) {}
    }

    function isNewFilter() {
        return filterSelect.value === NEW_FILTER_VALUE;
    }

    function selectedFilter() {
        var id = filterSelect.value;
        for (var i = 0; i < state.filters.length; i++) {
            if (String(state.filters[i].id) === id) return state.filters[i];
        }
        return null;
    }

    function currentTarget() {
        var f = selectedFilter();
        return f ? f.target : newFilterTarget.value;
    }

    function syncNewFilterForm() {
        filterNewForm.style.display = isNewFilter() ? "" : "none";
        if (isNewFilter()) newFilterNameInput.focus();
    }

    filterSelect.addEventListener("change", function() {
        syncNewFilterForm();
        refreshPreview();
    });
    newFilterTarget.addEventListener("change", refreshPreview);
    newFilterNameInput.addEventListener("input", updateSaveState);

    // ── Word selection ──

    function renderTermSource() {
        termSource.innerHTML = "";
        appendWordGroup("Title", state.articleTitle, "title");
        appendWordGroup("Summary", state.articleSummary, "summary");
    }

    function appendWordGroup(labelText, text, group) {
        if (!text) return;
        var label = document.createElement("span");
        label.className = "term-source-label";
        label.textContent = labelText;
        termSource.appendChild(label);

        var container = document.createElement("div");
        container.className = "term-word-container";
        var wordIndex = 0;
        text.split(/\s+/).forEach(function(word) {
            if (!word) return;
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "term-word";
            btn.textContent = word;
            btn.dataset.group = group;
            btn.dataset.idx = wordIndex++;
            btn.addEventListener("click", function() { handleWordClick(btn); });
            container.appendChild(btn);
        });
        termSource.appendChild(container);
    }

    function handleWordClick(btn) {
        var group = btn.dataset.group;
        var idx = parseInt(btn.dataset.idx, 10);
        if (btn.classList.contains("selected")) {
            deselectWord(btn, idx);
        } else {
            selectWord(btn, group, idx);
        }
        termAddBtn.disabled = state.selectedWords.length === 0;
    }

    function isAdjacentToSelection(group, idx) {
        var sel = state.selectedWords;
        if (!sel.length) return false;
        var first = sel[0];
        var last = sel[sel.length - 1];
        return (first.group === group && Math.abs(first.idx - idx) === 1) ||
               (last.group === group && Math.abs(last.idx - idx) === 1);
    }

    function selectWord(btn, group, idx) {
        if (!isAdjacentToSelection(group, idx)) clearSelection();
        btn.classList.add("selected");
        state.selectedWords.push({ el: btn, group: group, idx: idx });
        state.selectedWords.sort(function(a, b) { return a.idx - b.idx; });
        updateConnectedClasses();
    }

    function deselectWord(btn, idx) {
        var sel = state.selectedWords;
        if (sel.length <= 1) {
            clearSelection();
            return;
        }
        var isEdge = idx === sel[0].idx || idx === sel[sel.length - 1].idx;
        var keep;
        if (isEdge) {
            keep = sel.filter(function(s) { return s.idx !== idx; });
        } else {
            var before = sel.filter(function(s) { return s.idx < idx; });
            var after = sel.filter(function(s) { return s.idx > idx; });
            keep = before.length >= after.length ? before : after;
        }
        clearSelection();
        keep.forEach(function(s) { s.el.classList.add("selected"); });
        state.selectedWords = keep;
        updateConnectedClasses();
    }

    function clearSelection() {
        state.selectedWords.forEach(function(s) {
            s.el.classList.remove("selected", "connected-left", "connected-right");
        });
        state.selectedWords = [];
    }

    function updateConnectedClasses() {
        var sel = state.selectedWords;
        sel.forEach(function(s) { s.el.classList.remove("connected-left", "connected-right"); });
        for (var i = 1; i < sel.length; i++) {
            if (sel[i].idx === sel[i - 1].idx + 1) {
                sel[i].el.classList.add("connected-left");
                sel[i - 1].el.classList.add("connected-right");
            }
        }
    }

    function getSelectedPhrase() {
        return state.selectedWords
            .map(function(s) { return cleanSelectedWord(s.el.textContent); })
            .filter(function(w) { return w; })
            .join(" ");
    }

    termAddBtn.addEventListener("click", function() {
        var phrase = getSelectedPhrase();
        if (!phrase) return;
        addChip(phrase);
        clearSelection();
        termAddBtn.disabled = true;
    });

    // ── Chips ──

    function addChip(text) {
        state.chips.push(makeChip(text));
        renderChips();
        refreshPreview();
    }

    function flushFreeInput() {
        var text = termFreeInput.value.trim();
        if (!text) return;
        termFreeInput.value = "";
        addChip(text);
    }

    termFreeInput.addEventListener("keydown", function(e) {
        if (e.key === "Enter") {
            e.preventDefault();
            flushFreeInput();
        }
    });
    termFreeInput.addEventListener("input", updateSaveState);

    function renderChips() {
        if (termChips.querySelector(".chip-edit-input")) return;
        termChips.innerHTML = "";
        state.chips.forEach(function(chip, idx) {
            var el = document.createElement("span");
            el.className = "term-chip" + (chip.isRegex ? " regex-chip" : "");

            var label = document.createElement("span");
            label.className = "chip-label";
            label.textContent = chipToTerm(chip);
            label.addEventListener("click", function(e) {
                e.stopPropagation();
                startChipEdit(el, chip, idx);
            });
            el.appendChild(label);

            var remove = document.createElement("button");
            remove.type = "button";
            remove.className = "chip-remove";
            remove.textContent = "×";
            remove.setAttribute("aria-label", "Remove");
            remove.addEventListener("click", function(e) {
                e.stopPropagation();
                state.chips.splice(idx, 1);
                renderChips();
                refreshPreview();
            });
            el.appendChild(remove);

            termChips.appendChild(el);
        });
        updateSaveState();
    }

    function startChipEdit(el, chip, idx) {
        var label = el.querySelector(".chip-label");
        if (!label) return;
        el.classList.add("term-chip-editing");
        var input = document.createElement("input");
        input.type = "text";
        input.className = "chip-edit-input";
        input.value = chip.text;
        input.addEventListener("blur", function() {
            var newText = input.value.trim();
            if (newText) {
                state.chips[idx] = makeChip(newText);
            } else {
                state.chips.splice(idx, 1);
            }
            renderChips();
            refreshPreview();
        });
        input.addEventListener("keydown", function(e) {
            if (e.key === "Enter") input.blur();
            if (e.key === "Escape") {
                input.value = chip.text;
                input.blur();
            }
        });
        label.replaceWith(input);
        input.focus();
        input.select();
    }

    pluralToggle.addEventListener("change", function() { renderChips(); refreshPreview(); });
    wholeWordToggle.addEventListener("change", function() { renderChips(); refreshPreview(); });

    // ── Pattern + live preview ──

    function buildPattern() {
        var f = selectedFilter();
        var terms = splitTerms(f ? f.pattern : "");
        state.chips.forEach(function(chip) { terms.push(chipToTerm(chip)); });
        return terms.join("|");
    }

    function compileForPreview(pattern) {
        return new RegExp(pattern.replace(/\(\?i\)/g, ""), "gi");
    }

    var countTimer = null;
    var countToken = 0;

    function setMatchCount(text, muted) {
        testMatchCount.textContent = text;
        testMatchCount.classList.toggle("count-muted", !!muted);
    }

    function scheduleMatchCount(pattern) {
        clearTimeout(countTimer);
        var token = ++countToken;
        setMatchCount("Counting matches…", true);
        countTimer = setTimeout(function() {
            fetch("/api/filters/match-count", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ pattern: pattern, target: currentTarget() })
            }).then(function(r) {
                if (!r.ok) return r.json().then(function(d) { throw new Error(d.error); });
                return r.json();
            }).then(function(data) {
                if (token !== countToken) return;
                var n = data.count;
                setMatchCount("Would filter " + n + (n === 1 ? " unread article" : " unread articles"), n === 0);
            }).catch(function() {
                if (token !== countToken) return;
                setMatchCount("Couldn't count matches", true);
            });
        }, COUNT_DEBOUNCE_MS);
    }

    function refreshPreview() {
        var pattern = buildPattern();
        testPatternDisplay.textContent = pattern;
        testError.style.display = "none";

        if (!pattern) {
            testResult.innerHTML = '<span class="no-match">Pick words above or type a term</span>';
            countToken++;
            setMatchCount("", true);
            updateSaveState();
            return;
        }

        var regex;
        try {
            regex = compileForPreview(pattern);
        } catch (e) {
            showError("Invalid regex: " + e.message);
            testResult.innerHTML = '<span class="no-match">Cannot test — fix the pattern</span>';
            countToken++;
            setMatchCount("", true);
            updateSaveState();
            return;
        }

        var html = '<div class="test-section"><div class="test-section-label">Title</div><div>' +
            highlightMatches(state.articleTitle, regex) + '</div></div>';
        if (state.articleSummary) {
            html += '<div class="test-section"><div class="test-section-label">Summary</div><div>' +
                highlightMatches(state.articleSummary, regex) + '</div></div>';
        }
        testResult.innerHTML = html;

        scheduleMatchCount(pattern);
        updateSaveState();
    }

    function highlightMatches(text, regex) {
        if (!text) return '<span class="no-match">No text</span>';
        regex.lastIndex = 0;
        var result = "";
        var lastIndex = 0;
        var match;
        var hasMatch = false;

        while ((match = regex.exec(text)) !== null) {
            if (match[0] === "") {
                regex.lastIndex++;
                continue;
            }
            hasMatch = true;
            result += escapeHtml(text.slice(lastIndex, match.index));
            result += "<mark>" + escapeHtml(match[0]) + "</mark>";
            lastIndex = regex.lastIndex;
        }
        result += escapeHtml(text.slice(lastIndex));

        if (!hasMatch) return '<span class="no-match">' + escapeHtml(text) + ' (no match)</span>';
        return result;
    }

    function showError(message) {
        testError.textContent = message;
        testError.style.display = "";
    }

    // ── Save ──

    function hasPendingTerms() {
        return state.chips.length > 0 || termFreeInput.value.trim() !== "";
    }

    function updateSaveState() {
        var ready = hasPendingTerms();
        if (isNewFilter() && !newFilterNameInput.value.trim()) ready = false;
        saveBtn.disabled = !ready;
    }

    function duplicateTerms() {
        var f = selectedFilter();
        if (!f) return [];
        var existing = splitTerms(f.pattern).map(function(t) { return t.trim().toLowerCase(); });
        return state.chips
            .filter(function(chip) { return existing.indexOf(chipToTerm(chip).toLowerCase()) !== -1; })
            .map(function(chip) { return chip.text; });
    }

    saveBtn.addEventListener("click", function() {
        flushFreeInput();
        if (!state.chips.length) return;

        var pattern = buildPattern();
        try {
            compileForPreview(pattern);
        } catch (e) {
            showError("Invalid regex: " + e.message);
            return;
        }

        var dupes = duplicateTerms();
        if (dupes.length) {
            showError("Already in this filter: " + dupes.join(", "));
            return;
        }

        saveBtn.disabled = true;
        saveBtn.textContent = "Saving...";

        var request;
        if (isNewFilter()) {
            request = fetch("/api/filters", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: newFilterNameInput.value.trim(),
                    pattern: pattern,
                    target: newFilterTarget.value
                })
            });
        } else {
            request = fetch("/api/filters/" + filterSelect.value, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ pattern: pattern })
            });
        }

        request.then(function(r) {
            if (!r.ok) return r.json().then(function(d) { throw new Error(d.error); });
            return r.json();
        }).then(function(data) {
            rememberFilterId(data.id);
            window.location.href = "/filters#filter-" + data.id;
        }).catch(function(err) {
            showError(err.message);
            saveBtn.disabled = false;
            saveBtn.textContent = "Save";
        });
    });
});
