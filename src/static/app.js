document.addEventListener("DOMContentLoaded", function() {
    // Check if we're in unread-only view (default when no param, or explicit unread=1)
    function isUnreadView() {
        return !window.location.search.includes("unread=0");
    }

    // Update sidebar unread counts after marking read/unread
    function updateUnreadCount(feedId, delta) {
        // Update the specific feed's count
        var feedRow = document.querySelector('.nav-row[data-feed-id="' + feedId + '"]');
        if (feedRow) {
            var countEl = feedRow.querySelector(".count");
            if (countEl) {
                var current = parseInt(countEl.textContent) || 0;
                var updated = Math.max(0, current + delta);
                countEl.textContent = updated;
                countEl.style.display = updated > 0 ? "" : "none";
            }
        }
        // Update "All Feeds" count
        var allRow = document.querySelector('.nav-row[data-feed-id="all"]');
        if (allRow) {
            var allCount = allRow.querySelector(".count");
            if (allCount) {
                var currentAll = parseInt(allCount.textContent) || 0;
                var updatedAll = Math.max(0, currentAll + delta);
                allCount.textContent = updatedAll;
                allCount.style.display = updatedAll > 0 ? "" : "none";
            }
        }
    }

    // Undo toast state
    var pendingUndo = null;
    var undoToast = document.getElementById("undoToast");
    var undoBtn = document.getElementById("undoBtn");
    var undoDismiss = document.getElementById("undoDismiss");
    var articleList = document.querySelector(".article-list");

    function collapseArticle(articleEl) {
        if (!articleEl) return;
        articleEl.style.maxHeight = articleEl.offsetHeight + "px";
        articleEl.offsetHeight; // Force reflow
        articleEl.classList.add("collapsing");
    }

    function expandArticle(articleEl) {
        if (!articleEl) return;
        articleEl.classList.remove("collapsing");
        articleEl.style.maxHeight = "";
    }

    function showUndoToast(articleId, feedId, articleEl) {
        // If there's a pending undo, remove that article permanently
        if (pendingUndo && pendingUndo.articleEl) {
            pendingUndo.articleEl.remove();
        }
        pendingUndo = { articleId: articleId, feedId: feedId, articleEl: articleEl };
        if (undoToast) {
            undoToast.classList.add("active");
        }
        if (articleList) {
            articleList.classList.add("has-toast");
        }
    }

    function hideUndoToast() {
        pendingUndo = null;
        if (undoToast) {
            undoToast.classList.remove("active");
        }
        if (articleList) {
            articleList.classList.remove("has-toast");
        }
    }

    // Undo button click
    if (undoBtn) {
        undoBtn.addEventListener("click", function() {
            if (!pendingUndo) return;
            var articleId = pendingUndo.articleId;
            var feedId = pendingUndo.feedId;
            var articleEl = pendingUndo.articleEl;

            fetch("/articles/" + articleId + "/unread", {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" }
            }).then(function() {
                updateUnreadCount(feedId, 1);
                if (articleEl) {
                    articleEl.classList.remove("is-read");
                    expandArticle(articleEl);
                }
                hideUndoToast();
            });
        });
    }

    // Dismiss button click
    if (undoDismiss) {
        undoDismiss.addEventListener("click", function() {
            if (pendingUndo && pendingUndo.articleEl) {
                pendingUndo.articleEl.remove();
            }
            hideUndoToast();
        });
    }

    // Handle marking article as read with flash and undo toast
    function markAsReadWithAnimation(article) {
        var articleId = article.dataset.id;
        var feedId = article.dataset.feedId;

        article.classList.add("just-read");
        setTimeout(function() {
            article.classList.remove("just-read");
            article.classList.add("is-read");
            // Only show undo toast in unread view (article will disappear)
            // In all view, user can just swipe to mark unread again
            if (isUnreadView()) {
                collapseArticle(article);
                showUndoToast(articleId, feedId, article);
            }
        }, 400);
    }

    // Mobile sidebar toggle
    const menuToggle = document.querySelector(".menu-toggle");
    const sidebarOverlay = document.querySelector(".sidebar-overlay");
    const app = document.querySelector(".app");

    function closeSidebar() {
        app.classList.remove("sidebar-open");
    }

    if (menuToggle) {
        menuToggle.addEventListener("click", function() {
            app.classList.toggle("sidebar-open");
        });
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener("click", closeSidebar);
    }

    // Close sidebar when clicking a nav link (mobile)
    document.querySelectorAll(".sidebar-nav a").forEach(function(link) {
        link.addEventListener("click", closeSidebar);
    });

    // Mark articles as read when clicked
    document.querySelectorAll(".article-title a").forEach(function(link) {
        link.addEventListener("click", function() {
            const articleId = this.dataset.articleId;
            if (!articleId) return;

            var articleEl = document.querySelector('.article-item[data-id="' + articleId + '"]');
            if (articleEl && articleEl.classList.contains("is-read")) return;

            fetch("/articles/" + articleId + "/read", {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" }
            }).then(function() {
                if (articleEl) {
                    updateUnreadCount(articleEl.dataset.feedId, -1);
                    markAsReadWithAnimation(articleEl);
                }
            });
        });
    });

    // Handle Mark Read button clicks with AJAX and flash animation
    document.querySelectorAll('.article-actions form[action*="/read"]').forEach(function(form) {
        // Only intercept "Mark Read" forms, not "Mark Unread"
        if (form.action.includes("/unread")) return;

        form.addEventListener("submit", function(e) {
            e.preventDefault();
            var article = form.closest(".article-item");
            if (!article) return;

            fetch(form.action, {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" }
            }).then(function() {
                updateUnreadCount(article.dataset.feedId, -1);
                markAsReadWithAnimation(article);
                // Update button to "Mark Unread"
                var btn = form.querySelector("button");
                if (btn) {
                    btn.textContent = "Mark Unread";
                    form.action = form.action.replace("/read", "/unread");
                }
            });
        });
    });

    // Swipe gestures for articles (mobile)
    var SWIPE_THRESHOLD = 80;
    var SWIPE_DEAD_ZONE = 30;
    document.querySelectorAll(".article-item").forEach(function(article) {
        var touchStartX = 0;
        var touchCurrentX = 0;
        var isSwiping = false;

        article.addEventListener("touchstart", function(e) {
            touchStartX = e.touches[0].clientX;
            touchCurrentX = touchStartX;
            isSwiping = true;
            article.style.transition = "none";
        }, { passive: true });

        article.addEventListener("touchmove", function(e) {
            if (!isSwiping) return;
            touchCurrentX = e.touches[0].clientX;
            var diff = touchCurrentX - touchStartX;
            var absDiff = Math.abs(diff);
            // Only show visual feedback after passing dead zone
            if (absDiff > SWIPE_DEAD_ZONE && absDiff < 150) {
                var visualDiff = diff > 0 ? diff - SWIPE_DEAD_ZONE : diff + SWIPE_DEAD_ZONE;
                article.style.transform = "translateX(" + visualDiff + "px)";
                article.style.opacity = 1 - (absDiff - SWIPE_DEAD_ZONE) / 200;
            }
        }, { passive: true });

        article.addEventListener("touchend", function() {
            if (!isSwiping) return;
            isSwiping = false;
            var diff = touchCurrentX - touchStartX;
            article.style.transition = "transform 0.2s, opacity 0.2s";
            article.style.transform = "";
            article.style.opacity = "";

            var articleId = article.dataset.id;
            if (!articleId) return;

            if (diff < -SWIPE_THRESHOLD) {
                // Swipe left = toggle read/unread
                var isRead = article.classList.contains("is-read");
                var endpoint = isRead ? "/articles/" + articleId + "/unread" : "/articles/" + articleId + "/read";
                fetch(endpoint, {
                    method: "POST",
                    headers: { "X-Requested-With": "XMLHttpRequest" }
                }).then(function() {
                    if (!isRead) {
                        // Marking as read - flash first, then collapse if in unread view
                        updateUnreadCount(article.dataset.feedId, -1);
                        markAsReadWithAnimation(article);
                    } else {
                        // Marking as unread - no flash
                        updateUnreadCount(article.dataset.feedId, 1);
                        article.classList.remove("is-read");
                    }
                });
            } else if (diff > SWIPE_THRESHOLD) {
                // Swipe right = add to favorites
                fetch("/articles/" + articleId + "/toggle-save", {
                    method: "POST",
                    headers: { "X-Requested-With": "XMLHttpRequest" }
                }).then(function() {
                    article.classList.toggle("is-saved");
                    var starBtn = article.querySelector(".btn-star");
                    if (starBtn) {
                        starBtn.classList.toggle("active");
                        starBtn.textContent = starBtn.classList.contains("active") ? "★" : "☆";
                    }
                });
            }
        });
    });

    // Filter inline edit toggle
    document.querySelectorAll(".btn-edit").forEach(function(btn) {
        btn.addEventListener("click", function() {
            var filterItem = btn.closest(".filter-item");
            if (!filterItem) return;
            filterItem.querySelector(".filter-display").style.display = "none";
            filterItem.querySelector(".filter-edit-form").classList.add("active");
        });
    });

    document.querySelectorAll(".btn-cancel").forEach(function(btn) {
        btn.addEventListener("click", function() {
            var filterItem = btn.closest(".filter-item");
            if (!filterItem) return;
            filterItem.querySelector(".filter-display").style.display = "";
            filterItem.querySelector(".filter-edit-form").classList.remove("active");
        });
    });

    // Custom confirm modal for filter deletion
    var deleteModal = document.getElementById("deleteFilterModal");
    var deleteNameEl = document.getElementById("deleteFilterName");
    var deleteCancelBtn = document.getElementById("deleteFilterCancel");
    var deleteConfirmBtn = document.getElementById("deleteFilterConfirm");
    var pendingDeleteForm = null;

    function openDeleteModal(name, form) {
        pendingDeleteForm = form;
        deleteNameEl.textContent = name;
        deleteModal.classList.add("active");
    }

    function closeDeleteModal() {
        deleteModal.classList.remove("active");
        pendingDeleteForm = null;
    }

    if (deleteModal) {
        document.querySelectorAll(".delete-filter-form").forEach(function(form) {
            form.addEventListener("submit", function(e) {
                e.preventDefault();
                openDeleteModal(form.dataset.filterName, form);
            });
        });

        deleteCancelBtn.addEventListener("click", closeDeleteModal);

        deleteModal.addEventListener("click", function(e) {
            if (e.target === deleteModal) closeDeleteModal();
        });

        deleteConfirmBtn.addEventListener("click", function() {
            if (pendingDeleteForm) pendingDeleteForm.submit();
        });
    }

    // Article search functionality
    const searchInput = document.getElementById("article-search");
    const searchClear = document.querySelector(".search-clear");

    if (searchInput) {
        searchInput.addEventListener("input", function() {
            const query = this.value.toLowerCase().trim();
            filterArticles(query);
        });

        if (searchClear) {
            searchClear.addEventListener("click", function() {
                searchInput.value = "";
                filterArticles("");
                searchInput.focus();
            });
        }
    }

    function escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function highlightText(el, regex) {
        if (!el) return;
        if (!el.dataset.originalText) {
            el.dataset.originalText = el.innerHTML;
        }
        el.innerHTML = el.dataset.originalText.replace(regex, "<mark>$&</mark>");
    }

    function clearHighlight(el) {
        if (!el) return;
        if (el.dataset.originalText !== undefined) {
            el.innerHTML = el.dataset.originalText;
            delete el.dataset.originalText;
        }
    }

    function filterArticles(query) {
        const articles = document.querySelectorAll(".article-item");
        const filterGroups = document.querySelectorAll(".filter-group");
        var regex = query ? new RegExp(escapeRegex(query), "gi") : null;

        // Filter individual articles
        articles.forEach(function(article) {
            var titleEl = article.querySelector(".article-title");
            var summaryEl = article.querySelector(".article-summary");

            if (!query) {
                article.classList.remove("search-hidden");
                clearHighlight(titleEl);
                clearHighlight(summaryEl);
                return;
            }

            const title = (titleEl?.textContent || "").toLowerCase();
            const summary = (summaryEl?.textContent || "").toLowerCase();

            if (title.includes(query) || summary.includes(query)) {
                article.classList.remove("search-hidden");
                highlightText(titleEl, regex);
                highlightText(summaryEl, regex);
            } else {
                article.classList.add("search-hidden");
                clearHighlight(titleEl);
                clearHighlight(summaryEl);
            }
        });

        // Hide filter groups if all their articles are hidden (for filtered.html)
        filterGroups.forEach(function(group) {
            const visibleArticles = group.querySelectorAll(".article-item:not(.search-hidden)");
            if (visibleArticles.length === 0 && query) {
                group.classList.add("search-hidden");
            } else {
                group.classList.remove("search-hidden");
            }
        });
    }
});
