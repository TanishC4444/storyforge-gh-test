# Production planning

Start from the repository with:

```powershell
python -m storyforge.production_web
```

Open http://127.0.0.1:8766. The only detected story is selected automatically;
otherwise use `--story <actual-run-folder>`. The installed entry point is
`storyforge-production`. Install `pip install -e ".[production]"` if the system
needs IANA time-zone data. The app's HTML is included when the package is installed.

The Troy output includes a live Muse Glimmer draft. Load it under Saved plans.
No filming city, cast bookings or vendor rates have been assumed for that example.
Unknown costs are visibly excluded rather than treated as free.

## Inputs and production prompts

The app reads narrative artifacts from the chosen story folder using the existing
soundtrack context reader. It sends bounded story excerpts and your production
brief to Vultr's `muse-glimmer-30b`, followed by a second synthesis call that includes
search leads, the calculated schedule and budget. Long sources may be truncated;
the plan records the source filenames. Generated plans do not change accepted prose.

Optional PNG/JPEG/WebP scene images (maximum 3, 5 MB each) are sent as inline image
content to Muse Glimmer. They are held in memory for the request and are not saved
in plan JSON or sent to SerpAPI. The prompt translates observable features into
scouting criteria and forbids claiming verified geolocation from a generated image.
Without images, the same workflow uses the story and text brief.

The system prompts and exact JSON contracts live in `storyforge/production.py`.
Focus controls cover scheduling, scouting, budgeting, legal research and logistics.
Cross-cutting requirements cover crew/equipment, weather cover, transport, power,
facilities, accessibility, meals, safety, releases, insurance, rights and contingency.
Story material and web results are explicitly treated as untrusted data. Model
output is validated; unknown scene references, dependency cycles, invalid rates and
invented source IDs are rejected rather than accepted through an automatic repair
loop. Provider/model usage is recorded in every plan.

## Scheduling and budgets

Scheduling is a deterministic, single-unit draft, not an optimizer. It observes
scene dependencies, date blackouts, cast/location date availability, weekends,
setup/move allowances, a fixed day/night planning window, a meal allowance and
12-hour turnaround between shifts. Night scenes use a separate 19:00 shift; day
scenes must finish by 18:00. These are assumptions, not forecasts of local light,
weather or labor-law compliance. Split scenes longer than a shift. Unresolved scenes
are reported, and Google sync is disabled while scenes remain unscheduled.

Set availability maps by exact character/location group names from the breakdown.
Date-level availability does not cover actor working-hour limits or partial-day
bookings; add those requirements to the brief and check the resulting plan manually.
Change shooting minutes or budget rows in the app and recalculate without any
provider calls. Calendar output is tentative. Setup/move allowances and meals are
recorded in exports; calendar event times describe the shooting blocks themselves.

Budget low/high totals and contingency are calculated with decimal arithmetic.
Rates remain estimates until replaced with actual quotes. Initial one-day budget
rows are provisionally expanded to the generated shoot-day count, with that
assumption noted. Check quantities after rescheduling; they are editable and are
not silently overwritten by a local recalculation. Zero-rate rows remain unknown
and excluded from totals. No currency conversion, tax, overtime or payroll rules
are silently added.

## SerpAPI conservation and fallbacks

Set these in the server process environment (the command does not load `.env`):

- `VULTR_INFERENCE_API_KEY`
- `SERPAPI_API_KEY`
- `SERPAPI_BACKUP_KEYS`: comma-separated backups, in preferred order
- `STORYFORGE_SEARCH_DAILY_LIMIT`: default 10 network attempts per rolling 24 hours,
  shared by plans within this story's research cache, maximum 30

Defaults: at most 2 new query attempts per plan; UI maximum 3. Cached exact queries
are reusable even after a plan reaches its search allowance. Successful location
and logistics searches cache for 24 hours; legal searches for 6 hours. The app also
leaves SerpAPI's own cache enabled. Each query returns at most 5 organic leads.

On HTTP 401, 403 or 429, the credential enters a one-hour cooldown and the next key
is attempted. At most 3 configured keys are tried per query. Failed attempts count
toward the daily cap. Network failures or server errors do not trigger a cascade
across keys. Exhaustion yields a visible warning and the plan can continue with
research gaps. No scraping fallback burns more queries or bypasses provider limits.

The cache and atomic usage reservations are in the story's
`production/search-cache.sqlite` (Git-ignored). No raw API keys or request URLs are
stored there. Only a non-reversible key fingerprint is used for cooldown records.
Different story folders have separate allowances. Research is skipped without a
real filming region. No location, rate or permit is reported as confirmed merely
because it appeared in a search snippet. Sources and retrieval times are shown.
SerpAPI alone is sufficient for this first version; Playwright is not required.

## Exports and integrations

Each plan is saved under `production/plans/<id>.json`. The app exports:

- `calendar.ics`: Google Calendar, Outlook and Apple Calendar import
- `schedule.csv`: shoot schedule for spreadsheets / production software
- `budget.csv`: editable cost rows for spreadsheets
- `tasks.csv`: legal/logistical follow-ups for task tools
- `call-sheets.txt`: draft call sheets with unconfirmed contacts/safety details marked
- `plan.json`: complete data, evidence and usage for other integrations

These are file integrations, not native two-way connectors to every production app.
CSV text is escaped to reduce spreadsheet formula injection. ICS uses UTC event
instants, stable event IDs, UTF-8 line folding and escaped user text.

### Direct Google Calendar connection

1. Create a Google OAuth web client, enable Google Calendar API and set its consent
   screen/test users as appropriate.
2. Register `http://127.0.0.1:8766/google/callback` (adjust for a custom port).
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the server environment.
4. Click Connect Google Calendar and authorize the `calendar.events` scope.
5. Preview a plan, select a destination calendar ID (default `primary`), then click
   Sync this schedule to Google Calendar.

The browser connection validates OAuth state and uses PKCE. Tokens stay in server
memory for that session. Existing `GOOGLE_CALENDAR_ACCESS_TOKEN` or a refresh token
in `GOOGLE_CALENDAR_REFRESH_TOKEN` with client credentials can be used instead.
Refresh tokens are never written to plan artifacts. OAuth configuration and user
consent are required; an API key alone cannot authorize a personal calendar.

Sync checks existing busy events and skips overlaps, creates private tentative
shoot events, and does not add guests or send invitations. Stable IDs make repeat
sync idempotent; partial provider failures return the IDs already created.
This is create-only sync: moving a shoot produces a different event ID; it does
not delete or update the old event. Review changes or use a dedicated production
calendar. Existing calendar conflicts are checked at sync time, not during offline
schedule generation. No calendar events are created just by generating a plan.

## Running checks

```powershell
python -m unittest tests.test_production tests.test_soundtracks -v
```

The production tests cover model/vision payloads, dependency cycles, availability,
lighting and rest constraints, budget arithmetic, source IDs, search caching,
quota/failover behavior, exports, Google conflict/idempotency/partial-failure paths,
local request protection and recalculation. Direct Google authorization requires
an actual client and consent; mocked tests do not claim a live calendar connection.

Provider contracts used:

- https://api.vultrinference.com/docs/reference/create-chat-completion
- https://serpapi.com/search-api
- https://serpapi.com/api-status-and-error-codes
- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- https://developers.google.com/identity/protocols/oauth2/web-server
