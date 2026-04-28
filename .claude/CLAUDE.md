# CLAUDE.md

Context for Claude Code working on this repository.

## TL;DR

Django 5 web app — job application tracker with a built-in work.ua scraper.
User pastes a vacancy URL → app parses it → creates `Vacancy` (shared catalog)
+ `Application` (user's personal tracking record). User then manages
application status: saved → interview → offer / rejected.

This is a **student portfolio project** for a Django course, not production.
But the code aims to be production-quality — separation of concerns, security
basics, no shortcuts.

## Stack

- Python 3.11+, Django 5.x
- SQLite for dev (Postgres-ready — no SQLite-specific code)
- Django Templates + Bootstrap 5 (CDN, no build step)
- `requests` + `beautifulsoup4` + `lxml` for the scraper
- `python-decouple` for `.env` config

## Project layout

```
config/                       # Django project settings
    settings.py
    urls.py
jobs/                         # The main (only) app
    models.py                 # Company, Skill, Vacancy, Application
    views.py                  # All views — function-based, no CBVs
    forms.py                  # ImportVacancyForm, ApplicationForm
    urls.py
    admin.py
    services/                 # Business logic, framework-agnostic where possible
        work_ua.py            # Scraper — pure Python, no Django imports
        importer.py           # Orchestrates parser + ORM in a transaction
    migrations/
templates/                    # Project-level templates dir (settings.DIRS)
    base.html
    jobs/
        home.html
        dashboard.html
        import.html
        application_detail.html
        application_form.html
        application_confirm_delete.html
    registration/             # Django auth looks here by convention
        login.html
        register.html
.env                          # NOT committed
.env.example                  # Template, committed
requirements.txt
README.md                     # User-facing
CLAUDE.md                     # This file
```

## Models

Four models. The split is deliberate.

### `Company`

Shared catalog. Not per-user. Dedup key: `name` (unique).
- `name`, `work_ua_url`, `created_at`

### `Skill`

Just a name. ManyToMany with Vacancy. Lets us answer "show all Django jobs"
or "top 10 skills" with one ORM call.
- `name` (unique)

### `Vacancy`

Shared catalog of parsed vacancies. **Not** per-user. Dedup key: `source_url`
(unique). If two users import the same URL, we get one Vacancy and two
Applications.

Fields map 1:1 to what the scraper returns. `is_active` is for future
"refresh vacancy data" feature — flips False if a re-parse returns 404.

### `Application`

The per-user record. Links a User to a Vacancy with personal metadata.
- ForeignKey: user, vacancy
- `status` via `TextChoices` enum (saved, interview, test_task, offer,
  accepted, rejected, withdrawn)
- `notes`, `cv_file` (PDF upload, ≤5 MB, stored under
  `media/cv_resumes/user_<id>/`), `applied_at` (auto), `updated_at` (auto)
- `Meta.unique_together = ["user", "vacancy"]` — one user can't have two
  Applications for the same Vacancy

## Auth

Built-in Django auth. Custom `register` view uses `UserCreationForm` and
auto-logs in after signup. `LOGIN_REDIRECT_URL = "home"`.

`/accounts/login/`, `/accounts/logout/`, `/accounts/password_change/` are
provided by `django.contrib.auth.urls`.

Logout is POST-only (Django 5 default) — `base.html` uses a tiny form for it,
not a link.

## URL routes

| Path | View | Purpose |
|---|---|---|
| `/` | `home` | Landing — different content for auth/anon |
| `/register/` | `register` | Signup (autologin on success) |
| `/dashboard/` | `dashboard` | List of current user's Applications |
| `/import/` | `import_vacancy` | Form: paste URL → parse → create records |
| `/applications/<pk>/` | `application_detail` | View one Application |
| `/applications/<pk>/edit/` | `application_edit` | Edit status/notes/cv_file |
| `/applications/<pk>/delete/` | `application_delete` | Confirm + delete |
| `/admin/` | Django admin | All four models registered |
| `/accounts/...` | Django auth | login, logout, password reset |

## The scraper (`services/work_ua.py`)

**Critical: framework-agnostic.** No Django imports. Returns a `dataclass`
(`VacancyData`), not a model. Can be tested standalone or run as a CLI:

```bash
python jobs/services/work_ua.py https://www.work.ua/jobs/1234567/
python jobs/services/work_ua.py <url> -o vacancy.json
```

### Error handling contract

- Only `title` (`h1#h1-name`) is required. Missing → raises
  `WorkUaParseError`.
- All other fields fall back to `""` or `[]`. Missing salary or skills
  is normal, not an error.
- 404 / network / non-200 → all raise `WorkUaParseError` with a specific
  message. Calling code catches this one exception type, never bare
  `Exception`.

### Selectors used (will break if work.ua redesigns)

| Field | Selector |
|---|---|
| title | `h1#h1-name` |
| company | `a[href^="/jobs/by-company/"] span.strong-500` |
| location | `<li>` containing `glyphicon-map-marker`, direct text children only |
| HR name | `<li>` with `glyphicon-phone` → `span.mr-sm` |
| phone | `a.js-get-phone[href^="tel:"]` (works even when JS hides the button) |
| salary | `<li>` with `glyphicon-hryvnia-fill` → `span.strong-500` |
| skills | `li.label-skill span.ellipsis` (all) |
| description | `div#job-description` |

If a selector breaks, fix it in **one place** — its dedicated
`_parse_<field>` method on `WorkUaParser`. Don't add fallback chains; let
the field return empty.

## The importer (`services/importer.py`)

Single function: `import_vacancy_from_url(url, user) -> Application`.
Wrapped in `@transaction.atomic` — if anything fails mid-way (parse error,
DB constraint, network), the whole thing rolls back. No half-created
records.

Sequence:
1. `WorkUaParser().parse_vacancy(url)` → `VacancyData`
2. `Company.get_or_create(name=...)`
3. `Skill.get_or_create` per skill name
4. `Vacancy.get_or_create(source_url=...)` — `source_url` is the dedup key
5. If vacancy was newly created, `vacancy.skills.set(skill_objects)`
6. `Application.get_or_create(user=, vacancy=)` — `unique_together`
   prevents duplicate Applications for the same vacancy

This function is the **only** legitimate way to create a Vacancy + linked
Application. Don't bypass it from views.

## Conventions and rules

### Don't bypass the importer

If you need a Vacancy + Application from a work.ua URL, call
`import_vacancy_from_url`. Don't reimplement the orchestration in a view
or management command.

### Owner check pattern

Every view that touches an `Application` (detail, edit, delete) must:

```python
application = get_object_or_404(Application, pk=pk)
if application.user != request.user:
    return HttpResponseForbidden("Not your record.")
```

Without this, anyone with a pk can read/edit/delete anyone's data. This is
the single most-likely security hole in this codebase. New views on
Application must follow this pattern.

### Filter by user, always

Dashboard and any list view of personal data must filter by
`request.user`:

```python
applications = Application.objects.filter(user=request.user)
```

`Vacancy` and `Company` are shared and don't filter by user.

### URL validation in `ImportVacancyForm`

`clean_url` checks `urlparse(url).netloc in ("work.ua", "www.work.ua")`.
This is **SSRF protection** — without it, a user could paste
`https://internal-service/admin` and the server would fetch it. Don't
remove this check. If adding new sources (e.g. djinni.co), extend the
allowlist explicitly.

### `get_or_create` idempotency

Importing the same URL twice must not create duplicates. This is
guaranteed by:
- `Vacancy.source_url` unique
- `Skill.name` unique
- `Company.name` unique
- `Application.unique_together = (user, vacancy)`

If you change a model, preserve these invariants.

### Function-based views only

This codebase uses FBVs for consistency and readability. Don't introduce
class-based views — the student is learning Django basics, mixing the two
patterns adds noise.

### Templates: `{# #}` not `<!-- -->`

Django evaluates tags inside HTML comments. Use Django comments
(`{# ... #}` or `{% comment %}...{% endcomment %}`) to actually disable
template logic.

### Bootstrap from CDN

No npm, no build step, no static-files pipeline beyond Django's defaults.
Bootstrap 5 + Bootstrap Icons via `<link>` in `base.html`. Keep it that
way unless explicitly asked.

### `verbose_name_plural` for Company and Vacancy

Django pluralizes them as "Companys" and "Vacancys" in admin. Both have
`verbose_name_plural = "Companies"` / `"Vacancies"` in `Meta`. Don't drop
those.

## Common tasks

### Run dev server
```bash
python manage.py runserver
```

### Reset DB (dev only)
```bash
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

### Test the scraper standalone
```bash
python jobs/services/work_ua.py https://www.work.ua/jobs/<id>/
```

### Test the importer in shell
```python
python manage.py shell
>>> from django.contrib.auth.models import User
>>> from jobs.services.importer import import_vacancy_from_url
>>> me = User.objects.get(username="<your_user>")
>>> app = import_vacancy_from_url("https://www.work.ua/jobs/<id>/", me)
>>> print(app)
```

### Add a new vacancy field

1. Add to `VacancyData` dataclass in `services/work_ua.py`
2. Add `_parse_<field>` method to `WorkUaParser`
3. Wire it in `parse_vacancy()`
4. Add the model field to `Vacancy`
5. `makemigrations` + `migrate`
6. Add to `Vacancy.get_or_create(defaults={...})` in `importer.py`
7. Display in `application_detail.html` if user-facing

### Add a new status

1. Add to `Application.Status` TextChoices enum
2. No migration needed — `choices` is a Python-level constraint, not a DB
   constraint
3. Update any status-grouping logic in dashboard if you do kanban later

## Things to watch out for

### `.env` must not be committed

`.gitignore` excludes it. Before any commit, check `git status` does not
show `.env`. `SECRET_KEY` rotation is annoying.

### Templates break silently on undefined vars

Django renders `{{ undefined_var }}` as empty string by default, no error.
If a page looks weirdly blank, check for typos in variable names. Common
trap: `{{ application.user.username }}` works,
`{{ application.user_username }}` silently fails.

### M2M `.skills.all()` triggers a query per call

In templates, multiple `{% for skill in app.vacancy.skills.all %}` in a
loop = N+1 problem. If we add a heavy list page, use `.prefetch_related`.
Currently fine — list pages don't render skills.

### `auto_now_add` vs `auto_now`

- `auto_now_add=True` — set once on creation, never updated. Used for
  `created_at`, `applied_at`, `parsed_at`.
- `auto_now=True` — updated on every `.save()`. Used for `updated_at`.

Don't swap them. If something feels wrong with timestamps, this is usually
the cause.

## Out of scope (intentionally)

- Bulk parsing / pagination / management commands — listed as bonus in the
  spec, not built unless asked
- Kanban drag-and-drop — bonus
- Email notifications — not in scope
- API / REST — Django Rest Framework would be a separate project
- Tests — not required by the course rubric (the student should add a
  smoke test for the scraper at minimum, but this isn't gated)
- i18n — UI is Ukrainian, no translation infrastructure
- Production deploy — DEBUG=True, SQLite, no WSGI config beyond Django
  defaults

If asked to add any of the above, confirm scope before writing code —
the student may be over-extending.

## Working style notes

The student is learning Django. They write their own code; help with
patterns, code review, and debugging — don't ghost-write large chunks
unless explicitly asked. When showing examples, label them clearly as
examples to study, not to copy-paste blindly. The course guide
(`django_portfolio_guide.docx`) emphasizes this.

When something breaks: ask for the full traceback, not a paraphrase.
"It doesn't work" is not actionable.
