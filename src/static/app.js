document.addEventListener("DOMContentLoaded", function() {
    // Check if we're in unread-only view
    function isUnreadView() {
        return window.location.search.includes("unread=1");
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

    // Handle marking article as read with flash and optional collapse
    function markAsReadWithAnimation(article) {
        article.classList.add("just-read");
        setTimeout(function() {
            article.classList.remove("just-read");
            if (isUnreadView()) {
                // In unread view: collapse and remove
                article.style.maxHeight = article.offsetHeight + "px";
                // Force reflow
                article.offsetHeight;
                article.classList.add("collapsing");
                setTimeout(function() {
                    article.remove();
                }, 300);
            } else {
                // In all view: just dim it
                article.classList.add("is-read");
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
                if (isUnreadView()) {
                    markAsReadWithAnimation(article);
                } else {
                    article.classList.add("just-read");
                    setTimeout(function() {
                        article.classList.remove("just-read");
                        article.classList.add("is-read");
                        // Update button to "Mark Unread"
                        var btn = form.querySelector("button");
                        if (btn) {
                            btn.textContent = "Mark Unread";
                            form.action = form.action.replace("/read", "/unread");
                        }
                    }, 400);
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

    function filterArticles(query) {
        const articles = document.querySelectorAll(".article-item");
        const filterGroups = document.querySelectorAll(".filter-group");

        // Filter individual articles
        articles.forEach(function(article) {
            if (!query) {
                article.classList.remove("search-hidden");
                return;
            }

            const title = (article.querySelector(".article-title")?.textContent || "").toLowerCase();
            const summary = (article.querySelector(".article-summary")?.textContent || "").toLowerCase();

            if (title.includes(query) || summary.includes(query)) {
                article.classList.remove("search-hidden");
            } else {
                article.classList.add("search-hidden");
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
