# MyFeeds - Project Specification

## Overview

A personal RSS reader with intelligent filtering. The core problem: free RSS readers lack auto-filtering, and paid tiers are overkill for personal use.

**Success criteria:**
- Subscribe to feeds, read articles, mark read/unread
- Regex filters auto-mark articles as read
- Filtered articles reviewable by which rule caught them (false-positive check)
- Works on iPad, Android, Mac, Windows (responsive web)

## Feature Requirements

### Must Have (MVP)

1. **Feed management**
   - Add feed by URL
   - Remove feed
   - OPML import (Feedly export compatibility)

2. **Article reading**
   - List articles (title, source, date, snippet)
   - Mark read/unread
   - Save for later
   - Open original article in new tab

3. **Filtering engine**
   - Create filter: name, regex pattern, target (title/summary/both)
   - Filters run on fetch, auto-mark matches as read
   - Filter matches stored with rule ID
   - "Filtered" view grouped by rule for review

4. **Background refresh**
   - Default: every 30 minutes (configurable in settings)
   - Manual refresh button

### Nice to Have (Post-MVP)

- Folders/categories for feeds
- Keyboard shortcuts
- Dark mode
- OPML export
- Search within articles

### Non-Goals

- Multi-user / authentication (personal tool)
- Mobile native apps (responsive web is sufficient)
- Social features, sharing, comments
- Full-text search across all historical articles

## Data Model

### feeds
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| url | TEXT | Feed URL |
| title | TEXT | Feed title |
| site_url | TEXT | Website URL |
| last_fetched | DATETIME | |
| created_at | DATETIME | |

### articles
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| feed_id | INTEGER FK | |
| guid | TEXT | Unique per feed (dedup) |
| title | TEXT | |
| summary | TEXT | |
| content | TEXT | Raw content for re-filtering |
| url | TEXT | Link to original |
| published_at | DATETIME | |
| is_read | BOOLEAN | Default false |
| is_saved | BOOLEAN | Default false |
| created_at | DATETIME | |

### filters
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| name | TEXT | User-friendly name |
| pattern | TEXT | Regex pattern |
| target | TEXT | 'title', 'summary', 'both' |
| is_active | BOOLEAN | Default true |
| created_at | DATETIME | |

### filter_matches
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| article_id | INTEGER FK | |
| filter_id | INTEGER FK | |
| matched_at | DATETIME | |

## Implementation Phases

### Phase 1: Core Reader
- Flask app scaffold with SQLite
- Feed model + feedparser integration
- Basic UI: list feeds, list articles, mark read
- Manual refresh

**Exit criteria:** Can add a feed, see articles, mark as read.

### Phase 2: Filtering Engine
- Filter CRUD
- Filter execution on article fetch
- filter_matches storage
- "Filtered" view grouped by rule
- Re-filter existing articles when rule added

**Exit criteria:** Can create regex filter, see it catch articles, review by rule.

### Phase 3: Polish
- OPML import
- Save for later
- Background scheduler (APScheduler or cron)
- Responsive CSS for mobile
- Settings page (refresh interval)

**Exit criteria:** Full MVP feature set, usable on phone.

## UI/UX Notes

**Key screens:**
1. **Feed list** — sidebar or collapsible, shows unread counts
2. **Article list** — main view, sortable by date
3. **Article detail** — optional, or just expand in list
4. **Filtered review** — grouped by filter rule
5. **Settings** — manage feeds, filters, refresh interval

**Responsive:** Must work on phone screens. Collapsible sidebar, readable font sizes.

**Keep it simple:** No fancy frameworks. Vanilla JS or Alpine.js. Minimal CSS (classless like Pico, or simple custom).

## Open Questions

CC should ask before assuming:

1. **Article retention** — Keep forever, or auto-delete after N days?
2. **Re-filtering** — When a new filter is added, apply to existing unread articles only, or all articles?
3. **Filter precedence** — If multiple filters match, store all matches or just first?
4. **Refresh failure handling** — Silent retry, or surface errors to user?

## Initial Feeds

For testing, import these feeds (or use OPML from Feedly):
- Lifehacker
- Scientific American
- The Verge
- Wirecutter
- XDA
- Multiple Sclerosis News Today
