# Kolel channels: source survey and taxonomy

**Status:** Survey — the factual input to `documents/plans/adding-series-plan.md`, and
before it to the catalogue redesign that is now implemented.
**Surveyed:** 2026-09-01, from full `yt-dlp --flat-playlist` listings plus YouTube Data API
playlist enumeration. Counts are a snapshot; nothing in the pipeline depends on them.

Every source in `adapters-plan.md` is **one rabbi's one series**, and every adapter is a
Python class with its playlist ids hardcoded. Institutional channels — a kolel's or a
yeshiva's shared feed — break both assumptions at once: one channel carries dozens of
rabbis and hundreds of series, and no number of new adapter classes keeps up.

This document is the evidence. The plan is next door.

---

## 1. The four channels

| Channel | Handle | Videos | Playlists | In a playlist | Shape |
| --- | --- | ---: | ---: | ---: | --- |
| כולל חזון עובדיה | `@כוללחזוןעובדיהמושבבןזכאי` | 4,650 | 3 | ~3% | **title-routed** |
| אור החיים | `@orhachaim_1` | 1,374 | 8 | **16.3%** | **title-routed** |
| מכון מאיר | `@Meir4All` | 7,362 | 170 | **51.3%** | **playlist-routed** |
| ישיבת הר עציון | `@HarEtzion-TheGush` | 7,966 | 561 | **90.7%** | **playlist-routed** |

**21,352 videos** across the four. The existing archive is 2,207 lessons.

Channel ids: `UCn2y_95ph3aCIQ87Fp7Z_0w`, `UCOAadJ9oU_GNK9BImoxLbNA`,
`UCEAZVyOtukIOH4BJ3gHKdng`, `UCpEUk0Kpt07ms4zHWFsXxhg`. The uploads playlist is the channel
id with `UC` → `UU`.

---

## 2. The taxonomy

The question that decides how a channel is ingested: **where does series identity live — in
the title, or in the playlist?**

**Shape A — title-routed.** Playlists absent or vestigial; the uploads feed is the only
complete listing, and both speaker and series come from the title. Viable only because the
titles are rigidly formatted. *Hazon Ovadia, Or HaChaim.*

**Shape B — playlist-routed.** Playlists carry real structure, often `<series> | <rabbi>`,
and are the natural series boundary — but they never cover the whole channel. *Meir,
Har Etzion.*

Neither is a superset of the other, and a channel can need both: Meir's playlists give clean
series for half the channel and the rest is reachable only by title.

**Playlist coverage must be measured, never assumed.** All four look playlist-organised at a
glance; coverage ranges 16.3% → 90.7%.

**So must speaker coverage.** Matching an honorific only at the start of a `|`/`:` segment
undercuts badly; matching one anywhere in the title is worth ~1,400 more attributions:

| Channel | Videos | Speaker at segment start | Speaker anywhere in title |
| --- | ---: | ---: | ---: |
| כולל חזון עובדיה | 4,650 | 4,507 | **4,529 (97.4%)** |
| אור החיים | 1,374 | 854 | **877 (63.8%)** |
| מכון מאיר | 7,362 | 5,964 | **6,611 (89.8%)** |
| ישיבת הר עציון | 7,966 | 4,059 | **4,771 (59.9%)** |

The gap is forms a narrow matcher misses — `ראש הישיבה הרב` (327 occurrences), `רה"י הרב`
(62), a name after a hyphen rather than a pipe — plus honorifics that are not `הרב` at all:
`ד"ר` (278), `פרופ'` (87), `הרבנית` (69), `פרופסור` (7), `Dr.` (22). **Not every speaker on
these channels is a rabbi.**

---

## 3. כולל חזון עובדיה — title-routed, 271 rabbis

4,650 videos, **271 distinct rabbis**, three near-empty playlists (145 items total — 1, 142
and 2). Even the largest covers only 142 of Gluchovsky's 333, so
`ButbulDailyHalachaAdapter`'s resolve-playlists-by-title-prefix trick has nothing to work
with. **The uploads playlist is the only complete listing.**

Titles are `הרב <name> : <topic>`:

| | |
| --- | ---: |
| Start with `הרב` (or a variant) | 4,499 / 4,650 — **96.8%** |
| Contain `:` | 4,231 / 4,650 — **91.0%** |
| Attributed to a rabbi by the census parser | 4,512 / 4,650 — **97.0%** |

**No title carries a date** — zero of 4,650 match a `DD.MM.YY` pattern, and there is no
Hebrew-date convention either. `recorded_at` must come from `published_at`.

### 3.1 Census

| # | Rabbi (as written on the channel) | Videos | Share | Planned |
| --- | --- | ---: | ---: | --- |
| 1 | בנימין חותה | 422 | 9.4% | **yes** |
| 2 | אלמוג לוי | 421 | 9.3% | **yes** |
| 3 | אברהם עובדיה | 399 | 8.8% |  |
| 4 | אהרן בוטבול | 392 | 8.7% | **yes** |
| 5 | גדעון בן משה | 378 | 8.4% |  |
| 6 | יחיאל גלוכובסקי | 330 | 7.3% | **yes** |
| 7 | נחמן ארוש | 200 | 4.4% |  |
| 8 | ליאור גלזר | 185 | 4.1% |  |
| 9 | אהרן זוהר | 158 | 3.5% |  |
| 10 | יעקב סיני | 131 | 2.9% | **yes** |
| 11 | חיים רבי | 85 | 1.9% |  |
| 12 | חיים גינצבורג | 72 | 1.6% |  |
| 13 | אמיר כהן | 60 | 1.3% |  |
| 14 | חיים יוסף אברגל | 56 | 1.2% |  |
| 15 | אליהו פינחסי | 53 | 1.2% |  |
| 16 | יצחק דעי | 52 | 1.2% |  |
| 17 | מיכאל רביע | 51 | 1.1% |  |
| 18 | מאיר אבוחצירא | 49 | 1.1% |  |
| 19 | יהודה מויאל | 37 | 0.8% |  |
| 20 | יגאל כהן | 32 | 0.7% |  |
| 21 | עובדיה יוסף בוטבול | 31 | 0.7% |  |
| 22 | מאיר אליהו | 29 | 0.6% |  |
| 23 | שניר גואטה | 27 | 0.6% |  |
| 24 | יצחק פנגר | 26 | 0.6% |  |
| 25 | ישראל אברגל | 25 | 0.6% |  |
| 26 | מאיר שוורץ | 24 | 0.5% |  |
| 27 | משה קינן | 23 | 0.5% |  |
| 28 | זמיר כהן | 22 | 0.5% |  |
| 29 | יהודה יוספי | 22 | 0.5% |  |
| 30 | יוסף חיים חדד | 21 | 0.5% |  |
| 31 | שניאור זלמן לוריא | 21 | 0.5% |  |
| 32 | ברוך רוזנבלום | 20 | 0.4% |  |
| 33 | אבי עובדיה | 20 | 0.4% |  |
| 34 | דניאל זדה | 19 | 0.4% |  |
| 35 | יוסף מוגרבי | 18 | 0.4% |  |
| 36 | שלמה לוינשטיין | 17 | 0.4% |  |
| 37 | ניסן שרוני | 17 | 0.4% |  |
| 38 | משה פרזיס | 16 | 0.4% |  |
| 39 | גבריאל סרף | 15 | 0.3% |  |
| 40 | דניאל בן ששון | 13 | 0.3% |  |
| 41 | מרדכי אינגלמן | 11 | 0.2% |  |
| 42 | דוד לאו | 11 | 0.2% |  |
| 43 | אברהם ישראל | 11 | 0.2% |  |
| 44 | שלומי קדוש | 10 | 0.2% |  |
| 45 | חנן אפללו | 10 | 0.2% |  |
**Long tail:** 226 further rabbis account for 470 videos (10.4%), each with fewer than 10:

אהרן טוייסיג (9) · שניאור אשכנזי (8) · יהודה סבאח (8) · חיים אלוש (8) · חגי לוי (8) · מיכאל לסרי (8) · יצחק קולדצקי (8) · אמיר ולר (8) · שלמה עמר (7) · משה ירוסלבסקי (7) · אופיר מלכה (7) · משה ארמוני (7) · חיים שלום סגל (6) · שלמה לווינשטיין (6) · בן ציון מוצפי (6) · שניאור ברוד (6) · פינחס אבוחצירא (6) · אייל עמרמי (6) · חיים יוסף דוד אברגל (6) · שמואל גלוכובסקי (6) · שי עמר (6) · אהרן אבוטבול (6) · יקיר נסימי (5) · מיכאל שושן (5) · שלמה עמאר (5) · שלום סגל (5) · משה יוסף (5) · מרדכי הלוי אינגלמן (5) · אהרון זוהר (5) · מנחם שטיין (5) · אברהם חזן (5) · יצחק אמסלם (4) · יחיאל מויאל (4) · יעקב שכנזי (4) · יחזקאל מוצפי (4) · ראובן אלבז (4) · אריה שכטר (4) · תמיר שלום (3) · מיכאל מירון (3) · שלמה עזרן (3) · אברהם יוסף (3) · מאיר מזוז (3) · משה יוסף נכד (3) · אהוד מולאי (3) · שמואל כהן (3) · ברוך גזהיי (3) · שלמה בניזרי (3) · נסים ארביב (3) · יוסף מזרחי (3) · ברק בן ניסן (3) · מאיר אבוחצירה (3) · מרדכי לוי (3) · נתנאל בן דוד (2) · משה חיים סגל (2) · יוסף דלויה (2) · נהוראי סבג (2) · אברהם יצחק (2) · משה שאלתיאל (2) · דוד נתנאל שוורץ (2) · יצחק מועלם (2) · אשר עובדיה (2) · אפרים עובדיה (2) · מקאליב (2) · יחיאל גוכובסקי (2) · שלמה יעקב ביטון (2) · שניאור גלוכובסקי (2) · חיים יוסף אברג'ל (2) · אלימלך בידרמן (2) · לידור סיטבון (2) · אורן נזרית (2) · יוסף בן פורת (2) · חיים זאיד (2) · יחיאל מאיר צוקר (2) · שלום לסקר (2) · משה פינטו (2) · יעקב ישראל פוזן (2) · מאיר מזוז ראש (2) · יעקב ישראל (2) · אלעזר שרעבי (2) · בן ציון (2) · גבריאל סרף אודיו (2) · יחיאל צוקר (1) · דלויה (1) · חיים משה סגל (1) · מאיר כהן (1) · אבר הם עובדיה (1) · חיים סגל (1) · עדיאל שפיגל (1) · יחיאל גלוכובקי (1) · שמעון גוטסמן (1) · אשר עובדיה חתן (1) · אבנר קוואס (1) · אהן בוטבול (1) · חיים יוסך אברגל (1) · אהר בוטבול (1) · דוד שלום נקי (1) · מקרלין (1) · דוד יוסף (1) · שניאור זלמן (1) · ליאור כהן (1) · חיים נינצבורג (1) · יחיאל גולוכובסקי (1) · אהר בטבול (1) · יהודה אייזנבך (1) · יחאל גלוכובסקי (1) · יחיאל גלועובסקי (1) · אברהם יוסף הכרת (1) · ברון רוזנבלום (1) · חיים שלמה אינגלמן (1) · אברה מוסלי (1) · אברהם מוסלי (1) · מיכאל עמוס (1) · שלמה לוונשטיין (1) · עידו במרגי (1) · חיים דוד אברגל (1) · נריה ברבי (1) · יחיאל גלוכוובסקי (1) · אברהם עובדיה אמר (1) · מרדכי אוחיון (1) · יעקב בן שבת (1) · פינחסי (1) · אילן גוזל (1) · דניאל זאדה (1) · צ'ברחובסקי חיים (1) · חנניה מנס (1) · שי עטרי (1) · אשר עובדיה חתנו (1) · יעקב בובליל (1) · יעקב שבתאי (1) · מיכאל בן שושן (1) · יהושע כהן (1) · בנימין קטורזה (1) · עמרם שחר (1) · יחיאל גלוכובסקי וכן (1) · אורי בלוי (1) · נתנאל רביבו (1) · אהרן בוטבטול (1) · אברהם כהן (1) · שוורץ (1) · אושרי מויאל (1) · חיים יוסף דוד (1) · יוסף עובדיה בוטבול (1) · שמואל בצלאל (1) · אופיר טנג'י (1) · מקליב (1) · יוסף חיים דוד אברגל (1) · עמרם יוסף הלברשטאם (1) · ליאוןר גלזר (1) · משה עמר (1) · אליסף בן טוב (1) · שמשון הכהן (1) · יצחק עטיה (1) · חגי יוסף (1) · חיים אלמקייס (1) · יניב עזיז (1) · איתמר גימאני (1) · נתנאל אביסרור (1) · ארז פינחס (1) · אסי טובי (1) · אפי עובדיה (1) · דניאל ששון (1) · נתנאל מלכה (1) · אלמוג (1) · לוריא שניאור (1) · אלעזר אלמליח (1) · משה יוסף בן (1) · מאיר מאזוז (1) · שלמה בנזרי (1) · שלום ארוש (1) · אליהו שוויכה (1) · יעקב לייפר (1) · גזהיי ברוך (1) · אהוד מולא (1) · אליאור עמר (1) · יחיאל גלוככובסקי (1) · יחיאיל גלוכובסקי (1) · יחיאל תניא (1) · יעקב ששון נכדו (1) · בועז שלום (1) · רפאל דרעי (1) · יוסף לרר (1) · נחום רבינוביץ (1) · ישראל אברג'ל (1) · יהושע הכהן (1) · אהרו בוטבול (1) · יוסף חיים אוהב ציון (1) · אליהו פנחסי (1) · יעקב לוי (1) · דן מונסונגו (1) · צבי יוסף בן פורת (1) · נח ברגר (1) · אהרו זוהר (1) · יצחק כרמי (1) · שמעון יוחאי יפרח (1) · רביד נגר (1) · קובי לוי (1) · אברהם בן אסולין (1) · מנחם מנדל גלוכובסקי (1) · יוסי מזרחי (1) · פנחס אבוחצירה (1) · הראשי דוד לאו (1) · פנחס אבוחצירא (1) · דן בן משה (1) · יעקב ישראל לוגסי (1) · פנגר (1) · יוסף צבי (1) · אליהו חלימי (1) · דוד פאור (1) · בוטבול תפילה (1) · שאלתיאל מאיר (1) · אורי וילהלם (1) · חיים שלום (1) · יצחק לנדא (1) · גלזר ליאור (1) · ישועה עטיה (1) · מרדכי כהן (1) · יצחק יוסף יום (1) · עזריאל שפירא (1) · אליהו שוויכה אודיו (1) · אהרן בטבול (1) · בניהו שמואלי (1) · יורם אברגל (1) · טוייסיג אודיו (1) · גדעוו בן משה (1) · ברוך שרגא (1) · בוטבול הלכות (1)

**Method and its limits.** Bidi control characters stripped; a leading
`הרב` / `הגאון הרב` / `הרה"ג` / `רב` / `האדמו"ר` / `מרן` matched; everything up to the first
`:` taken as the name. For the 9% with no colon, the first two words, extended past a
connector (`בן`, `בר`, `הלוי`). **138 titles (3.0%) are unattributed** — schedules
(`לוח שיעורים`, `לו"ז`), holiday notices, titles with no `הרב` prefix. **The long tail is
noisy**: some single-video entries are spelling variants of rabbis listed higher, not
distinct people. The head (≥10 videos) is reliable; the tail is indicative.

### 3.2 Name traps

The reason matching must be on a **full name anchored at the start of the title**, never a
surname substring.

| Trap | Detail |
| --- | --- |
| `אבוטבול` contains `בוטבול` | `אהרן אבוטבול` (6) is a **different rabbi** whom a substring match silently absorbs |
| `בוטבול` is not unique | `אהרן בוטבול` (392) shares the channel with **`עובדיה יוסף בוטבול`** (29) — a different person |
| `לוינשטיין` contains `לוי` | Matching `לוי` picks up `שלמה לוינשטיין` (16), `חגי לוי` (8), `מרדכי הלוי אינגלמן` (5), `מרדכי לוי` (3) |
| `גלוכובסקי` is not unique | `יחיאל גלוכובסקי` (330) vs **`שמואל גלוכובסקי`** (6) and `שניאור גלוכובסקי` (2) — and שמואל also teaches תניא |
| `סיני` is also a topic | `גדעון בן משה` and `נחמן ארוש` mention הר סיני; only a start-anchored match isolates `יעקב סיני` |
| `אהרן` / `אהרון` | Butbul is spelled both ways — 360 and 32. Same rabbi. |
| `חותה`, not `חוטה` | The channel spells it **`בנימין חותה`** (ת) in all 421 titles. `חוטה` (ט) returns **zero** hits. |
| `יצחק דעי` / `דיעי` / `דיין` | Three spellings, merged to 52 above. Not a target; flagged so a later pass doesn't treat them as three rabbis. |

### 3.3 Gluchovsky's תניא series

333 videos by `יחיאל גלוכובסקי`, of which **320 contain `תניא`**; the other 13 are holiday
talks and התוועדות. So his series is defined by rabbi **plus a topic keyword**, not rabbi
alone. Only **124 of 320** carry a `שיעור N` number, with 22 gaps in 1..123 — **numbering is
not usable as a key.**

---

## 4. אור החיים — title-routed, one dominant rabbi

1,374 videos. Eight playlists covering **224 (16.3%)** — vestigial.

Titles are dash-delimited, not colon-delimited (**one** title in 1,374 contains a colon):

```
הרב אלבז - סליחות - ליל י"ט אלול תשפ"ו
הרב אלבז – שיעור המוסר השבועי – פרשת כי תבוא תשפ"ו
ביאורים על פרשת השבוע - פרשת כי תבוא תשפ"ו
```

The channel is **Rabbi Reuven Elbaz's** (אור החיים is his yeshiva); the second segment is
the series.

| First segment | Videos | | Elbaz series (2nd segment) | Videos |
| --- | ---: | --- | --- | ---: |
| `הרב אלבז` | 826 | | שיעור המוסר השבועי | 282 |
| `ביאורים על פרשת השבוע` (no rabbi) | 130 | | סליחות | 187 |
| `חידון הלכה למעשה` | 46 | | מעמד התיקון לביטול הגזירה הנוראה | 48 |
| `הרב ראובן אלבז`, `סליחות הרב אלבז` | 10 | | שיחת פתיחה | 14 |

**Traps:** the separator is both ASCII hyphen `-` **and** en-dash `–`, mixed within the same
channel and sometimes the same title. Hebrew dates **are** present here
(`ליל י"ט אלול תשפ"ו`), so `hebrew_date.py` applies — unlike Hazon Ovadia.

---

## 5. מכון מאיר — playlist-routed, and workable

7,362 videos, 170 playlists, **3,779 in a playlist (51.3%)**, **3,583 orphans**, 351 in more
than one playlist.

Playlist titles are `<series> | <rabbi>`, and **102 of 170 (60%) name a rabbi**, covering
2,500 items. These map onto rabbi + series with no invention:

| Playlist | Items |
| --- | ---: |
| לימוד בספר דברים תשס"ט - תשע"ב \| סדרת שיעורים \| הרב שרקי | 106 |
| פסיכותרפיה יהודית \| ד"ר מיכאל אבולעפיה | 95 |
| פרקי אבות סדרת שיעורים \| הרב אורי שרקי | 93 |
| ספר הכוזרי לריה"ל \| סדרת לימוד התשע"ז \| הרב אורי שרקי | 92 |
| ספר במדבר \| סדרת שיעורים \| הרב אורי שרקי | 76 |
| נפש החיים לר' חיים מוולוז'ין \| הרב אורי שרקי | 73 |

**Rabbis have many series here.** By video count: אורי שרקי 952 · אייל ורד 483 ·
חגי לונדין 358 · דב ביגון 319 · ליאור לביא 232. Sharki alone has ~30 playlists, one per book.

### 5.1 Are playlists single-rabbi?

Measured across the 168 non-empty playlists, after normalising speaker strings (a raw
segment like `הרב אורי שרקי - פרקי אבות שיעור 9` must be truncated at the dash, or one rabbi
counts as ninety):

| | |
| --- | ---: |
| Single rabbi | 113 |
| Dominant — ≥90% one rabbi | 6 |
| **Genuinely mixed** | **32** |
| No speaker named at all | 17 |

**71% are effectively single-rabbi.** Every genuinely mixed one is a *thematic anthology*,
not a lesson series — `אמונה והשקפה` (104 videos, 18 rabbis), `קטעים קצרים לחיזוק "מלחמת
חרבות הברזל"` (68, 22), `עוצמה נשית` (47, 25), `ימי בין המצרים | תשעה באב` (24, 10). Every
real series — `ספר הכוזרי`, `מסילת ישרים`, `מורה נבוכים`, `נפש החיים` — is one rabbi
teaching one book start to finish. **Both shapes must be representable.**

### 5.2 Titles do not give series here

Video titles are `<lesson> | <series> | <rabbi>`, but the middle segment matches a playlist
name in only **18 of 876** distinct cases. **Playlists are authoritative; titles are not** —
the exact opposite of Hazon Ovadia.

The 68 playlists not naming a rabbi in a pipe segment are not all lost: some name one after
a hyphen (`הלכה יומית - אורח חיים - הרב מרדכי ענתבי`, 100 items), so a parser should try
both separators.

---

## 6. ישיבת הר עציון — best organised, hardest to attribute

7,966 videos, **561 playlists**, **7,224 in a playlist (90.7%)** — only 742 orphans, and
2,031 videos in more than one playlist. 92% of titles are pipe-delimited. **Coverage is the
best of all four**, and playlists are a sound series boundary.

The difficulty is entirely attribution:

| Problem | Evidence |
| --- | --- |
| Playlists organised by **topic, not rabbi** | Only **131 of 561** (23%) name a rabbi. The largest are `דף יומי \| מסכת X` — by tractate. |
| Many videos name no rabbi *at the start of a title segment* | `הדף היומי`: 892 videos. **But the series is taught throughout by `הרב אודי שוורץ`**, named in every description; and titles like `שיעור תנ"ך \| ספר יהושע \| ראש הישיבה הרב יעקב מדן` do name one, just not in a form a narrow matcher catches. 39 of 50 sampled are recoverable. |
| Series with **rotating** teachers | `חידוש מהגוש` — 417 videos, 25 distinct speakers. `פרשת שבוע \| English` — 409 videos, 288. |
| **Co-taught** lessons | `הרב יעקב מדן והרב אמנון בזק` — 289 videos. Two rabbis, one lesson. |
| Tiny playlists | Median 8 items; **165 of 561** have fewer than 5. |

Under the redesign these are representable (per-lesson speakers, zero or many). What remains
is a **curation** question — which of 561 playlists are worth having — not a schema one.

**Descriptions carry attribution the titles omit.** In a 50-video sample of Har Etzion's
3,907 title-unattributed videos, **39 (78%) name a rabbi in the description**; at Meir,
18 of 50 (36%). The YouTube Data API call the pipeline already makes for `published_at`
requests `part=snippet` and discards the description, so this costs no extra quota — see
`catalogue-redesign-plan.md` §4.3.

---

## 7. Related documents

- `documents/plans/adding-series-plan.md` — the plan this survey now feeds.
- `documents/plans/implemented/catalogue-redesign-plan.md` — the redesign it fed first.
- `documents/pipelines/discover.md` — the pipeline these channels plug into.
- `documents/database-schema.md` §2 — the rabbi→series→lesson shape §5.1 and §6 strain.
