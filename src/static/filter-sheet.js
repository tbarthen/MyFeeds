document.addEventListener("DOMContentLoaded", function() {
    var overlay = document.getElementById("filterSheetOverlay");
    var sheet = document.getElementById("filterSheet");
    if (!overlay || !sheet) return;

    var closeBtn = document.getElementById("filterSheetClose");
    var stepPickFilter = document.getElementById("stepPickFilter");
    var stepSelectTerm = document.getElementById("stepSelectTerm");
    var stepTestSave = document.getElementById("stepTestSave");
    var filterPickList = document.getElementById("filterPickList");
    var filterPickNewBtn = document.getElementById("filterPickNewBtn");
    var filterPickNewForm = document.getElementById("filterPickNewForm");
    var newFilterNameInput = document.getElementById("newFilterName");
    var newFilterTarget = document.getElementById("newFilterTarget");
    var filterPickNewConfirm = document.getElementById("filterPickNewConfirm");
    var termSource = document.getElementById("termSource");
    var termAddBtn = document.getElementById("termAddBtn");
    var termChips = document.getElementById("termChips");
    var termFreeInput = document.getElementById("termFreeInput");
    var wholeWordToggle = document.getElementById("wholeWordToggle");
    var pluralToggle = document.getElementById("pluralToggle");
    var termBackBtn = document.getElementById("termBackBtn");
    var termNextBtn = document.getElementById("termNextBtn");
    var testBackBtn = document.getElementById("testBackBtn");
    var testSaveBtn = document.getElementById("testSaveBtn");
    var testRetestBtn = document.getElementById("testRetestBtn");
    var testResult = document.getElementById("testResult");
    var testPatternDisplay = document.getElementById("testPatternDisplay");
    var testError = document.getElementById("testError");
    var sheetFooter = document.getElementById("filterSheetFooter");
    var dots = overlay.querySelectorAll(".dot");

    var state = {
        articleEl: null,
        articleTitle: "",
        articleSummary: "",
        filters: [],
        selectedFilter: null,
        isNewFilter: false,
        chips: [],
        selectedWords: [],
        currentStep: 0
    };

    var LONG_PRESS_MS = 500;
    var MOVE_TOLERANCE = 10;
    var longPressGhost = false;

    function escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function hasRegexMeta(str) {
        return /[.*+?^${}()|[\]\\]/.test(str);
    }

    function countTerms(pattern) {
        if (!pattern) return 0;
        try {
            return pattern.split("|").filter(function(t) { return t.trim(); }).length;
        } catch(e) {
            return 0;
        }
    }

    function isSimpleSPlural(text) {
        var lastWord = text.split(/\s+/).pop();
        return lastWord.length >= 3 && lastWord.endsWith("s") && !lastWord.endsWith("ss") && !lastWord.endsWith("us");
    }

    // ── Long Press ──

    document.querySelectorAll(".article-item").forEach(function(article) {
        var timer = null;
        var startX = 0;
        var startY = 0;

        function cancelPress() {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
            article.classList.remove("long-pressing");
        }

        article.addEventListener("touchstart", function(e) {
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
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
            var dx = e.touches[0].clientX - startX;
            var dy = e.touches[0].clientY - startY;
            if (Math.sqrt(dx * dx + dy * dy) > MOVE_TOLERANCE) {
                cancelPress();
            }
        }, { passive: true });

        article.addEventListener("touchend", function() {
            cancelPress();
        });

        article.addEventListener("touchcancel", function() {
            cancelPress();
        });

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

    // ── Kebab Button ──

    document.querySelectorAll(".btn-kebab").forEach(function(btn) {
        btn.addEventListener("click", function(e) {
            e.stopPropagation();
            var article = btn.closest(".article-item");
            if (article) openSheet(article);
        });
    });

    // ── Sheet Open/Close ──

    function openSheet(articleEl) {
        state.articleEl = articleEl;
        var titleEl = articleEl.querySelector(".article-title");
        var summaryEl = articleEl.querySelector(".article-summary");
        state.articleTitle = titleEl ? (titleEl.textContent || "").trim() : "";
        state.articleSummary = summaryEl ? (summaryEl.textContent || "").trim() : "";
        state.selectedFilter = null;
        state.isNewFilter = false;
        state.chips = [];
        state.selectedWords = [];

        showStep(0);
        loadFilters();
        overlay.classList.add("active");
        requestAnimationFrame(function() {
            overlay.style.opacity = "1";
        });
        closeBtn.focus();
    }

    function closeSheet() {
        longPressGhost = false;
        overlay.style.opacity = "0";
        sheet.style.transform = "";
        setTimeout(function() {
            overlay.classList.remove("active");
            overlay.style.opacity = "";
            filterPickNewForm.style.display = "none";
            filterPickNewBtn.style.display = "";
            wholeWordToggle.checked = false;
            pluralToggle.checked = false;
        }, 200);
    }

    closeBtn.addEventListener("click", closeSheet);

    overlay.addEventListener("click", function(e) {
        if (e.target === overlay) closeSheet();
    });

    // ── Drag to Dismiss ──

    var dragStartY = 0;
    var isDragging = false;
    var sheetHandle = sheet.querySelector(".filter-sheet-handle");

    sheetHandle.addEventListener("touchstart", function(e) {
        dragStartY = e.touches[0].clientY;
        isDragging = true;
        sheet.style.transition = "none";
    }, { passive: true });

    sheetHandle.addEventListener("touchmove", function(e) {
        if (!isDragging) return;
        var dy = e.touches[0].clientY - dragStartY;
        if (dy > 0) {
            sheet.style.transform = "translateY(" + dy + "px)";
        }
    }, { passive: true });

    sheetHandle.addEventListener("touchend", function(e) {
        if (!isDragging) return;
        isDragging = false;
        sheet.style.transition = "";
        var dy = e.changedTouches[0].clientY - dragStartY;
        if (dy > sheet.offsetHeight * 0.25) {
            closeSheet();
        } else {
            sheet.style.transform = "";
        }
    });

    sheetHandle.addEventListener("mousedown", function(e) {
        dragStartY = e.clientY;
        isDragging = true;
        sheet.style.transition = "none";

        function onMouseMove(e) {
            if (!isDragging) return;
            var dy = e.clientY - dragStartY;
            if (dy > 0) {
                sheet.style.transform = "translateY(" + dy + "px)";
            }
        }

        function onMouseUp(e) {
            isDragging = false;
            sheet.style.transition = "";
            var dy = e.clientY - dragStartY;
            if (dy > sheet.offsetHeight * 0.25) {
                closeSheet();
            } else {
                sheet.style.transform = "";
            }
            document.removeEventListener("mousemove", onMouseMove);
            document.removeEventListener("mouseup", onMouseUp);
        }

        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
    });

    // ── Step Navigation ──

    function showStep(n) {
        state.currentStep = n;
        stepPickFilter.style.display = n === 0 ? "" : "none";
        stepSelectTerm.style.display = n === 1 ? "" : "none";
        stepTestSave.style.display = n === 2 ? "" : "none";
        dots.forEach(function(d, i) {
            d.classList.toggle("active", i === n);
        });

        sheetFooter.style.display = n === 0 ? "none" : "flex";
        termBackBtn.style.display = n === 1 ? "" : "none";
        termNextBtn.style.display = n === 1 ? "" : "none";
        testBackBtn.style.display = n === 2 ? "" : "none";
        testRetestBtn.style.display = n === 2 ? "" : "none";
        testSaveBtn.style.display = n === 2 ? "" : "none";

        if (n === 1) renderTermStep();
        if (n === 2) runTest();
    }

    // ── Step 1: Pick Filter ──

    function loadFilters() {
        fetch("/api/filters")
            .then(function(r) {
                if (!r.ok) throw new Error("Failed to load filters");
                return r.json();
            })
            .then(function(filters) {
                state.filters = filters;
                renderFilterList(filters);
            })
            .catch(function() {
                filterPickList.innerHTML = "";
                var msg = document.createElement("p");
                msg.className = "empty-state";
                msg.textContent = "Could not load filters.";
                filterPickList.appendChild(msg);
            });
    }

    function renderFilterList(filters) {
        filterPickList.innerHTML = "";
        filters.forEach(function(f) {
            var row = document.createElement("div");
            row.className = "filter-pick-row";

            var nameSpan = document.createElement("span");
            nameSpan.className = "filter-pick-name";
            nameSpan.textContent = f.name;
            row.appendChild(nameSpan);

            var termsSpan = document.createElement("span");
            termsSpan.className = "filter-pick-terms";
            termsSpan.textContent = countTerms(f.pattern) + " terms";
            row.appendChild(termsSpan);

            row.addEventListener("click", function() {
                state.selectedFilter = f;
                state.isNewFilter = false;
                showStep(1);
            });
            filterPickList.appendChild(row);
        });
    }

    filterPickNewBtn.addEventListener("click", function() {
        filterPickNewBtn.style.display = "none";
        filterPickNewForm.style.display = "";
        newFilterNameInput.value = "";
        newFilterNameInput.focus();
    });

    filterPickNewConfirm.addEventListener("click", function() {
        var name = newFilterNameInput.value.trim();
        if (!name) {
            newFilterNameInput.focus();
            return;
        }
        state.selectedFilter = {
            id: null,
            name: name,
            pattern: "",
            target: newFilterTarget.value,
            is_active: true
        };
        state.isNewFilter = true;
        showStep(1);
    });

    // ── Step 2: Select Terms ──

    function renderTermStep() {
        state.selectedWords = [];
        renderTermSource();
        renderChips();
        termFreeInput.value = "";
        updateAddBtn();
    }

    function renderTermSource() {
        termSource.innerHTML = "";

        if (state.articleTitle) {
            var titleLabel = document.createElement("span");
            titleLabel.className = "term-source-label";
            titleLabel.textContent = "Title";
            termSource.appendChild(titleLabel);
            termSource.appendChild(wrapWords(state.articleTitle, "title"));
        }

        if (state.articleSummary) {
            var summaryLabel = document.createElement("span");
            summaryLabel.className = "term-source-label";
            summaryLabel.textContent = "Summary";
            termSource.appendChild(summaryLabel);
            termSource.appendChild(wrapWords(state.articleSummary, "summary"));
        }
    }

    function wrapWords(text, group) {
        var container = document.createElement("div");
        container.className = "term-word-container";
        var words = text.split(/(\s+)/);
        var wordIndex = 0;
        words.forEach(function(word) {
            if (/^\s+$/.test(word)) return;
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "term-word";
            btn.textContent = word;
            btn.dataset.group = group;
            btn.dataset.idx = wordIndex;
            wordIndex++;
            btn.addEventListener("click", function() {
                handleWordClick(btn);
            });
            container.appendChild(btn);
        });
        return container;
    }

    function handleWordClick(btn) {
        var group = btn.dataset.group;
        var idx = parseInt(btn.dataset.idx);

        if (btn.classList.contains("selected")) {
            deselectWord(btn, group, idx);
        } else {
            selectWord(btn, group, idx);
        }
        updateAddBtn();
    }

    function selectWord(btn, group, idx) {
        var sel = state.selectedWords;
        if (sel.length > 0) {
            var lastSel = sel[sel.length - 1];
            if (lastSel.group === group && Math.abs(lastSel.idx - idx) === 1) {
                btn.classList.add("selected");
                sel.push({ el: btn, group: group, idx: idx });
                sel.sort(function(a, b) { return a.idx - b.idx; });
                updateConnectedClasses();
                return;
            }
            var firstSel = sel[0];
            if (firstSel.group === group && Math.abs(firstSel.idx - idx) === 1) {
                btn.classList.add("selected");
                sel.push({ el: btn, group: group, idx: idx });
                sel.sort(function(a, b) { return a.idx - b.idx; });
                updateConnectedClasses();
                return;
            }
        }
        clearSelection();
        btn.classList.add("selected");
        state.selectedWords = [{ el: btn, group: group, idx: idx }];
        updateConnectedClasses();
    }

    function deselectWord(btn, group, idx) {
        var sel = state.selectedWords;
        if (sel.length <= 1) {
            clearSelection();
            return;
        }
        var first = sel[0];
        var last = sel[sel.length - 1];
        if (idx === first.idx || idx === last.idx) {
            btn.classList.remove("selected");
            btn.classList.remove("connected-left", "connected-right");
            state.selectedWords = sel.filter(function(s) { return s.idx !== idx; });
            updateConnectedClasses();
        } else {
            var beforeSplit = sel.filter(function(s) { return s.idx < idx; });
            var afterSplit = sel.filter(function(s) { return s.idx > idx; });
            clearSelection();
            var keep = beforeSplit.length >= afterSplit.length ? beforeSplit : afterSplit;
            keep.forEach(function(s) { s.el.classList.add("selected"); });
            state.selectedWords = keep;
            updateConnectedClasses();
        }
    }

    function clearSelection() {
        state.selectedWords.forEach(function(s) {
            s.el.classList.remove("selected", "connected-left", "connected-right");
        });
        state.selectedWords = [];
    }

    function updateConnectedClasses() {
        var sel = state.selectedWords;
        sel.forEach(function(s) {
            s.el.classList.remove("connected-left", "connected-right");
        });
        for (var i = 0; i < sel.length; i++) {
            if (i > 0 && sel[i].idx === sel[i - 1].idx + 1) {
                sel[i].el.classList.add("connected-left");
                sel[i - 1].el.classList.add("connected-right");
            }
        }
    }

    function getSelectedPhrase() {
        if (state.selectedWords.length === 0) return "";
        var sorted = state.selectedWords.slice().sort(function(a, b) { return a.idx - b.idx; });
        return sorted.map(function(s) { return s.el.textContent; }).join(" ");
    }

    function updateAddBtn() {
        termAddBtn.disabled = state.selectedWords.length === 0;
    }

    // ── Add Button ──

    termAddBtn.addEventListener("click", function() {
        var phrase = getSelectedPhrase();
        if (!phrase) return;
        commitChip(phrase);
    });

    function commitChip(text) {
        text = text.toLowerCase();
        state.chips.push({ text: text, isRegex: hasRegexMeta(text) });
        clearSelection();
        updateAddBtn();
        renderChips();
    }

    // ── Chips ──

    function chipDisplayText(chip) {
        if (chip.isRegex) return chip.text;
        var display = chip.text;
        if (pluralToggle.checked && isSimpleSPlural(display)) {
            display = display + "?";
        }
        if (wholeWordToggle.checked) {
            display = "\\b" + display + "\\b";
        }
        return display;
    }

    function renderChips() {
        termChips.innerHTML = "";
        state.chips.forEach(function(chip, idx) {
            var el = document.createElement("span");
            el.className = "term-chip" + (chip.isRegex ? " regex-chip" : "");

            var label = document.createElement("span");
            label.className = "chip-label";
            label.textContent = chipDisplayText(chip);
            label.addEventListener("click", function(e) {
                e.stopPropagation();
                startChipEdit(el, chip, idx);
            });
            el.appendChild(label);

            var remove = document.createElement("button");
            remove.type = "button";
            remove.className = "chip-remove";
            remove.textContent = "\u00D7";
            remove.setAttribute("aria-label", "Remove");
            remove.addEventListener("click", function(e) {
                e.stopPropagation();
                state.chips.splice(idx, 1);
                renderChips();
            });
            el.appendChild(remove);

            termChips.appendChild(el);
        });
    }

    pluralToggle.addEventListener("change", function() {
        renderChips();
    });

    wholeWordToggle.addEventListener("change", function() {
        renderChips();
    });

    function startChipEdit(el, chip, idx) {
        var label = el.querySelector(".chip-label");
        if (!label) return;
        el.classList.add("term-chip-editing");
        var input = document.createElement("input");
        input.type = "text";
        input.className = "chip-edit-input";
        input.value = chip.text;
        input.addEventListener("blur", function() {
            finishChipEdit(chip, idx, input.value);
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

    function finishChipEdit(chip, idx, newText) {
        newText = newText.trim();
        if (!newText) {
            state.chips.splice(idx, 1);
        } else {
            chip.text = newText;
            chip.isRegex = hasRegexMeta(newText);
        }
        renderChips();
    }

    termFreeInput.addEventListener("keydown", function(e) {
        if (e.key === "Enter" && termFreeInput.value.trim()) {
            var text = termFreeInput.value.trim().toLowerCase();
            state.chips.push({ text: text, isRegex: hasRegexMeta(text) });
            termFreeInput.value = "";
            renderChips();
        }
    });

    function buildPattern() {
        var existingTerms = state.selectedFilter.pattern
            ? state.selectedFilter.pattern.split("|").filter(function(t) { return t.trim(); })
            : [];

        var newTerms = [];
        state.chips.forEach(function(chip) {
            if (chip.isRegex) {
                newTerms.push(chip.text);
            } else if (chip.text.includes("|")) {
                chip.text.split("|").forEach(function(part) {
                    var t = escapeRegex(part.trim());
                    if (wholeWordToggle.checked) t = "\\b" + t + "\\b";
                    if (t) newTerms.push(t);
                });
            } else {
                var t = escapeRegex(chip.text);
                if (pluralToggle.checked && isSimpleSPlural(chip.text)) {
                    t = t.slice(0, -1) + "s?";
                }
                if (wholeWordToggle.checked) t = "\\b" + t + "\\b";
                newTerms.push(t);
            }
        });

        var allTerms = existingTerms.concat(newTerms);
        return allTerms.join("|");
    }

    termBackBtn.addEventListener("click", function() {
        showStep(0);
    });

    termNextBtn.addEventListener("click", function() {
        if (state.chips.length === 0 && termFreeInput.value.trim() === "") {
            termFreeInput.focus();
            return;
        }
        if (termFreeInput.value.trim()) {
            var text = termFreeInput.value.trim().toLowerCase();
            state.chips.push({ text: text, isRegex: hasRegexMeta(text) });
            termFreeInput.value = "";
            renderChips();
        }
        showStep(2);
    });

    // ── Step 3: Test & Save ──

    function preparePatternForJS(pattern) {
        var flags = "gi";
        pattern = pattern.replace(/\(\?i\)/g, "");
        return { pattern: pattern, flags: flags };
    }

    function runTest() {
        var pattern = buildPattern();
        testPatternDisplay.textContent = pattern;
        testError.style.display = "none";

        var prepared = preparePatternForJS(pattern);
        try {
            var regex = new RegExp(prepared.pattern, prepared.flags);
        } catch(e) {
            testError.textContent = "Invalid regex: " + e.message;
            testError.style.display = "";
            testResult.innerHTML = '<span class="no-match">Cannot test \u2014 fix the pattern</span>';
            return;
        }

        var html = "";
        html += '<div class="test-section">';
        html += '<div class="test-section-label">Title</div>';
        html += '<div>' + highlightMatches(state.articleTitle, regex) + '</div>';
        html += '</div>';

        if (state.articleSummary) {
            html += '<div class="test-section">';
            html += '<div class="test-section-label">Summary</div>';
            html += '<div>' + highlightMatches(state.articleSummary, regex) + '</div>';
            html += '</div>';
        }

        testResult.innerHTML = html;
    }

    function highlightMatches(text, regex) {
        if (!text) return '<span class="no-match">No text</span>';
        regex.lastIndex = 0;
        var result = "";
        var lastIndex = 0;
        var match;
        var hasMatch = false;

        while ((match = regex.exec(text)) !== null) {
            hasMatch = true;
            result += escapeHtml(text.slice(lastIndex, match.index));
            result += "<mark>" + escapeHtml(match[0]) + "</mark>";
            lastIndex = regex.lastIndex;
            if (!regex.global) break;
        }
        result += escapeHtml(text.slice(lastIndex));

        if (!hasMatch) {
            return '<span class="no-match">' + escapeHtml(text) + ' (no match)</span>';
        }
        return result;
    }

    testBackBtn.addEventListener("click", function() {
        showStep(1);
    });

    testRetestBtn.addEventListener("click", function() {
        runTest();
    });

    testSaveBtn.addEventListener("click", function() {
        var pattern = buildPattern();

        var prepared = preparePatternForJS(pattern);
        try {
            new RegExp(prepared.pattern, prepared.flags);
        } catch(e) {
            testError.textContent = "Invalid regex: " + e.message;
            testError.style.display = "";
            return;
        }

        if (checkDuplicateTerms()) return;

        testSaveBtn.disabled = true;
        testSaveBtn.textContent = "Saving...";

        if (state.isNewFilter) {
            fetch("/api/filters", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: state.selectedFilter.name,
                    pattern: pattern,
                    target: state.selectedFilter.target
                })
            }).then(function(r) {
                if (!r.ok) return r.json().then(function(d) { throw new Error(d.error); });
                return r.json();
            }).then(function(data) {
                window.location.href = "/filters#filter-" + data.id;
            }).catch(function(err) {
                testError.textContent = err.message;
                testError.style.display = "";
                testSaveBtn.disabled = false;
                testSaveBtn.textContent = "Save";
            });
        } else {
            fetch("/api/filters/" + state.selectedFilter.id, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ pattern: pattern })
            }).then(function(r) {
                if (!r.ok) return r.json().then(function(d) { throw new Error(d.error); });
                return r.json();
            }).then(function(data) {
                window.location.href = "/filters#filter-" + data.id;
            }).catch(function(err) {
                testError.textContent = err.message;
                testError.style.display = "";
                testSaveBtn.disabled = false;
                testSaveBtn.textContent = "Save";
            });
        }
    });

    function checkDuplicateTerms() {
        if (!state.selectedFilter.pattern || state.isNewFilter) return false;

        var existingTerms = state.selectedFilter.pattern.split("|").map(function(t) {
            return t.trim().toLowerCase();
        });

        var dupes = [];
        state.chips.forEach(function(chip) {
            var term = chip.isRegex ? chip.text : escapeRegex(chip.text);
            if (wholeWordToggle.checked && !chip.isRegex) {
                term = "\\b" + term + "\\b";
            }
            if (existingTerms.indexOf(term.toLowerCase()) !== -1) {
                dupes.push(chip.text);
            }
        });

        if (dupes.length > 0) {
            testError.textContent = "Already in this filter: " + dupes.join(", ");
            testError.style.display = "";
            return true;
        }
        return false;
    }

    // ── Utilities ──

    function escapeHtml(str) {
        var div = document.createElement("div");
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }
});
