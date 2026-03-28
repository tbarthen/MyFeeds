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

    function buildPluralPattern(word) {
        var lower = word.toLowerCase();
        if (lower.length < 3) return null;

        if (lower.endsWith("ies") && lower.length > 4 && !/[aeiou]/.test(lower[lower.length - 4])) {
            return word.slice(0, -3) + "(ies|y)";
        }
        if (lower.endsWith("ves")) {
            return word.slice(0, -3) + "(ves|f|fe)";
        }
        if (lower.endsWith("ches") || lower.endsWith("shes")) {
            return word.slice(0, -2) + "(es)?";
        }
        if (lower.endsWith("ses") || lower.endsWith("xes") || lower.endsWith("zes")) {
            return word.slice(0, -2) + "(es)?";
        }
        if (lower.endsWith("s") && !lower.endsWith("ss") && !lower.endsWith("us")) {
            return word.slice(0, -1) + "s?";
        }
        if (lower.endsWith("y") && lower.length > 2 && !/[aeiou]/.test(lower[lower.length - 2])) {
            return word.slice(0, -1) + "(y|ies)";
        }
        if (lower.endsWith("fe")) {
            return word.slice(0, -2) + "(fe|ves)";
        }
        if (lower.endsWith("f") && !lower.endsWith("ff")) {
            return word.slice(0, -1) + "(f|ves)";
        }
        if (lower.endsWith("ch") || lower.endsWith("sh") || lower.endsWith("s") ||
            lower.endsWith("x") || lower.endsWith("z")) {
            return word + "(es)?";
        }
        return word + "s?";
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
        renderTermSource();
        renderChips();
        termFreeInput.value = "";
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
            var chip = { text: word, isRegex: false, plural: false };
            state.chips.push(chip);
            renderChips();
        }
    }

    function removeChipByText(text) {
        state.chips = state.chips.filter(function(c) {
            return c.text !== text;
        });
        renderChips();
    }

    function renderChips() {
        termChips.innerHTML = "";
        state.chips.forEach(function(chip, idx) {
            if (chip.text.includes("|") && !chip.isRegex && !chip.plural) {
                var parts = chip.text.split("|").filter(function(p) { return p; });
                parts.forEach(function(part) {
                    var sub = document.createElement("span");
                    sub.className = "term-sub-chip";
                    sub.textContent = part;
                    termChips.appendChild(sub);
                });
            } else {
                var el = document.createElement("span");
                var displayText = chip.text;
                if (chip.plural && !chip.isRegex) {
                    var pluralResult = buildPluralPattern(chip.text);
                    displayText = pluralResult || chip.text;
                }
                el.className = "term-chip" + (chip.isRegex ? " regex-chip" : "") + (chip.plural ? " plural-chip" : "");
                var textSpan = document.createElement("span");
                textSpan.className = "chip-text";
                textSpan.textContent = displayText;
                el.appendChild(textSpan);

                if (!chip.isRegex) {
                    var pluralBtn = document.createElement("span");
                    pluralBtn.className = "chip-plural" + (chip.plural ? " active" : "");
                    pluralBtn.textContent = "S/P";
                    pluralBtn.title = chip.plural ? "Disable singular/plural" : "Include singular/plural";
                    pluralBtn.addEventListener("click", function(e) {
                        e.stopPropagation();
                        chip.plural = !chip.plural;
                        renderChips();
                    });
                    el.appendChild(pluralBtn);
                }

                var remove = document.createElement("span");
                remove.className = "chip-remove";
                remove.textContent = "\u00D7";
                remove.addEventListener("click", function(e) {
                    e.stopPropagation();
                    state.chips.splice(idx, 1);
                    clearWordSelections();
                    renderChips();
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
        }
    });

    function buildPattern() {
        var existingTerms = state.selectedFilter.pattern
            ? state.selectedFilter.pattern.split("|").filter(function(t) { return t.trim(); })
            : [];

        var newTerms = state.chips.map(function(chip) {
            var term;
            if (chip.isRegex) {
                term = chip.text;
            } else if (chip.plural) {
                term = buildPluralPattern(chip.text) || escapeRegex(chip.text);
            } else {
                term = escapeRegex(chip.text);
            }
            if (wholeWordToggle.checked && !chip.isRegex) {
                term = "\\b" + term + "\\b";
            }
            return term;
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
            var text = termFreeInput.value.trim();
            state.chips.push({ text: text, isRegex: hasRegexMeta(text) });
            termFreeInput.value = "";
            renderChips();
        }
        showStep(2);
    });

    // ── Step 3: Test & Save ──

    function preparePatternForJS(pattern) {
        var flags = "gi";
        if (/^\(\?i\)/.test(pattern)) {
            pattern = pattern.replace(/^\(\?i\)/, "");
            flags = "gi";
        }
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
