# One-time setup: Google Sheet push webhook

> **Already deployed?** If the webhook exists (it does — deployed 2026-07-21),
> new teammates skip ALL steps below. They only need `config/sheet.json` with
> the existing `webhook_url` + `token`, shared privately by someone who has it
> (the file is gitignored, never in the repo). Nothing is hosted on our side —
> the webhook runs on Google's servers, so there is no server to deploy or
> maintain.

Lets the generator push new picks straight into the shared pool spreadsheet
(tab "Word Content"), inserted at the top so people see the newest first.
Takes ~5 minutes.

## 1. Add the Apps Script to the spreadsheet

1. Open the pool spreadsheet:
   https://docs.google.com/spreadsheets/d/1qW17E9iSseOB3V3jj97PqWCqVy0M6ws_r-HqVJthXO0/edit
2. Menu: **Extensions → Apps Script**.
3. Delete any code in the editor and paste this, then set `TOKEN` to a long
   random string (e.g. run `openssl rand -hex 24` in a terminal):

```javascript
const TOKEN = "PASTE-A-LONG-RANDOM-STRING-HERE";
const SHEET_NAME = "Word Content";
const CATEGORY_BG = "#d9e1f2";

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.token !== TOKEN) {
      return reply({error: "invalid token"});
    }
    const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
    if (body.action === "restyle") return restyle(sheet, body);
    if (body.action === "deleteKeys") return deleteKeys(sheet, body);
    if (body.action === "updateRows") return updateRows(sheet, body);
    return insertRows(sheet, body);
  } finally {
    lock.releaseLock();
  }
}

function insertRows(sheet, body) {
  if (!Array.isArray(body.rows) || !body.rows.length) {
    return reply({error: "no rows"});
  }
  const lastRow = sheet.getLastRow();
  const existing = new Set(
    lastRow > 1
      ? sheet.getRange(2, 1, lastRow - 1, 1).getValues()
          .map(row => String(row[0]))
      : []);
  const width = sheet.getLastColumn();
  const fresh = body.rows
    .filter(row => !existing.has(String(row[0])))
    .map(row => {
      const cells = row.slice(0, width);
      while (cells.length < width) cells.push("");
      return cells;
    });
  if (fresh.length) {
    sheet.insertRowsBefore(2, fresh.length);
    sheet.getRange(2, 1, fresh.length, width).setValues(fresh);
    applyStyles(sheet, fresh.map(row => row[0]), width);
  }
  return reply({inserted: fresh.length,
                skipped: body.rows.length - fresh.length});
}

// {action: "updateRows", rows: [...]} — for each row whose Key exists in
// column A, fill ONLY the cells that are currently blank. Manual edits made
// in the sheet are never overwritten. Unknown keys are reported, not inserted.
function updateRows(sheet, body) {
  if (!Array.isArray(body.rows) || !body.rows.length) {
    return reply({error: "no rows"});
  }
  const lastRow = sheet.getLastRow();
  const width = sheet.getLastColumn();
  const rowByKey = {};
  if (lastRow > 1) {
    sheet.getRange(2, 1, lastRow - 1, 1).getValues().forEach((row, i) => {
      rowByKey[String(row[0])] = i + 2;
    });
  }
  let updated = 0, missing = 0;
  body.rows.forEach(row => {
    const rowIndex = rowByKey[String(row[0])];
    if (!rowIndex) { missing++; return; }
    const range = sheet.getRange(rowIndex, 1, 1, width);
    const current = range.getValues()[0];
    let changed = false;
    for (let col = 1; col < width; col++) {
      const fresh = col < row.length ? row[col] : "";
      if (String(current[col]) === "" && fresh !== "") {
        current[col] = fresh;
        changed = true;
      }
    }
    if (changed) { range.setValues([current]); updated++; }
  });
  return reply({updated: updated, missing: missing});
}

// Category rows (Key without a dot) are bold on a light-blue background;
// item rows are plain. Inserted rows would otherwise inherit the style of
// the row they were inserted above.
function applyStyles(sheet, keys, width) {
  const isCategory = keys.map(key => String(key).indexOf(".") === -1);
  const range = sheet.getRange(2, 1, keys.length, width);
  range.setFontWeights(isCategory.map(c => Array(width).fill(c ? "bold" : "normal")));
  range.setBackgrounds(isCategory.map(c => Array(width).fill(c ? CATEGORY_BG : null)));
}

// {action: "restyle", count: N} — reapply the category/item styling rule to
// the top N data rows (rows 2..N+1). Repair tool for badly styled inserts.
function restyle(sheet, body) {
  const count = Math.min(Math.floor(Number(body.count) || 0),
                         sheet.getLastRow() - 1);
  if (count < 1) return reply({error: "bad count"});
  const width = sheet.getLastColumn();
  const keys = sheet.getRange(2, 1, count, 1).getValues().map(row => row[0]);
  applyStyles(sheet, keys, width);
  return reply({restyled: count});
}

// {action: "deleteKeys", keys: [...]} — delete the rows with exactly these
// Keys. Only used for explicit cleanups; normal pushes never delete.
function deleteKeys(sheet, body) {
  if (!Array.isArray(body.keys) || !body.keys.length) {
    return reply({error: "no keys"});
  }
  const wanted = new Set(body.keys.map(String));
  const values = sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).getValues();
  let deleted = 0;
  for (let i = values.length - 1; i >= 0; i--) {
    if (wanted.has(String(values[i][0]))) {
      sheet.deleteRow(i + 2);
      deleted++;
    }
  }
  return reply({deleted: deleted});
}

function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
```

4. Click the save icon (name the project anything, e.g. "wcg webhook").

## 2. Deploy as a web app

1. **Deploy → New deployment**.
2. Gear icon → type **Web app**.
3. *Execute as:* **Me** · *Who has access:* **Anyone**.
4. Click **Deploy**, authorize when prompted, and copy the **Web app URL**
   (ends in `/exec`).

Note: after any later edit to the script you must **Deploy → Manage
deployments → edit → New version**, otherwise the URL keeps serving the old
code.

## 3. Configure the generator

Create `config/sheet.json` (gitignored — it holds the secret):

```json
{
  "webhook_url": "https://script.google.com/macros/s/DEPLOYMENT-ID/exec",
  "token": "the same TOKEN string you pasted in the script"
}
```

## 4. Backfill and verify

```bash
python -m wcg sheet-push
```

Expected output like: `pushed 25 rows: 16 inserted, 9 already in sheet` — and
the new rows appear at the top of the Word Content tab.

From now on every pick in the web UI is pushed automatically; if the push
fails you'll see a `sheet: ...` warning in the status line, and rerunning
`python -m wcg sheet-push` repairs the sheet from `data/localization.csv`.

## How it behaves

- **Idempotent:** rows whose Key already exists in column A are skipped, so
  re-pushing is always safe.
- **Newest on top:** new rows are inserted at row 2, below the header.
- **Styled:** category rows (Key without a dot) get bold + light-blue
  background; item rows stay plain.
- **Translations arrive later:** picks are pushed with English only;
  the generator backfills translations via `updateRows`, which fills only
  blank cells — a translation someone hand-fixed in the sheet is never
  overwritten.
- Normal pushes never delete existing rows; `restyle` and `deleteKeys` are
  explicit maintenance actions.

> **Already deployed before 2026-07-21?** The `updateRows` action was added
> then. Paste the current script over the old one and publish a new version
> (**Deploy → Manage deployments → edit → New version**), or translation
> backfills will be silently skipped (old deployments treat them as inserts
> of existing keys, which are ignored).
