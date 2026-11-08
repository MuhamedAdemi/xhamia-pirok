# Xhamia Pirok — management app (context for Claude Code)

Django app that runs the finances of the Pirok mosque (North Macedonia): ~1150 member households
("shtëpi"), yearly membership fees (antarësia), cemetery fees (varrezat), donations to the mosque fund
(fondi), expenses (harxhimet), invoices, SMS/email notices and debt letters. It replaced the old
"Masjid Manager" web app; the staff are used to that app's screens, so the "Puna e përditshme" pages
mimic it on purpose.

## Working with the user
- The user (admin of the app, not a professional developer) writes in **Albanian, often without
  diacritics** — always answer in Albanian, short and step by step. Code identifiers, comments,
  templates and UI text are in Albanian too; keep that style (e.g. `shtepia`, `pagesat`, `borxhi`).
- Workflow for every change: implement → run the full test suite → commit → push to GitHub →
  give the **full deploy block** below (never just `git pull`).
- The GitHub repo is **PUBLIC**: never commit names, phone numbers, emails of members, PDFs,
  Excel/CSV data files, `db.sqlite3`, passwords or API keys. Member data lives only in the
  production DB and in local data files outside the repo; imports go through upload pages in the app.
- Production data is on PythonAnywhere. The local `db.sqlite3` is only a copy (e.g. restored from a
  backup) — analysis done locally is indicative; real corrections are made through app pages
  (preview first, then the user confirms).
- Don't guess about payment status: payments registered in the app always win over old notebooks /
  imported lists.

## Deploy (PythonAnywhere free tier, account `xhamiapirok`)
Project in `~/xhamia-pirok`, plain venv inside it. After pushing, give the user exactly:
```bash
cd ~/xhamia-pirok
source venv/bin/activate
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
deactivate
```
…then **Web tab → green Reload** (the app does not reload on its own). Tell them to run the lines
one by one (pasting the block several times once froze the console; fix = close it under Consoles
and open a new Bash console). Free tier: requests must be fast — avoid heavy work per request
(e.g. xhtml2pdf took 68 s for 1150 rows; large PDFs are built with reportlab directly).

## Stack and commands
- Django 5.2, SQLite, Python 3.10 on the server. `requirements.txt` is **UTF-16 encoded** — edit it
  with an encoding-aware script, not with plain `echo >>`.
- PDF: xhtml2pdf (invoices, letters) and reportlab (big tables); Excel: openpyxl; Word: python-docx;
  PDF reading: pypdf.
- Windows dev machine: run commands with `venv/Scripts/python.exe manage.py …`; use
  `PYTHONIOENCODING=utf-8` when printing Albanian text. PDF font warnings in tests on Windows are harmless.
- Tests: `venv/Scripts/python.exe manage.py test xhamia` (all must pass before commit; ~2–3 min).
- Management commands: `backup_automatik [--email]`, `rikthe_backup <zip> --po`, `fillo_nga_zero --po`,
  `llogarite_stafit`, `vendos_kategorite [--provo]`.

## Domain rules (important)
- **Roles** (`ProfilStafi.rol`): ADMIN, STAF (may register payments if allowed), MONITORUES (view only).
  Helpers in views: `është_admin`, `mund_shikoje`, `mund_regjistrojë`.
- **House accounts** (username `sh####`, `ProfilShtepi`): `xhamia/middleware.py` restricts them to the
  house portal and their own invoice PDFs only — keep this whitelist tight (it was a real security bug).
- **Membership status** of a house = registered payments (`PagesaAntaresia`, each covers `viti..viti_deri`)
  + historical fields `viti_fillimit_antaresise` (debt counted from this year) and `paguar_deri_viti`
  (paid up to this year, from imports/notebooks). Central logic: `xhamia/gjendja.py`
  (`gjendja_e_shtepive`) and `_tabela_vjetore` in `views.py`.
- Minimum tariff: 50 € for past years, 70 € for the current year (`KonfigurimiSistemit`).
- Category with yearly amount 0 € (e.g. "E Liruar") = **gratis**: no membership debt, no letters.
- **House categories 1–4** (`xhamia/kategorite.py`): `Kategoria.shuma_vjetore` (€) + `shuma_vjetore_mkd` (den)
  are thresholds; categories with amount > 0 are numbered 1.. from the highest. A year's payment gets the
  highest category whose threshold it reaches (7000 den → 1, 4999 den / 79 € → 4); mixed €+den counts
  `eur/kufiri_eur + den/kufiri_den ≥ 1`. Defaults: 120/7000, 100/6000, 80/5000, 70/4000.
  `caktoje_nga_pagesa` runs after every new membership payment: sets `kategoria_pageses` and changes the
  house's category (also from "E Liruar") only if the payment covers its latest paid year (old-debt payments
  don't lower it). Houses known only from history (`paguar_deri_viti`, no amount) are set by hand in the
  Antarësia list (Kategoria column, admin only). One-off fill: `python manage.py vendos_kategorite [--provo]`.
- **Membership payments** can be in two currencies (`monedha_2`/`shuma_monedhe_2`, e.g. 150 € + 3.700 den;
  `shuma_mkd`/`shuma_paguar` hold the total) and can store an amount per year in `vitet_shumat`
  (`{"2024": {"EUR": "50", "MKD": "1233"}}`, totals must match; empty = equal split) — see
  `PagesaAntaresia.shumat_e_viteve()`, UI in `static/js/vitet_shumat.js`
  (years pre-filled with the tariffs, the user edits; the totals above are filled from the years).
- Cemetery fee is obligatory only from **2027** (`viti_fillimit_varrezave` default 2027).
- **Invoices**: paper receipt books from the Muftiate — `blloku` (4 digits) + `nr_fatures` (6 digits),
  shown as "Bllok 1100 nr 046386"; unique together; `sugjero_faturen` suggests the next one.
- **Money**: payments in MKD/EUR/CHF/USD (`MonedhaMixin`), always also stored in € (`FUSHA_EUR`);
  display with `formato_shumen` ("75.000 den", "69,92 €").
- Every new payment automatically emails the invoice ONLY to the official addresses (`EMAILET_ZYRTARE`:
  xhamia, kryetari i këshillit, imami) — staff personal emails never receive it (field removed); the payer
  gets email/SMS only via buttons on the payment page.
- **SMS** via SMSGate ("SMS Gateway for Android", api.sms-gate.app — on PythonAnywhere's whitelist),
  sent from the mosque's phone. Credentials, SIM choice and the Gmail app password are entered in the
  app page "⚙️ SMS & Email" (`KonfigurimiSistemit`), not in files. For SMS failures, read the gateway's
  per-message error (the app shows "SMSGate e refuzoi (…)").
- Names: `emri_kryefamiljarit` + `emri_prindit` + `mbiemri_kryefamiljarit` (`emri_i_plote`). Searches
  normalize ë→e, ç→c and highlight matches.

## Main parts (where to look)
- `xhamia/views.py` — most pages (houses, payments, dashboards, letters, backup, SMS…).
- `xhamia/views_puna.py` — "Puna e përditshme": Antarësia list (the user's main screen, speed matters: search →
  + (or Enter when one row is left) opens a small dialog with ✏️ Edito, 📋 Antarësia, 🤲 Fondi, ⚰️ Varrezat, 🏠 Kartela;
  each link carries `next=<list ?q=…&hap=<pk>>`, so after saving the list reopens the same house's dialog with the
  "U regjistrua … Hap pagesën" banner. Forms opened with `next` load only that house in the select
  (`_vetem_shtepia_e_zgjedhur`); GZipMiddleware shrinks the 1 MB list to ~50 KB. Kategoria column) and "Paguar deri"
  column, Pagesat hyrëse/dalëse, Llojet e pagesave (`LlojiPageses`), Fletorja, Evidenca.
- House ledger downloads (Word print / PDF / Excel, `fletorja.plotëso_qelizat`): Albanian alphabet order
  (`celesi_shqip`), columns Nr · Emri · Prindi · Mbiemri · Kat. · Borxh (unpaid years before the first column, '/' none)
  · years (payment category, else house category, else '+'; blank unpaid). The old Paguar/Borxh PDF is kept as
  `fletorja/krahasim/` because `lexo_fletoren` reads that format.
- `xhamia/raporti.py` — register (Antarësia/Fondi/Varrezat): block, month, quarter, cumulative 3/6/9 months, year;
  `statistika_vjetore` month-by-month table; Excel (+ "Statistika" sheet) and PDF.
- `xhamia/fletorja.py` — membership ledger: build rows, read a ledger PDF, compare with the app
  (`krahaso`: corrections / conflicts with old debt / name suggestions), apply chosen fixes.
- `xhamia/word.py` — Word documents: ledger (A4) and "Informim" debt letters (2 per A4 page).
- `xhamia/evidenca.py` — statistics by first letter of the name (A, B, … I-Y, L-LL, SH, XH, Z):
  members / paid / unpaid / gratis per chosen year, PDF.
- `xhamia/letrat.py` — debt letter texts and selection (min. years of debt).
- `xhamia/importi_pdf.py`, `importi_excel.py` — house imports (Masjid Manager PDFs, Excel).
- `xhamia/sms.py`, `utils.py` (emails), `backup.py`, `duplikatet.py`, `kerkimi.py`, `raporti.py`.

## Open / planned
- The user is checking the ledger corrections manually before trusting them 100%.
- Later: the user will type old handwritten notebooks (2020–2026 donations and memberships) into Excel
  and we will import them as historical records (no emails/SMS, no invoice number required, marked as
  "from the old notebook"). Ask for a 5–10 row sample before building the import.
- Deferred idea: WhatsApp reminders.
