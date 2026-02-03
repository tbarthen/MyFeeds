document.addEventListener("DOMContentLoaded", function() {
    // Mark articles as read when clicked
    document.querySelectorAll(".article-title a").forEach(function(link) {
        link.addEventListener("click", function() {
            const articleId = this.dataset.articleId;
            if (!articleId) return;

            fetch("/articles/" + articleId + "/read", {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" }
            }).then(function() {
                const articleEl = document.querySelector('.article-item[data-id="' + articleId + '"]');
                if (articleEl) {
                    articleEl.classList.add("is-read");
                }
            });
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
