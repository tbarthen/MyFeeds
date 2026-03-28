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
    var termChips = document.getElementById("termChips");
    var termFreeInput = document.getElementById("termFreeInput");
    var wholeWordToggle = document.getElementById("wholeWordToggle");
    var advancedToggle = document.getElementById("advancedToggle");
    var termAdvanced = document.getElementById("termAdvanced");
    var termRawRegex = document.getElementById("termRawRegex");
    var termBackBtn = document.getElementById("termBackBtn");
    var termNextBtn = document.getElementById("termNextBtn");
    var testBackBtn = document.getElementById("testBackBtn");
    var testSaveBtn = document.getElementById("testSaveBtn");
    var testResult = document.getElementById("testResult");
    var testPatternDisplay = document.getElementById("testPatternDisplay");
    var testError = document.getElementById("testError");
    var dots = overlay.querySelectorAll(".dot");

    var state = {
        articleEl: null,
        articleTitle: "",
        articleSummary: "",
        filters: [],
        selectedFilter: null,
        isNewFilter: false,
        chips: [],
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

        showStep(0);
        loadFilters();
        overlay.classList.add("active");
        requestAnimationFrame(function() {
            overlay.style.opacity = "1";
        });
        closeBtn.focus();
    }

    function closeSheet() {
        overlay.style.opacity = "0";
        sheet.style.transform = "";
        setTimeout(function() {
            overlay.classList.remove("active");
            overlay.style.opacity = "";
            filterPickNewForm.style.display = "none";
            filterPickNewBtn.style.display = "";
            termAdvanced.style.display = "none";
            wholeWordToggle.checked = false;
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

    // Mouse drag for desktop
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

        if (n === 1) renderTermStep();
        if (n === 2) runTest();
    }

    // ── Step 1: Pick Filter ──

    function loadFilters() {
        fetch("/api/filters")
            .then(function(r) { return r.json(); })
            .then(function(filters) {
                state.filters = filters;
                renderFilterList(filters);
            });
    }

    function renderFilterList(filters) {
        filterPickList.innerHTML = "";
        filters.forEach(function(f) {
            var row = document.createElement("div");
            row.className = "filter-pick-row";
            row.innerHTML = '<span class="filter-pick-name">' + escapeHtml(f.name) + '</span>' +
                '<span class="filter-pick-terms">' + countTerms(f.pattern) + ' terms</span>';
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
        renderTermSource();
        renderChips();
        termFreeInput.value = "";
        termAdvanced.style.display = "none";
        updateRawRegex();
    }

    function renderTermSource() {
        termSource.innerHTML = "";

        if (state.articleTitle) {
            var titleLabel = document.createElement("span");
            titleLabel.className = "term-source-label";
            titleLabel.textContent = "Title";
            termSource.appendChild(titleLabel);
            termSource.appendChild(wrapWords(state.articleTitle));
        }

        if (state.articleSummary) {
            var summaryLabel = document.createElement("span");
            summaryLabel.className = "term-source-label";
            summaryLabel.textContent = "Summary";
            termSource.appendChild(summaryLabel);
            termSource.appendChild(wrapWords(state.articleSummary));
        }
    }

    function wrapWords(text) {
        var container = document.createElement("div");
        container.style.userSelect = "none";
        var words = text.split(/(\s+)/);
        words.forEach(function(word) {
            if (/^\s+$/.test(word)) {
                container.appendChild(document.createTextNode(word));
                return;
            }
            var span = document.createElement("span");
            span.className = "term-word";
            span.textContent = word;
            span.addEventListener("click", function() {
                handleWordClick(span);
            });
            container.appendChild(span);
        });
        return container;
    }

    function handleWordClick(span) {
        var word = span.textContent.trim();
        if (!word) return;

        if (span.classList.contains("selected")) {
            span.classList.remove("selected");
            removeChipByText(word);
            return;
        }

        var prev = span.previousElementSibling;
        var merged = false;
        if (prev && prev.classList.contains("selected")) {
            var lastChip = state.chips[state.chips.length - 1];
            if (lastChip && !lastChip.isRegex) {
                lastChip.text += " " + word;
                span.classList.add("selected");
                renderChips();
                merged = true;
            }
        }

        if (!merged) {
            span.classList.add("selected");
            state.chips.push({ text: word, isRegex: false });
            renderChips();
        }
        updateRawRegex();
    }

    function removeChipByText(text) {
        state.chips = state.chips.filter(function(c) {
            return c.text !== text;
        });
        renderChips();
        updateRawRegex();
    }

    function renderChips() {
        termChips.innerHTML = "";
        state.chips.forEach(function(chip, idx) {
            if (chip.text.includes("|") && !chip.isRegex) {
                var parts = chip.text.split("|").filter(function(p) { return p; });
                parts.forEach(function(part) {
                    var sub = document.createElement("span");
                    sub.className = "term-sub-chip";
                    sub.textContent = part;
                    termChips.appendChild(sub);
                });
            } else {
                var el = document.createElement("span");
                el.className = "term-chip" + (chip.isRegex ? " regex-chip" : "");
                var textSpan = document.createElement("span");
                textSpan.className = "chip-text";
                textSpan.textContent = chip.text;
                el.appendChild(textSpan);

                var remove = document.createElement("span");
                remove.className = "chip-remove";
                remove.textContent = "\u00D7";
                remove.addEventListener("click", function(e) {
                    e.stopPropagation();
                    state.chips.splice(idx, 1);
                    clearWordSelections();
                    renderChips();
                    updateRawRegex();
                });
                el.appendChild(remove);

                el.addEventListener("click", function() {
                    startChipEdit(el, chip, idx);
                });
                termChips.appendChild(el);
            }
        });
    }

    function startChipEdit(el, chip, idx) {
        el.innerHTML = "";
        el.classList.add("term-chip-editing");
        var input = document.createElement("input");
        input.type = "text";
        input.value = chip.text;
        input.addEventListener("blur", function() {
            finishChipEdit(el, chip, idx, input.value);
        });
        input.addEventListener("keydown", function(e) {
            if (e.key === "Enter") input.blur();
            if (e.key === "Escape") {
                input.value = chip.text;
                input.blur();
            }
        });
        el.appendChild(input);
        input.focus();
        input.select();
    }

    function finishChipEdit(el, chip, idx, newText) {
        newText = newText.trim();
        if (!newText) {
            state.chips.splice(idx, 1);
        } else {
            chip.text = newText;
            chip.isRegex = hasRegexMeta(newText);
        }
        clearWordSelections();
        renderChips();
        updateRawRegex();
    }

    function clearWordSelections() {
        termSource.querySelectorAll(".term-word.selected").forEach(function(w) {
            w.classList.remove("selected");
        });
    }

    termFreeInput.addEventListener("keydown", function(e) {
        if (e.key === "Enter" && termFreeInput.value.trim()) {
            var text = termFreeInput.value.trim();
            state.chips.push({ text: text, isRegex: hasRegexMeta(text) });
            termFreeInput.value = "";
            renderChips();
            updateRawRegex();
        }
    });

    function buildPattern() {
        var existingTerms = state.selectedFilter.pattern
            ? state.selectedFilter.pattern.split("|").filter(function(t) { return t.trim(); })
            : [];

        if (termAdvanced.style.display !== "none" && termRawRegex.value.trim()) {
            return termRawRegex.value.trim();
        }

        var newTerms = state.chips.map(function(chip) {
            var term = chip.isRegex ? chip.text : escapeRegex(chip.text);
            if (wholeWordToggle.checked && !chip.isRegex) {
                term = "\\b" + term + "\\b";
            }
            return term;
        });

        var allTerms = existingTerms.concat(newTerms);
        return allTerms.join("|");
    }

    function updateRawRegex() {
        termRawRegex.value = buildPattern();
    }

    wholeWordToggle.addEventListener("change", updateRawRegex);

    advancedToggle.addEventListener("click", function() {
        var showing = termAdvanced.style.display !== "none";
        termAdvanced.style.display = showing ? "none" : "";
        if (!showing) {
            updateRawRegex();
            termRawRegex.focus();
        }
    });

    termBackBtn.addEventListener("click", function() {
        showStep(0);
    });

    termNextBtn.addEventListener("click", function() {
        if (state.chips.length === 0 && termFreeInput.value.trim() === "" &&
            (termAdvanced.style.display === "none" || !termRawRegex.value.trim())) {
            termFreeInput.focus();
            return;
        }
        if (termFreeInput.value.trim()) {
            var text = termFreeInput.value.trim();
            state.chips.push({ text: text, isRegex: hasRegexMeta(text) });
            termFreeInput.value = "";
            renderChips();
            updateRawRegex();
        }
        showStep(2);
    });

    // ── Step 3: Test & Save ──

    function runTest() {
        var pattern = buildPattern();
        testPatternDisplay.textContent = pattern;
        testError.style.display = "none";

        try {
            var regex = new RegExp(pattern, "gi");
        } catch(e) {
            testError.textContent = "Invalid regex: " + e.message;
            testError.style.display = "";
            testResult.innerHTML = '<span class="no-match">Cannot test — fix the pattern</span>';
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

    testSaveBtn.addEventListener("click", function() {
        var pattern = buildPattern();

        try {
            new RegExp(pattern);
        } catch(e) {
            testError.textContent = "Invalid regex: " + e.message;
            testError.style.display = "";
            return;
        }

        if (checkDuplicateTerms(pattern)) return;

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

    function checkDuplicateTerms(fullPattern) {
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
