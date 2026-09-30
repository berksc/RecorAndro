# RecorAndro v0.1 — Teknik Kurulum ve Codex Geliştirme Planı
## PART 1 / 3 — Faz 0–2
### Teknik baseline → Recora behavioral parity → Media contract freeze → Android local scaffold → Storage preflight → Audio core

**Proje:** RecorAndro  
**Hedef sürüm:** v0.1  
**Bu dosya:** PART 1 / 3  
**Kapsam:** Faz 0, Faz 1, Faz 2  
**Sonraki dosya:** `RECORANDRO_V0.1_SETUP_PART2.md`

---

# 0. Bu bölümün amacı

Bu bölüm tamamlandığında RecorAndro'nun Android üzerinde çalışan ilk gerçek çekirdeği hazır olmalıdır.

Başarı durumunda sistem:

- Xiaomi Redmi Note 10 Pro üzerinde çalışır.
- Termux + Python + FFmpeg/ffprobe tabanlıdır.
- Tamamen local çalışır.
- Bir session için tam olarak 1 audio kabul eder.
- 0..N fotoğraf opsiyonunu veri modelinde destekler; ancak görsel subsystem bu bölümün çekirdeği değildir.
- Seçilen audio'yu işlem öncesi storage preflight ile değerlendirir.
- Yeterli alan varsa original audio'yu managed session alanına byte-for-byte import eder.
- Original'ın hash/size değerini doğrular.
- ffprobe ile media inspection yapar.
- Recora'nın gerçek çalışan implementation'ından doğrulanmış normalization davranışını uygular.
- Auto / Force / Off normalization semantiğini destekler.
- Recora parity'si doğrulanmış segmentation davranışını temel alır.
- Auto / Force / Off segmentation semantiğini destekler.
- Tiny first/last part üretmemeye çalışan deterministik segmentation davranışını uygular.
- Source timeline'ı korur.
- Silence silmez.
- Gap üretmez.
- Source-end coverage sağlar.
- Android'de gerçek lecture audio için kullanılabilir part audio çıktıları oluşturur.

Bu bölümde henüz günlük Android UI, Tasker/shortcut, native shell, visual metadata subsystem, final manifest/report/package/archive tasarımı, Android background hardening, root helper ve ChatGPT/Notion/PACE entegrasyonu tamamlanmayacaktır.

---

# 1. Canonical ürün kontratı — PART 1 boyunca değişmeyecekler

## 1.1 Input

Bir RecorAndro session'ın canonical input'u:

```text
exactly 1 audio
+
optionally 0..N photos
```

RecorAndro v0.1 **audio-first** bir sistemdir.

PART 1'in birincil acceptance fixture'ı:

```text
1 audio
0 photos
```

olacaktır.

0 fotoğraf:
- edge-case değildir,
- warning üretmez,
- ekstra confirmation gerektirmez,
- missing-feature state değildir,
- audio pipeline davranışını hiçbir şekilde düşürmez.

## 1.2 Recora parity tanımı

Recora:
- frozen reference implementation,
- çalışan davranış kaynağı,
- media-processing reference,
- test/edge-case kaynağı

olarak kullanılacaktır.

> **Recora parity means media-processing behavior and invariants only. It does not imply code, filesystem, state-machine, deployment or architecture parity.**

RecorAndro; Recora'nın FastAPI/web, Windows runtime, Cloudflare, remote upload/download, server auth veya deployment baggage'ını taşımayacaktır.

Taşınacak olan:
- canonical media decisions,
- normalization semantics,
- segmentation semantics,
- source preservation,
- source-end coverage,
- overlap semantics,
- media integrity invariants,
- uygun test fixture ve acceptance expectations

olacaktır.

## 1.3 Root politikası

> **Root is an optional capability, not the execution model.**

Normal Termux user context içinde çalışması hedeflenenler:
- ffprobe
- FFmpeg
- hashing
- audio analysis
- normalization
- segmentation
- session metadata
- manifests
- packaging

PART 1 audio core root gerektirmemelidir.

## 1.4 Original media

Original protection non-negotiable'dır.

- Kaynak audio overwrite edilmez.
- Processing external URI/path üzerinde yapılmaz.
- Storage preflight geçmeden import başlamaz.
- Import sonrası managed original byte-for-byte korunur.
- Derived output ayrı alanda tutulur.
- Destructive cleanup PART 1 kapsamı dışındadır.

---

# FAZ 0 — Teknik baseline ve media davranışını freeze etme

# Adım 0.1 — Final cihaz / Android baseline'ını kaydet

## Amaç

RecorAndro'nun geliştirme ve gerçek-device test referansını kayıt altına almak.

## Neden

Planlama anındaki Android 12 / MIUI Global 13.0.7 yalnızca pre-update referansıdır. Teknik implementasyon, resmi stabil OTA tamamlandıktan sonra cihazın gerçek final build'i üzerinden yürütülmelidir.

## Ön koşullar

İdeal sıra:

1. Cihazı desteklenen en güncel resmi stabil OTA'ya güncelle.
2. Normal cihaz işlevini kontrol et.
3. Final Android/MIUI build'i kaydet.
4. Root işlemini bağımsız olarak tamamla veya root durumunu açıkça `not yet rooted` olarak kaydet.
5. RecorAndro technical baseline oluştur.

## Model / Efor

**GPT-6 Sol — Medium**

## Codex Promptu

```text
We are starting a new Android-first local project named "RecorAndro".

Do not implement media processing yet.

Your task is to create the technical baseline documentation and the smallest repository skeleton needed to record the real Android device/environment state.

Important product context:

- RecorAndro is Android-first, local-first, user-triggered and audio-first.
- It is a separate project from Recora.
- Recora remains a frozen Windows/server reference implementation.
- RecorAndro must not inherit Recora's server, Cloudflare, Windows deployment, remote-upload, or web architecture.
- Primary device: Xiaomi Redmi Note 10 Pro, 128 GB.
- The device is secondary, not the user's primary phone.
- The device may later be rooted, but root is optional and must not be the normal execution model.
- Core processing should remain usable from a normal Termux user context.
- Canonical session input is exactly 1 audio + optionally 0..N photos.
- Zero-photo sessions are fully normal first-class sessions.

Do not guess the final Android/MIUI build.

Create a minimal repository if none exists, and add:

docs/DEVICE_BASELINE.md

The document must have clearly marked fields for:

Device:
- manufacturer
- model
- storage capacity
- approximate free storage at baseline

OS:
- Android version
- MIUI version
- exact build/version string if available
- security patch date if available

Environment:
- root status: rooted / unrooted / planned
- Termux source/version when installed
- Python version when installed
- FFmpeg version when installed
- ffprobe version when installed
- architecture / ABI if easy to determine

Operational notes:
- device is also used as an iPhone hotspot
- Xiaomi/MIUI background restrictions are a future real-device constraint
- root must not become a dependency of the normal media-processing core

Also create:

docs/SCOPE.md

with a concise statement that RecorAndro v0.1 is:
- Android-first
- local-first
- user-triggered
- audio-first
- exactly 1 audio + optional 0..N photos
- complete and valid with zero photos
- no PC required
- no server
- no Cloudflare
- no database
- no OpenAI API
- no Notion API
- no transcription engine
- no OCR
- no cloud sync

Add the invariant:

"Recora parity means media-processing behavior and invariants only. It does not imply code, filesystem, state-machine, deployment or architecture parity."

Do not add Android-specific workarounds yet.
Do not add root code.
Do not install tools automatically.

Before editing:
1. inspect the current repository
2. summarize existing files
3. list planned changes

After editing:
1. list created/modified files
2. show which DEVICE_BASELINE fields still require manual user input
3. stop after this step
```

## Codex'in üretmesi gerekenler

Minimum:

```text
recorandro/
├── docs/
│   ├── DEVICE_BASELINE.md
│   └── SCOPE.md
└── README.md
```

## Şimdi senin yapman gereken

1. Final OTA tamamlandıysa Android version, MIUI version, exact build ve security patch bilgilerini gir.
2. Root tamamlandıysa root durumunu kaydet; tamamlanmadıysa `planned / not yet installed` bırak.
3. Yaklaşık boş alanı kaydet.
4. Termux henüz kurulmadıysa Termux/Python/FFmpeg alanlarını `pending` bırak.

## Test prosedürü

Dokümantasyon kontrolü:
- final build tahmin edilmemiş olmalı,
- pre-update MIUI referansı final baseline gibi yazılmamalı,
- root core dependency olarak tanımlanmamalı.

## Başarı kriterleri

- [ ] Final cihaz baseline dosyası var.
- [ ] Gerçek Android/MIUI build kaydedildi veya açıkça pending.
- [ ] Root durumu açık.
- [ ] Audio-first / 0-photo first-class workflow açık.
- [ ] Recora parity yalnız behavioral parity.
- [ ] Server/cloud baggage scope dışında.

## Sorun çıkarsa — düzeltme promptu

```text
Revise only the RecorAndro baseline/scope documentation.

Do not implement features.

Correct the documentation so that:
- final Android/MIUI values are factual, not guessed
- root is optional and not the processing model
- zero-photo sessions are first-class
- Recora parity is behavioral/media parity only
- no Recora server/Windows/cloud architecture leaks into RecorAndro

Stop after the documentation correction.
```

## Sonraki adıma geçiş koşulu

`DEVICE_BASELINE.md` ve `SCOPE.md` gerçek durumu doğru yansıtmalı.

---

# Adım 0.2 — Gerçek Recora implementation parity extraction

## Amaç

RecorAndro'nun media behavior baseline'ını hafızadan veya eski plan metninden değil, **gerçek çalışan Recora implementation'ından** çıkarmak.

## Ön koşullar

- RecorAndro repo hazır.
- Recora GitHub repository erişilebilir.
- Recora frozen reference olarak değiştirilmeyecek.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
This step is a reference-extraction task.

Do NOT implement RecorAndro media processing yet.
Do NOT modify the Recora repository.

Inspect the actual current working Recora implementation and its relevant tests/docs.

Primary source of truth:
- real Recora code
- real Recora tests
- current frozen Recora documentation

Do not rely on remembered values or old planning text when implementation differs.

Goal:
Extract Recora's canonical MEDIA-PROCESSING behavior for RecorAndro.

Create in the RecorAndro repository:

docs/RECORA_MEDIA_PARITY.md

The document must identify the exact Recora implementation files/tests used as evidence and extract:

A. Input/media support
- accepted input audio containers/extensions
- accepted/observed codecs where enforced or tested
- MIME/format validation behavior relevant to media processing
- unsupported media behavior

B. ffprobe/media inspection
- selected stream logic
- duration source/validation
- codec/sample rate/channel handling
- creation-time behavior if relevant
- failure behavior

C. Normalization
- exact measurement method
- exact FFmpeg filter/measurement configuration
- Auto normalization threshold(s)
- target loudness
- maximum boost
- peak/true-peak ceiling
- minimum useful boost if present
- skip logic
- Force behavior if Recora has a direct equivalent
- output codec/container
- sample-rate behavior
- channel behavior
- bitrate/quality behavior
- duration/integrity checks
- original hash protection
- failure behavior

D. Segmentation analysis
- exact target duration
- search-window minimum/maximum
- silence/quiet threshold
- minimum quiet duration
- quiet-region candidate selection/ranking
- deterministic fallback behavior
- short-file behavior
- any existing protection against tiny parts
- source-end handling

E. Segment export
- exact overlap behavior
- exact global start/end semantics
- no-gap/source coverage checks
- output format/container
- codec
- bitrate/quality
- sample-rate/channel policy
- whether Recora stream-copies or re-encodes segments
- why
- output duration/probe verification
- final-part behavior

F. Media integrity invariants
- silence removal policy
- source timeline preservation
- original immutability
- hash/size checks
- derived-file verification
- relevant FFmpeg subprocess safety behavior

G. Relevant test fixtures
Identify Recora tests/fixtures worth reusing semantically in RecorAndro:
- short audio
- ~61 minute
- ~90 minute
- quiet audio
- loud audio
- no suitable silence
- overlap/source-end
- malformed media

Important invariant:

"Recora parity means media-processing behavior and invariants only.
It does not imply code, filesystem, state-machine, deployment or architecture parity."

Explicitly mark OUT OF SCOPE FOR PARITY:
- FastAPI
- remote upload
- resumable network upload
- Cloudflare
- Windows runtime
- Windows autostart
- server authentication
- web UI
- remote downloads
- Recora server-state architecture

At the end create a table:

Behavior | Actual Recora implementation | RecorAndro baseline candidate | Evidence

Do NOT freeze RecorAndro values yet.
This step only extracts factual Recora behavior.

Before writing:
- inspect the Recora repository
- list the implementation/test files you will use

After writing:
- report any conflict between code, tests and docs
- treat working code/tests as higher confidence than stale prose
- list any media behavior that is still ambiguous
- stop before RecorAndro implementation
```

## Codex'in üretmesi gerekenler

Ana çıktı:

```text
docs/RECORA_MEDIA_PARITY.md
```

Özellikle şu sorular açık cevaplanmalı:

```text
Normalization:
- When exactly does Auto apply?
- What exact target/ceiling/boost values exist?

Segmentation:
- What exact target/window/quiet/overlap values exist?

Generated audio:
- What exact codec/container?
- Encode or stream-copy?
- What bitrate / sample-rate / channels?
```

## Şimdi senin yapman gereken

Codex tamamladıktan sonra:
1. `RECORA_MEDIA_PARITY.md`
2. exact normalization değerleri
3. exact segmentation değerleri
4. media output format/codec bilgisi
5. Recora'da tiny-part protection var mı/yok mu
6. code/docs/test conflict varsa özeti

kontrol et.

Henüz RecorAndro değerlerini elle değiştirme.

## Test prosedürü

Extraction review:
- değerler gerçek source code/test referanslı mı?
- eski setup MD source-of-truth yapılmamış mı?
- server kodu parity kapsamına sızmış mı?
- media output format açık mı?

## Başarı kriterleri

- [ ] Normalization canonical davranışı çıkarıldı.
- [ ] Segmentation canonical davranışı çıkarıldı.
- [ ] Output codec/container çıkarıldı.
- [ ] Stream-copy vs encode net.
- [ ] Sample-rate/channel politikası net.
- [ ] Test fixture listesi çıkarıldı.
- [ ] Server baggage parity dışında.
- [ ] Ambiguity varsa açıkça kaydedildi.

## Sorun çıkarsa — düzeltme promptu

```text
Re-run only the Recora media-parity extraction.

The previous extraction is incomplete or relied too heavily on planning documentation.

Use the actual Recora implementation and tests as the primary source of truth.

Do not modify either project.

Specifically resolve:
[PASTE MISSING OR CONFLICTING ITEM]

Return evidence from the exact Recora implementation/test files and update docs/RECORA_MEDIA_PARITY.md.

Do not proceed to RecorAndro implementation.
```

## Sonraki adıma geçiş koşulu

Recora media davranışının gerçek canonical referansı yeterince net olmalı.

---

# Adım 0.3 — RecorAndro v0.1 behavior + media format contract freeze

## Amaç

RecorAndro audio core başlamadan önce threshold'ları ve **media input/output contract'ını** kesinleştirmek.

## Ön koşullar

- Adım 0.2 tamam.
- `RECORA_MEDIA_PARITY.md` mevcut.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- docs/SCOPE.md
- docs/DEVICE_BASELINE.md
- docs/RECORA_MEDIA_PARITY.md

Do NOT implement the audio engine yet.

Goal:
Freeze the RecorAndro v0.1 behavioral and media-format contract.

Create:

docs/MEDIA_CONTRACT.md
docs/BEHAVIOR_CONTRACT.md

Use the ACTUAL Recora media implementation as the preferred baseline.
Do not create Android-specific divergence unless there is a concrete reason.

PART A — MEDIA INPUT CONTRACT

Define:
1. Supported input containers/extensions for v0.1.
2. Supported codec handling policy.
3. What is rejected before processing.
4. Whether unknown-but-ffprobe-readable formats are allowed or rejected.
5. Whether the original input is ever transcoded merely for import.

PART B — NORMALIZED OUTPUT CONTRACT

Freeze:
- normalized output container
- normalized output codec
- bitrate/quality mode
- sample-rate policy: preserve / normalize / conditional conversion
- channel policy: preserve / normalize / conditional conversion
- duration tolerance
- filename convention

Prefer Recora's proven behavior unless Android/Termux requires documented divergence.

PART C — GENERATED PART AUDIO CONTRACT

Freeze:
- part output container
- codec
- bitrate/quality
- sample-rate behavior
- channel behavior
- stream-copy vs re-encode behavior
- seek/cut accuracy policy
- output verification requirements
- global source-range semantics

PART D — NORMALIZATION SEMANTICS

Define exact v0.1:

Auto
- exact measured decision threshold
- exact target
- exact boost ceiling
- exact peak ceiling
- minimum useful boost if applicable
- exact skip behavior

Force
- must process intentionally
- must still obey safety/peak constraints
- define behavior when source is already loud
- never overwrite original

Off
- no normalization
- segmentation uses the appropriate non-normalized source path
- original remains immutable

PART E — SEGMENTATION SEMANTICS

Define:

Auto
- short enough => one part
- long enough => segment
- exact auto segmentation threshold

Force
- intentionally segment even when Auto would keep one part
- still obey useful-part invariants

Off
- one generated canonical audio output / no multi-part segmentation
- define whether packaging references original or a safe generated copy

Freeze:
- nominal target duration
- search-window min/max
- quiet threshold
- minimum quiet duration
- candidate ranking
- deterministic fallback
- overlap duration
- source-end coverage
- no-gap requirement

PART F — TINY PART AVOIDANCE

Add this invariant:

"Segmentation may deviate from the nominal target duration to avoid nonsensical tiny first or last parts."

Define an explicit deterministic policy.

Requirements:
- no meaningless ~1–3 minute first/last leftover when a nearby valid redistribution is possible
- avoid creating a tiny final tail merely to stay close to nominal targets
- preserve source coverage
- preserve no-gap behavior
- preserve overlap semantics
- remain deterministic

Document examples around:
- just above one-part threshold
- ~26–30 min
- ~49–55 min
- ~51–53 min tiny-tail risk
- ~74–80 min
- ~90 min

PART G — FULL ARCHIVE POLICY

Do NOT freeze Lecture default ON.

Freeze only:
- full archive is a supported capability
- profile-controlled
- exact Lecture default remains pending real-device storage/performance measurements

PART H — VISUAL NON-DEPENDENCY

Re-state:
- zero-photo sessions are fully complete
- visual data is not required by any media-processing step
- no hard visual->audio mapping in v0.1

At the end create a concise canonical constants/decision table.

Also create a "Pending after real-device measurement" section.

Do not implement code.

Before writing:
- compare every proposed default against docs/RECORA_MEDIA_PARITY.md
- identify any intentional divergence and justify it explicitly

After writing:
- list all frozen constants
- list all intentionally still-unfrozen decisions
- stop before implementation
```

## Codex'in üretmesi gerekenler

```text
docs/MEDIA_CONTRACT.md
docs/BEHAVIOR_CONTRACT.md
```

## Şimdi senin yapman gereken

Özellikle kontrol et:

### Media
- input formats
- normalized output format
- part output format
- codec
- bitrate/quality
- sample rate
- channels
- stream-copy / encode

### Normalization
- Auto exact behavior
- Force exact behavior
- Off exact behavior

### Segmentation
- Auto threshold
- Force
- Off
- nominal target
- window
- silence threshold
- min quiet
- overlap
- tiny-part rule

### Yanlışlıkla freeze edilmemesi gerekenler
- Lecture full archive default
- Android daily UX technology
- root helper behavior
- Xiaomi-specific optimization

## Test prosedürü

Implementation testi yok.

Duration tabloları üzerinden beklenen part yapısını mantıksal olarak kontrol et:

```text
5 min
25 min civarı
26–30 min
49–55 min
61 min
74–80 min
90 min
```

## Başarı kriterleri

- [ ] Media input contract açık.
- [ ] Generated audio contract açık.
- [ ] Normalized audio contract açık.
- [ ] Stream-copy/encode kararı açık.
- [ ] Sample-rate/channel policy açık.
- [ ] Auto/Force/Off semantics açık.
- [ ] Tiny first/last avoidance deterministik.
- [ ] Full Archive default measurement-dependent.
- [ ] 0-photo workflow core contract içinde.
- [ ] Recora divergence varsa gerekçeli.

## Sorun çıkarsa — düzeltme promptu

```text
Revise only the RecorAndro v0.1 media/behavior contract.

Do not implement code.

Problem:
[PASTE SPECIFIC AMBIGUITY OR BAD DECISION]

Use docs/RECORA_MEDIA_PARITY.md as the preferred implementation baseline.

Preserve:
- Android-local architecture
- behavioral parity only
- original immutability
- no silence deletion
- no gaps
- source-end coverage
- tiny-part avoidance
- zero-photo first-class workflow

Do not freeze Full Archive Lecture default before real-device measurements.
```

## Sonraki adıma geçiş koşulu

Media behavior implementation sırasında yeniden tartışılmayacak kadar açık olmalı.

---

# FAZ 1 — Android local foundation

# Adım 1.1 — Termux / Python / FFmpeg environment + project scaffold

## Amaç

RecorAndro audio core'un çalışacağı sade Android-local runtime'ı kurmak.

## Model / Efor

**GPT-6 Sol — Medium**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read and obey:
- docs/SCOPE.md
- docs/DEVICE_BASELINE.md
- docs/RECORA_MEDIA_PARITY.md
- docs/MEDIA_CONTRACT.md
- docs/BEHAVIOR_CONTRACT.md

Goal:
Create the minimal Android/Termux Python project scaffold and environment diagnostics.

Do not implement normalization or segmentation yet.

Architecture constraints:
- Android-first
- local-only
- no server
- no FastAPI
- no web backend
- no database
- no Docker
- no OpenAI API
- no Notion API
- no root requirement
- no native Android app yet

Create a small Python package.

Suggested concepts:
recorandro/
  config.py
  diagnostics.py
  media/
  sessions/
  utils/
  cli.py

Keep the structure minimal.

Requirements:

1. Support execution as `python -m recorandro ...` and/or a small CLI entry point.
2. Add a diagnostics command such as `recorandro doctor`.
3. Diagnostics should report:
   - Python version
   - platform/Android identification where available
   - Termux context if detectable
   - FFmpeg path/version
   - ffprobe path/version
   - current configured RecorAndro data root
   - writable data root
   - free storage bytes
   - root status only as informational; do not require root
4. Configuration:
   - local config file and/or environment variables
   - no secrets needed
   - explicit data root
   - sane defaults for Termux/Android
   - do not assume unrestricted arbitrary Android path access
5. Use safe subprocess argument lists.
6. shell=True is forbidden.
7. Add lightweight local logging.
8. Do not log media contents.
9. Add tests for configuration/diagnostics where practical.
10. Add .gitignore for caches, venv, generated session data and local config.
11. Add docs/TERMUX_ENVIRONMENT.md with manual install/check steps and no automatic root operations.

Do not execute destructive package-management or root commands automatically.
Generate exact manual instructions instead.

Before editing:
- inspect repo
- list planned files

After editing:
- run tests available in the current environment
- report exact Android/Termux manual commands required
- stop before session import/media processing
```

## Codex'in üretmesi gerekenler

- Python package scaffold
- `doctor`
- config
- diagnostics
- tests
- `docs/TERMUX_ENVIRONMENT.md`

## Şimdi senin yapman gereken

Android/Termux üzerinde Codex'in verdiği manuel kurulum adımlarını uygula.

Sonra:

```text
python
ffmpeg
ffprobe
```

çalışıyor mu kontrol et.

Ardından `doctor` komutunu çalıştır ve gerçek versiyonları `DEVICE_BASELINE.md` içine geçir.

## Test prosedürü

Gerçek Redmi üzerinde:
- doctor
- data root write
- free-space read
- root olmadan execution

## Başarı kriterleri

- [ ] Python çalışıyor.
- [ ] FFmpeg çalışıyor.
- [ ] ffprobe çalışıyor.
- [ ] RecorAndro import ediliyor.
- [ ] Doctor çalışıyor.
- [ ] Free storage okunuyor.
- [ ] Core root istemiyor.
- [ ] Server/web framework yok.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only the RecorAndro Android/Termux project environment.

Do not implement media processing.

Problem:
[PASTE ERROR]

Check:
- Python/package layout
- Termux paths
- FFmpeg/ffprobe discovery
- writable data root
- Android path assumptions

Do not add root as a workaround unless normal Termux execution is proven impossible.

Make the smallest fix and update docs/TERMUX_ENVIRONMENT.md.
```

## Sonraki adıma geçiş koşulu

Gerçek Redmi üzerinde `doctor` PASS olmalı.

---

# Adım 1.2 — Session model + storage preflight + immutable import

## Amaç

Bir source audio'nun processing başlamadan güvenli şekilde session'a alınması.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- docs/MEDIA_CONTRACT.md
- docs/BEHAVIOR_CONTRACT.md
- docs/SCOPE.md

Goal:
Implement the RecorAndro session model, conservative storage preflight, and immutable audio import.

Do not implement normalization or segmentation yet.

Canonical v0.1 input:
- exactly 1 audio
- optional 0..N photos

This step implements AUDIO-FIRST session creation.
Photo processing comes later.

SESSION REQUIREMENTS

Create a unique session identifier.

Use a local session layout concept such as:

<data_root>/
  sessions/
    <session_id>/
      session.json
      originals/
        audio/
      generated/
      temp/

SESSION METADATA

Store at least:
- schema_version
- session_id
- created_at
- profile
- title/course if supplied
- source audio original filename
- source audio size
- imported audio filename
- imported audio SHA-256
- current state
- errors/warnings
- storage preflight result
- visual_count default 0

STORAGE PREFLIGHT

Before copying the original audio:
1. determine source file size
2. determine currently available space on the target filesystem
3. estimate required peak working space conservatively

Account for when relevant:
- immutable original imported copy
- possible normalized output
- generated part audio
- package ZIP duplication
- optional full archive capability
- temporary files
- safety headroom

Use docs/MEDIA_CONTRACT.md to estimate generated audio sizes where possible.

Record:
- source bytes
- estimated required bytes
- free bytes
- headroom policy
- decision
- assumptions

The formula must be simple, documented, conservative and testable.

Full Archive default is not yet frozen.
Preflight must support archive requested/not requested and a profile-controlled decision resolved before processing.

If free space is insufficient:
- fail BEFORE importing original
- do not create a fake successful session
- provide a clear required/free-space message

IMPORT

If preflight passes:
1. create session safely
2. copy source audio into session originals/audio
3. never modify source file
4. hash source/import in a streaming manner
5. verify imported size/hash
6. only then publish imported original as valid
7. partial file remains temporary/not canonical
8. session clearly records failure if needed
9. later processing uses the managed imported original, not the external Android path

FILENAME/PATH SAFETY

- sanitize leaf filenames
- preserve original filename in metadata
- support Turkish/Unicode
- handle long names
- prevent path traversal
- keep managed paths under data root

ATOMICITY

Use temporary import + verification + atomic rename/publication.

CLI

Add a temporary technical CLI such as:

recorandro import-audio <path> --profile lecture

This is not final UX.

Testing:
- normal import
- insufficient storage
- zero-byte audio
- Turkish filename
- emoji filename
- long filename
- path traversal style filename
- interrupted copy simulation
- hash mismatch simulation
- original source unchanged
- imported hash matches
- no photos / visual_count 0

Before edits:
- propose the storage preflight formula
- explain safety margin
- list planned files

After edits:
- run tests
- show one example session.json
- show one insufficient-storage example
- confirm processing source is the managed immutable copy
- stop before ffprobe
```

## Codex'in üretmesi gerekenler

- session model
- storage preflight
- immutable import
- hash verification
- atomic temp/publish
- tests
- technical import CLI

## Şimdi senin yapman gereken

Gerçek Redmi üzerinde önce küçük audio, sonra mümkünse gerçek 45–70 MB / 1–1.5 saat lecture audio ile import testi yap.

Kontrol:
1. Source dosya aynı.
2. Managed original oluştu.
3. Hash PASS.
4. `visual_count = 0`.
5. Preflight sonucu kaydedildi.
6. External source sonradan taşınsa bile managed original bağımsız.

## Test prosedürü

```text
source audio
↓
storage preflight
↓
import
↓
hash
↓
managed original
```

0-photo normal kabul edilmeli.

## Başarı kriterleri

- [ ] Preflight importtan önce.
- [ ] Yetersiz alan import başlatmıyor.
- [ ] Original source değişmiyor.
- [ ] Managed copy byte-identical.
- [ ] SHA-256 doğru.
- [ ] Session state doğru.
- [ ] Unicode isimler sorun yaratmıyor.
- [ ] Core 0-photo session ile tam.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only RecorAndro session import/storage-preflight behavior.

Problem:
[PASTE FAILURE]

Do not implement ffprobe, normalization, segmentation, visuals or UI.

Preserve:
- preflight before import
- original source immutable
- managed copy verified by size/hash
- partial files never canonical
- managed paths remain inside data root
- zero-photo session is normal

Reproduce, add a regression test, and make the smallest fix.
```

## Sonraki adıma geçiş koşulu

Gerçek lecture audio güvenli şekilde managed session'a alınabilmeli.

---

# FAZ 2 — Android local audio core

# Adım 2.1 — ffprobe media inspection

## Amaç

Managed original audio'nun teknik özelliklerini güvenilir biçimde çıkarmak.

## Neden

Normalization ve segmentation kararları guessed metadata ile değil gerçek media inspection ile çalışmalıdır.

## Ön koşullar

- Session/import stabil.
- Managed original hash doğrulanmış.
- ffprobe mevcut.

## Model / Efor

**GPT-6 Sol — Medium**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- docs/MEDIA_CONTRACT.md
- docs/RECORA_MEDIA_PARITY.md
- current session/import implementation

Goal:
Implement ffprobe-based inspection of the managed immutable original audio.

Do not implement normalization or segmentation yet.

Requirements:

1. Probe ONLY the managed imported original inside the session.
2. Never rely on the external source path after import.
3. Use ffprobe with:
   - argument arrays
   - shell=False
   - bounded timeout
   - machine-readable JSON
4. Parse defensively.

Store where available:
- format/container
- duration_seconds
- human duration
- size_bytes
- selected audio stream index
- codec
- sample_rate
- channels
- channel_layout
- bitrate
- stream count
- creation_time metadata as informational only if present
- probe status
- warnings

Use docs/RECORA_MEDIA_PARITY.md to mirror Recora's relevant media-stream/duration behavior where appropriate.

Do not promote unreliable creation_time into lecture/session timing.

Validate:
- file is non-empty
- audio stream exists
- duration is finite/sane
- probed file still matches expected managed-original size/hash before or after probe as appropriate

Failure:
- original stays safe
- session becomes clear failed/probe_failed state
- actionable error
- retry remains possible later

Add CLI/status output suitable for technical testing.

Testing:
- valid M4A
- valid supported secondary format from MEDIA_CONTRACT
- malformed media
- file with no audio stream if practical
- missing ffprobe
- timeout/failure
- original hash unchanged

Before edits:
- inspect the media contract
- state exactly which Recora probe semantics are being preserved

After edits:
- run tests
- show one real/fixture probe result
- stop before normalization
```

## Codex'in üretmesi gerekenler

Session içinde probe metadata ve teknik test CLI/status çıktısı.

## Şimdi senin yapman gereken

Gerçek lecture audio session'ında probe çalıştır.

Telefon recorder'ın gösterdiği süre ile ffprobe süresini karşılaştır.

Kontrol:
- duration doğru mu?
- codec doğru mu?
- sample rate doğru mu?
- channels doğru mu?
- size doğru mu?
- original hash aynı mı?

## Test prosedürü

Gerçek 45–70 MB audio üzerinde probe.

## Başarı kriterleri

- [ ] Probe gerçek Android'de çalışıyor.
- [ ] Duration doğru.
- [ ] Audio stream doğru.
- [ ] Unsupported/malformed media kontrollü fail.
- [ ] Original değişmedi.
- [ ] External path bağımlılığı yok.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only RecorAndro's ffprobe media-inspection layer.

Problem:
[PASTE ERROR OR WRONG FIELD]

Use the managed imported original only.

Do not implement normalization or segmentation.

Preserve the media contract and Recora behavioral parity where relevant.
Add a regression test and make the smallest parsing/execution fix.
```

## Sonraki adıma geçiş koşulu

Gerçek lecture audio doğru teknik metadata ile probe edilebilmeli.

---

# Adım 2.2 — Normalization Auto / Force / Off

## Amaç

Recora'dan doğrulanmış normalization davranışını Android-local ortamda aynı semantics ile uygulamak.

## Ön koşullar

- Probe stabil.
- `MEDIA_CONTRACT.md`
- `BEHAVIOR_CONTRACT.md`
- `RECORA_MEDIA_PARITY.md`

hazır.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read and treat as authoritative:
- docs/MEDIA_CONTRACT.md
- docs/BEHAVIOR_CONTRACT.md
- docs/RECORA_MEDIA_PARITY.md

Goal:
Implement RecorAndro normalization with Auto / Force / Off semantics.

Do NOT redesign the thresholds.
Use the frozen exact values from the contracts.

Core invariants:
- original source file is never modified
- managed original is never modified
- normalized output is derived
- no silence removal
- no speed change
- no time-stretch
- no aggressive denoise
- no EQ unless the frozen contract explicitly requires it
- no arbitrary compressor chain
- source/global timeline duration must remain equivalent within the frozen tolerance

AUTO

Implement exactly the frozen decision behavior:
- measure using the agreed FFmpeg method
- if normalization is not justified, skip without unnecessary re-encoding
- record exact reason
- if required, generate normalized output with frozen codec/container/sample-rate/channel policy

FORCE

Implement the frozen Force semantics:
- user intentionally requests normalization
- still obey safety/peak constraints
- never overwrite original
- record that the decision source was "force"

OFF

- no normalization
- record explicit skip reason "off"
- downstream segmentation source must follow the frozen behavior contract

OUTPUT

Use the exact normalized-output media contract:
- container
- codec
- bitrate/quality
- sample rate
- channels

INTEGRITY

Before processing:
- verify managed original identity/size/hash as required

Generate to temporary path.
After FFmpeg:
- verify process return code
- probe generated output
- verify duration tolerance
- verify output audio stream
- hash/size output
- atomically publish

If any verification fails:
- do not publish bad normalized output
- original remains safe
- session marks failure clearly

STATE/METADATA

Record:
- requested mode: auto/force/off
- decision
- reason
- measurement values
- exact frozen processing parameters
- input artifact
- output artifact if any
- input/output duration
- size/hash
- processing time
- return status

TESTING

Port/recreate the relevant Recora semantic fixtures:
- source level acceptable -> Auto skip
- low source -> Auto apply
- Force
- Off
- very loud source
- peak-constrained source
- malformed FFmpeg output/failure
- duration mismatch
- original hash unchanged

Do not implement segmentation yet.

Before edits:
- restate the exact frozen normalization constants from docs
- explain any unavoidable Android/FFmpeg-version difference before coding

After edits:
- run tests
- show Auto skip example
- show Auto applied example
- show Force/Off examples
- report whether semantic behavior matches Recora
- stop before segmentation
```

## Codex'in üretmesi gerekenler

- normalization engine
- decision metadata
- verified normalized artifact
- tests

## Şimdi senin yapman gereken

Gerçek lecture kaydında:

```text
Normalization = Auto
```

çalıştır.

Auto skip diyorsa:
- derived normalized audio gereksiz yere oluşmamış mı?
- reason açık mı?

Applied diyorsa original ile normalized audio'nun:
- başlangıç
- orta
- son

bölümlerini kısa şekilde dinle.

Kontrol:
- speech bozulmuş mu?
- clipping var mı?
- noise gereksiz büyümüş mü?
- süre aynı mı?

Ayrıca küçük bir test audio ile `Force` ve `Off` modlarını doğrula.

## Test prosedürü

Gerçek lecture + küçük fixture.

## Başarı kriterleri

- [ ] Auto exact contract'a göre karar veriyor.
- [ ] Force çalışıyor.
- [ ] Off çalışıyor.
- [ ] Gereksiz normalization yok.
- [ ] Derived output contract doğru.
- [ ] Original değişmiyor.
- [ ] Timeline korunuyor.
- [ ] Android FFmpeg çıktısı playable.
- [ ] Recora behavioral parity korunuyor.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only RecorAndro normalization.

Problem:
[PASTE FAILURE]

Do not change the frozen thresholds or media contract unless the implementation proves the contract impossible on the real Android FFmpeg environment.

Compare against:
- docs/MEDIA_CONTRACT.md
- docs/BEHAVIOR_CONTRACT.md
- docs/RECORA_MEDIA_PARITY.md

Preserve:
- original immutability
- duration/timeline
- conservative processing
- Auto/Force/Off semantics

Reproduce, add a regression test, and make the smallest fix.
```

## Sonraki adıma geçiş koşulu

Normalization gerçek Redmi üzerinde güvenilir olmalı.

---

# Adım 2.3 — Segmentation planner + tiny-part avoidance

## Amaç

Audio'yu önce kesmeden deterministik bir segmentation planı oluşturmak.

## Neden

Planlama ile export'u ayırmak:
- davranışı test etmeyi,
- tiny-tail logic doğrulamayı,
- FFmpeg export bug'ını algoritma bug'ından ayırmayı

kolaylaştırır.

## Ön koşullar

- Frozen segmentation contract.
- Probe stabil.
- Normalization semantics stabil.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- docs/BEHAVIOR_CONTRACT.md
- docs/MEDIA_CONTRACT.md
- docs/RECORA_MEDIA_PARITY.md

Goal:
Implement the segmentation DECISION and PLANNING layer only.

Do not export/cut part audio yet.

INPUT SOURCE

Choose the segmentation-analysis source according to the frozen behavior contract:
- normalized output when applicable
- otherwise the correct canonical non-normalized source

GLOBAL TIMELINE

All boundaries must remain source/global timeline-relative.
Normalization must not redefine timeline zero.

MODES

AUTO
- short enough => single-part plan
- long enough => segmentation plan
- use exact frozen Auto threshold

FORCE
- create a segmentation plan even when Auto would keep a single part
- still obey useful-part/tiny-part invariants

OFF
- produce a single-part/no-segmentation plan according to the contract

SILENCE/QUIET DETECTION

Use the exact frozen:
- target duration
- search window
- quiet threshold
- minimum quiet duration
- candidate ranking
- deterministic fallback

Do not remove silence.

TINY FIRST/LAST PART AVOIDANCE

Implement exactly the deterministic policy from docs/BEHAVIOR_CONTRACT.md.

Key invariant:

"Segmentation may deviate from the nominal target duration to avoid nonsensical tiny first or last parts."

The planner should prefer:
1. complete source coverage
2. no gaps
3. useful part structure
4. natural quiet boundaries
5. nominal target proximity

Do not create meaningless ~1–3 minute residual parts when a deterministic redistribution/alternate boundary satisfying the contract exists.

SOURCE-END

The final nominal part must reach the actual source duration.

PLAN OUTPUT

Create structured planning metadata containing:
- source artifact/revision
- mode
- source duration
- single vs segmented
- target
- search window
- detected quiet regions or summary
- chosen boundaries
- reason for each boundary
- tiny-part avoidance adjustments
- nominal part ranges
- expected part count
- source-end coverage
- silence_removed=false

Do not include overlap-expanded export ranges yet unless clearly separated from nominal boundaries.

TEST MATRIX

Use deterministic synthetic/fixture tests around:
- 5 min
- just below Auto threshold
- exactly threshold
- just above threshold
- 25–30 min
- 49–55 min
- 51–53 min tiny-tail risk
- 61 min
- 74–80 min
- 90 min
- no suitable silence
- many quiet candidates
- quiet region near boundary
- very short source

Where suitable, compare against Recora's segmentation semantics, but RecorAndro's frozen tiny-part rule may be an intentional behavioral improvement.

Before edits:
- restate the exact frozen segmentation constants
- restate the exact tiny-part policy
- describe expected part-count examples

After edits:
- run tests
- show planning results for representative durations
- explicitly identify any intentional divergence from Recora
- stop before audio export
```

## Codex'in üretmesi gerekenler

- segmentation planner
- deterministic plan metadata
- Auto/Force/Off behavior
- tiny-part avoidance
- tests

## Şimdi senin yapman gereken

Önce automated duration-matrix sonuçlarını kontrol et.

Sonra gerçek 61 dk civarı lecture için yalnız **plan** üret.

Planı oku:

```text
Part 1 nominal
Part 2 nominal
Part 3 nominal
Boundary reasons
Tiny-part adjustment
```

Önerilen split noktalarının audio üzerinde çevresini dinlemek faydalı.

## Test prosedürü

Gerçek 61 dk lecture + duration matrix.

## Başarı kriterleri

- [ ] Auto threshold doğru.
- [ ] Force doğru.
- [ ] Off doğru.
- [ ] Silence silinmiyor.
- [ ] Boundary selection deterministik.
- [ ] Source-end coverage var.
- [ ] Tiny first/last avoidance çalışıyor.
- [ ] Gereksiz 1–3 dk residual part üretilmiyor.
- [ ] 61/90 dk mantıklı plan.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only the RecorAndro segmentation planner.

Failing case:
[PASTE DURATION / PLAN / EXPECTED]

Do not export audio yet.
Do not change normalization.

Compare behavior against the frozen segmentation contract.

Preserve priority:
1. full source coverage
2. no gaps
3. useful non-tiny parts
4. natural quiet boundaries
5. nominal target proximity

Fix the deterministic planner, add a regression test, and report the new plan.
```

## Sonraki adıma geçiş koşulu

Planner duration matrix ve gerçek lecture üzerinde mantıklı olmalı.

---

# Adım 2.4 — Audio part export + overlap + integrity

## Amaç

Frozen planı gerçek ChatGPT-ready audio part'larına dönüştürmek.

## Ön koşullar

- Planner stabil.
- Media output contract frozen.
- FFmpeg Android'de stabil.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- docs/MEDIA_CONTRACT.md
- docs/BEHAVIOR_CONTRACT.md
- current segmentation plan implementation

Goal:
Export actual audio parts from the approved segmentation plan.

Do not implement ZIP packaging or final manifests yet.

SOURCE

Use the correct canonical processing source from the session:
- normalized derived audio when the frozen decision requires it
- otherwise the frozen canonical source

Never modify original media.

PART MEDIA CONTRACT

Use exactly the frozen:
- container
- codec
- bitrate/quality
- sample-rate policy
- channel policy
- encode/stream-copy policy

Do not optimize differently just because Android is the host.

TIMELINE

Nominal segmentation boundaries remain global/source-relative.

Apply the frozen overlap semantics to exported part ranges.

Requirements:
- no negative start
- no end beyond source duration
- no unintended gap
- configured overlap between adjacent exported parts
- first part covers source start
- final part reaches exact source end
- global start/end metadata retained
- local part duration recorded

Use deterministic filenames:
part_01.<ext>
part_02.<ext>
...

ATOMICITY

For each part:
1. write temporary output
2. verify FFmpeg success
3. ffprobe output
4. verify expected duration within frozen tolerance
5. verify playable audio stream
6. calculate size/hash
7. atomically publish final part

Do not publish partial/bad output.

INTEGRITY

Before export:
- verify source artifact identity/revision where applicable

After all exports:
- prove source timeline coverage from start to end
- prove no unintended gap
- prove overlap behavior
- prove final end coverage

SESSION METADATA

Record:
- part index
- global_start_seconds
- global_end_seconds
- nominal boundary relation
- duration
- overlap_before
- overlap_after
- filename
- size
- SHA-256
- source artifact
- export status

TESTS
- single-part
- multi-part
- first boundary
- last boundary
- overlap
- source-end
- tiny-tail-adjusted plan
- FFmpeg export failure
- invalid output
- duration mismatch
- original unchanged

Use Recora media behavior for semantic parity where applicable.

Before edits:
- restate the final part output codec/container and encode policy
- explain the overlap convention

After edits:
- run tests
- show one multi-part example
- prove no-gap/source-end checks
- stop before manifests/packages
```

## Codex'in üretmesi gerekenler

```text
generated/parts/
├── part_01.*
├── part_02.*
└── part_03.*
```

ve part integrity metadata.

## Şimdi senin yapman gereken

Gerçek lecture audio'yu baştan sona işle.

Kontrol:
1. Part count planla aynı mı?
2. Her part'ın ilk/son 10–15 saniyesini dinle.
3. Adjacent part overlap'ını doğrula.
4. Son part gerçek kaydın sonuna ulaşıyor mu?
5. Beklenmedik kalite kaybı var mı?
6. File size/media contract mantıklı mı?

## Test prosedürü

Gerçek 45–70 MB / 1–1.5 saat lecture.

## Başarı kriterleri

- [ ] Part dosyaları playable.
- [ ] Codec/container contract doğru.
- [ ] Part count planla aynı.
- [ ] Overlap doğru.
- [ ] Gap yok.
- [ ] Source start/end tam.
- [ ] Tiny residual part yok.
- [ ] Original değişmedi.
- [ ] Generated hashes kayıtlı.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only RecorAndro audio-part export.

Problem:
[PASTE FAILURE]

Do not redesign segmentation planning unless the exported ranges prove the planner metadata itself is wrong.

Verify:
- frozen codec/container
- encode/stream-copy policy
- FFmpeg seek/cut arguments
- overlap arithmetic
- source-end clamping
- duration verification
- atomic publication

Preserve:
- original immutability
- no gaps
- full source coverage
- deterministic overlap

Add a regression test and make the smallest fix.
```

## Sonraki adıma geçiş koşulu

Gerçek lecture Android üzerinde güvenilir audio part'larına dönüşebilmeli.

---

# Adım 2.5 — Recora vs RecorAndro behavioral parity acceptance

## Amaç

PART 1 sonunda Android audio core'un gerçekten Recora reference davranışından kopmadığını doğrulamak.

## Neden

Aynı FFmpeg/Python araçlarını kullanmak parity kanıtı değildir. Karşılaştırılması gereken davranıştır.

## Ön koşullar

- RecorAndro audio core tamam.
- Recora reference erişilebilir.
- En az bir ortak test audio mevcut.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Perform a MEDIA-BEHAVIOR parity review between frozen Recora and current RecorAndro.

Do not modify Recora.

Do not compare architecture, server behavior, filesystem layout, state machines, UI, or deployment.

Parity scope is ONLY:
- probe/media semantics
- normalization decision
- normalization safety invariants
- segmentation decision
- segment count
- boundary-selection semantics
- overlap semantics
- source timeline preservation
- source-end coverage
- part media contract
- media integrity behavior

Use the same representative input files/fixtures where practical.

Create:

docs/PART1_PARITY_REPORT.md

For each fixture record:
- input identity/hash
- duration
- Recora probe result summary
- RecorAndro probe result summary
- Recora normalization decision
- RecorAndro normalization decision
- normalization parameter parity
- Recora segment count
- RecorAndro segment count
- boundaries
- overlap
- source-end
- output codec/container behavior
- expected intentional divergence

Important:

RecorAndro has one intentional possible improvement:
- frozen tiny-first/last-part avoidance behavior

If this produces a different but intentional segmentation result, label it:
"intentional behavioral divergence"

Do not call it a parity failure if it matches the frozen RecorAndro contract.

Byte-identical output is NOT required.
Semantic media parity is required.

Suggested fixtures:
- short
- ~61 min
- ~90 min
- low-level source
- already acceptable loudness
- no suitable silence
- tiny-tail-risk duration

At the end classify:
PASS
PASS WITH INTENTIONAL DIVERGENCE
FAIL

If FAIL:
- identify the exact media behavior mismatch
- do not auto-fix it in this step

Also run the current RecorAndro automated test suite.

Stop after the report.
```

## Codex'in üretmesi gerekenler

```text
docs/PART1_PARITY_REPORT.md
```

ve full test sonucu.

## Şimdi senin yapman gereken

Parity report'u incele.

Özellikle:
- normalization decision
- part count
- boundaries
- overlap
- source end
- output format

karşılaştırmalarına bak.

`intentional behavioral divergence` yalnız daha önce freeze ettiğimiz tiny-part davranışı veya açıkça belgelenmiş media contract divergence için kabul edilmeli.

Bilinmeyen yeni divergence görürsen PART 2'ye geçme.

## Test prosedürü

En az bir gerçek lecture ve representative fixture set.

## Başarı kriterleri

- [ ] Probe semantics uyumlu.
- [ ] Normalization semantics uyumlu.
- [ ] Segmentation semantics uyumlu.
- [ ] Media format contract'a uygun.
- [ ] No-gap/source-end invariants PASS.
- [ ] Bilinmeyen divergence yok.
- [ ] RecorAndro tests PASS.
- [ ] Gerçek Android lecture audio başarıyla işleniyor.

## Sorun çıkarsa — düzeltme promptu

```text
RecorAndro PART 1 media parity found one unexpected mismatch:

[PASTE MISMATCH]

Do not change Recora.

Determine whether:
A) RecorAndro implementation violates the frozen contract, or
B) the frozen contract incorrectly captured actual Recora behavior.

If A:
fix RecorAndro only and add a regression test.

If B:
stop before changing code and report the contract discrepancy for review.

Do not broaden scope beyond media-processing behavior.
```

## Sonraki adıma geçiş koşulu

Parity classification `PASS` veya yalnız belgelenmiş intentional divergence ile `PASS WITH INTENTIONAL DIVERGENCE` olmalı.

---

# PART 1 — Final Acceptance Gate

PART 2'ye geçmeden önce aşağıdakiler tamam olmalıdır.

## Device baseline

- [ ] Final Android/MIUI baseline kaydedilmiş.
- [ ] Root durumu kaydedilmiş.
- [ ] Root media core requirement değil.
- [ ] Termux/Python/FFmpeg/ffprobe gerçek versiyonları kaydedilmiş.

## Behavioral contract

- [ ] Recora actual implementation incelenmiş.
- [ ] Normalization exact values gerçek code/tests üzerinden çıkarılmış.
- [ ] Segmentation exact values gerçek code/tests üzerinden çıkarılmış.
- [ ] Input format policy frozen.
- [ ] Normalized output format frozen.
- [ ] Part output codec/container frozen.
- [ ] Sample-rate policy frozen.
- [ ] Channel policy frozen.
- [ ] Encode/stream-copy policy frozen.
- [ ] Auto / Force / Off normalization frozen.
- [ ] Auto / Force / Off segmentation frozen.
- [ ] Tiny first/last avoidance frozen.
- [ ] Full Archive Lecture default gerçek-device measurement sonrası karar verilmek üzere açık.

## Session/import

- [ ] Storage preflight importtan önce.
- [ ] Conservative peak-space estimate var.
- [ ] Yetersiz alan import başlatmıyor.
- [ ] Original source değişmiyor.
- [ ] Managed original hash doğrulanıyor.
- [ ] Processing external URI/path'e bağımlı değil.
- [ ] 0-photo session normal.

## Probe

- [ ] ffprobe gerçek cihazda.
- [ ] Duration/codec/sample-rate/channel doğru.
- [ ] Malformed media güvenli fail.
- [ ] Original integrity korunuyor.

## Normalization

- [ ] Auto çalışıyor.
- [ ] Force çalışıyor.
- [ ] Off çalışıyor.
- [ ] Gereksiz encode yok.
- [ ] Timeline korunuyor.
- [ ] Media output contract korunuyor.

## Segmentation

- [ ] Auto threshold doğru.
- [ ] Force doğru.
- [ ] Off doğru.
- [ ] Silence-aware planner doğru.
- [ ] Deterministic fallback doğru.
- [ ] Tiny first/last avoidance doğru.
- [ ] Overlap doğru.
- [ ] Gap yok.
- [ ] Source-end coverage var.

## Gerçek cihaz — primary acceptance

Primary acceptance fixture:

```text
1 real lecture audio
0 photos
45–70 MB
~1–1.5 hours
```

şu zinciri tamamlamalı:

```text
storage preflight
↓
immutable import
↓
ffprobe
↓
normalization decision
↓
normalize or skip
↓
segmentation plan
↓
part export
↓
verified Android-local audio parts
```

- [ ] Fotoğraf gerekmedi.
- [ ] Visual warning çıkmadı.
- [ ] PC gerekmedi.
- [ ] Server gerekmedi.
- [ ] Cloudflare gerekmedi.

## Recora parity

- [ ] `PART1_PARITY_REPORT.md` mevcut.
- [ ] Unknown media divergence yok.
- [ ] Intentional divergence yalnız frozen RecorAndro contract içinde.
- [ ] Byte-identical output beklenmiyor.
- [ ] Behavioral/invariant parity sağlanıyor.

---

# PART 1 tamamlandığında frozen kabul edilecekler

PART 2 artık şunları yeniden tasarlamamalıdır:

```text
RecorAndro media input contract
normalization semantics
normalization output contract
segmentation semantics
tiny-part policy
part media format
overlap
global/source timeline
source-end coverage
immutable original model
storage preflight ordering
audio-first / zero-photo behavior
```

PART 2 şu konuların üzerine kurulacaktır:

```text
filesystem/session state
atomic publication
resume/retry
manifest/report
package ZIP
full archive capability
optional visuals
audio-only end-to-end packaging acceptance
```

---

# PART 1 geliştirme sırası

```text
0.1 Device baseline
↓
0.2 Recora media parity extraction
↓
0.3 Behavior + media contract freeze
↓
1.1 Termux/Python/FFmpeg scaffold
↓
1.2 Storage preflight + immutable import
↓
2.1 ffprobe
↓
2.2 Normalization
↓
2.3 Segmentation planner
↓
2.4 Part export
↓
2.5 Recora behavioral parity acceptance
```

Toplam:

**10 orta büyüklükte geliştirme / verification adımı.**

Her adımın acceptance kriterleri geçmeden sonraki kritik media adımına geçme.

---

# PART 1 sonunda beklenen teknik kullanım

Bu aşamada kullanıcı deneyimi henüz final değildir.

Teknik kullanım kabaca:

```text
Termux
↓
RecorAndro CLI
↓
audio import
↓
process
↓
generated parts
```

Final günlük UX daha sonraki bölümde:

```text
Audio seç
Optional photos
PROCESS
Share Part
```

seviyesine indirilecektir.

---

**Dosya sonu — RecorAndro v0.1 SETUP PART 1 / 3**


# RecorAndro v0.1 — Teknik Kurulum ve Codex Geliştirme Planı
## PART 2 / 3 — Faz 3–5
### Session state & recovery → Manifest/report → Part ZIP & archive capability → Optional visual attachments → Audio-only packaging acceptance

**Proje:** RecorAndro  
**Hedef sürüm:** v0.1  
**Bu dosya:** PART 2 / 3  
**Kapsam:** Faz 3, Faz 4, Faz 5  
**Önceki dosya:** `RECORANDRO_V0.1_SETUP_PART1.md`  
**Sonraki dosya:** `RECORANDRO_V0.1_SETUP_PART3.md`

---

# 0. Bu bölümün amacı

PART 1 sonunda RecorAndro audio core şu davranışları sağlamış olmalıdır:

- Android-local / Termux execution
- immutable managed original
- storage preflight
- ffprobe media inspection
- Auto / Force / Off normalization
- Auto / Force / Off segmentation
- deterministic tiny first/last part avoidance
- audio part export
- overlap
- no-gap
- source-end coverage
- Recora behavioral media parity

PART 2'nin amacı bu çekirdeği **günlük kullanımda güvenilir bir session sistemi** haline getirmek ve ChatGPT'ye verilecek deterministik paketleri hazırlamaktır.

Bu bölüm tamamlandığında RecorAndro:

- session state'ini kalıcı tutar,
- process kill / hata sonrası hangi noktada kaldığını bilir,
- aynı session'ın aynı anda iki kez işlenmesini engeller,
- geçici çıktıları final olarak göstermeden önce doğrular,
- lecture-level ve part-level manifest üretir,
- insan okunabilir processing report üretir,
- audio part ZIP'leri üretir,
- full archive capability sağlar ancak Lecture default'unu henüz zorunlu olarak ON yapmaz,
- fotoğrafları yalnız opsiyonel attachment olarak korur/indexler,
- 0-photo session'ı visual warning/prompt olmadan tamamlar.

---

# 1. PART 2 boyunca korunacak kontratlar

PART 1'de freeze edilen şu davranışlar yeniden tasarlanmayacaktır:

```text
media input contract
normalization semantics
normalization output contract
segmentation semantics
tiny-part policy
part media format
overlap
source/global timeline
source-end coverage
immutable original model
storage preflight ordering
audio-first behavior
zero-photo first-class behavior
```

PART 2 bu davranışların üzerine metadata, recovery ve packaging ekler.

---

# 2. PART 2 ana tasarım ilkeleri

## 2.1 Audio pipeline dominant kalır

Visual subsystem:

```text
optional enrichment
```

olarak kalır.

Fotoğraf:
- probe'u bloklamaz,
- normalization'ı bloklamaz,
- segmentation'ı bloklamaz,
- part export'u bloklamaz,
- manifest/report üretimini bloklamaz,
- part ZIP üretimini bloklamaz.

Bir görsel metadata hatası bütün session'ı fail ettirmez.

## 2.2 State machine küçük tutulur

Amaç distributed queue veya workflow engine kurmak değildir.

Local JSON/state yeterlidir.

## 2.3 Derived artifacts disposable olabilir, originals olamaz

Protected:

```text
managed original audio
managed original photos
canonical session metadata
final manifests
```

Regenerable:

```text
normalized audio
parts
ZIPs
reports
full archive
```

Bu ayrım recovery ve ileride cleanup için temel olacaktır.

## 2.4 Full Archive capability ≠ default ON

Full Archive:
- desteklenir,
- profile-controlled olur,
- gerçek Redmi storage/performance ölçümünden sonra Lecture default freeze edilir.

---

# FAZ 3 — Session state, artifact registry ve recovery

# Adım 3.1 — Session state model + artifact registry

## Amaç

Bir session'ın hangi aşamada olduğunu ve hangi artifact'ların gerçekten geçerli olduğunu kalıcı ve deterministik biçimde kaydetmek.

## Neden

Android/MIUI:
- process öldürebilir,
- Termux kapanabilir,
- pil/thermal koşulu nedeniyle işlem yarıda kalabilir,
- kullanıcı yanlışlıkla komutu ikinci kez çalıştırabilir.

Bu durumda session'ın "ne oldu?" sorusuna açık cevap verebilmesi gerekir.

## Ön koşullar

- PART 1 PASS.
- Session import/probe/normalization/segmentation/parts mevcut.
- PART 1 frozen contract'lar değişmiyor.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- docs/SCOPE.md
- docs/MEDIA_CONTRACT.md
- docs/BEHAVIOR_CONTRACT.md
- current session/import/audio pipeline implementation
- PART 1 parity report if present

Goal:
Implement a small persistent session-state model and artifact registry.

Do NOT introduce:
- database
- Redis
- queue service
- server
- background daemon architecture
- Android service/native shell

Keep this local-filesystem and JSON based.

STATE MODEL

Define a finite state model such as:

created
imported
probed
normalization_decided
normalized_or_skipped
segmentation_planned
segments_exported
manifested
packaged
archived_or_skipped
complete
failed

You may refine names to fit existing implementation, but keep them:
- explicit
- finite
- understandable
- versioned

Visual processing must NOT become a mandatory core state transition.

If visuals exist, represent them as optional attachment status/metadata such as:
- not_present
- pending
- indexed
- partial_warning
- failed_nonblocking

Do not make visual failure invalidate a successful audio pipeline.

SESSION METADATA

Expand session.json to record:

- schema_version
- session_id
- created_at / updated_at
- current_state
- last_successful_state
- failed_stage when applicable
- error_code
- error_message
- retryable flag
- profile
- original audio identity
- optional visual_count
- selected normalization mode
- normalization decision/result
- selected segmentation mode
- segmentation plan identity/version
- artifact registry
- package/archive status

ARTIFACT REGISTRY

Create a structured registry for canonical artifacts.

Each artifact should have, where relevant:
- artifact_id
- type
- relative path
- status
- source artifact id
- size
- SHA-256
- media metadata summary
- created_at
- verified_at
- regenerable/protected classification

Protected artifacts:
- managed original audio
- managed original photos when implemented later
- canonical session metadata

Regenerable artifacts:
- normalized audio
- parts
- reports
- ZIP packages
- full archive

Do not treat a path alone as proof that an artifact is valid.

STATE WRITES

Use safe atomic session metadata writes:
- write temp
- fsync if practical/appropriate
- atomic replace

A partially written session JSON must not replace the last valid canonical state.

INVARIANTS

- original audio identity cannot silently change after import
- session_id is immutable
- current state cannot claim a stage succeeded when required artifacts are unverified
- visual_count=0 is normal
- absence of visual subsystem data is not a warning
- derived artifact failure must not delete protected artifacts

CLI / TECHNICAL STATUS

Add a technical command such as:
recorandro status <session_id>

Show:
- current state
- last successful state
- audio summary
- normalization result
- segmentation result
- part count
- artifact status
- errors/warnings

Do not add final user UI.

TESTING

Add tests for:
- normal state progression
- invalid state transition
- atomic metadata update
- simulated partial/corrupt temp metadata
- original artifact identity invariant
- regenerable artifact registration
- visual_count=0
- visual status absent without warning
- session reload round-trip

Before edits:
- propose the exact state list
- propose artifact classes
- explain protected vs regenerable classification
- list planned files

After edits:
- run tests
- show one example session.json
- show one technical status output
- stop before recovery/retry implementation
```

## Codex'in üretmesi gerekenler

- session state model
- artifact registry
- atomic metadata writes
- technical status command
- tests

## Şimdi senin yapman gereken

Gerçek PART 1 test session'ını yeni modelle aç.

Kontrol:

```text
original
normalization
segmentation
parts
```

artifact olarak doğru kayıtlı mı?

`status` çıktısında:

- current state
- last successful state
- part count
- visual_count = 0

anlaşılır mı?

## Test prosedürü

Mevcut gerçek session reload.

Ayrıca test session'ında metadata temp/corrupt senaryosu automated test ile doğrulansın.

## Başarı kriterleri

- [ ] State finite ve anlaşılır.
- [ ] Artifact validity path existence'a indirgenmemiş.
- [ ] Protected/regenerable ayrımı var.
- [ ] Atomic session write var.
- [ ] 0-photo state sessiz/normal.
- [ ] Visual subsystem core state'i bölmüyor.
- [ ] Original identity değiştirilemiyor.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only the RecorAndro session-state/artifact-registry layer.

Problem:
[PASTE FAILURE]

Do not modify the frozen media behavior.

Preserve:
- finite local state model
- JSON/filesystem architecture
- protected vs regenerable artifact distinction
- atomic session metadata writes
- zero-photo normal behavior
- visual status non-blocking

Add a regression test and make the smallest fix.
```

## Sonraki adıma geçiş koşulu

PART 1'den üretilmiş gerçek session doğru state/artifact modeliyle temsil edilebilmeli.

---

# Adım 3.2 — Recovery, resume, duplicate-run prevention ve atomic publication

## Amaç

Process kill veya stage failure sonrası bütün session'ı sıfırdan işlemeye gerek kalmadan güvenli şekilde devam etmek.

## Neden

Android'de process survival garanti değildir.

Recovery tasarımı:
- deterministic,
- küçük,
- local

olmalıdır.

## Ön koşullar

- Adım 3.1 tamam.
- Artifact registry mevcut.
- Session state atomic yazılıyor.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- current session-state implementation
- artifact registry
- media contracts
- existing normalization/segmentation/export code

Goal:
Implement safe local recovery and resume for RecorAndro.

Do NOT add:
- database
- external job queue
- daemon/server
- Android native background service yet

RECOVERY PRINCIPLE

Resume from the last VERIFIED artifact/stage.

Do not trust:
- filename existence alone
- partial files
- temporary files
- stale metadata claiming success without verified artifacts

STARTUP / SESSION OPEN

When opening an existing session:

1. load last valid session metadata
2. inspect any state left in an in-progress/transient stage
3. validate artifacts needed for the next step
4. classify session as:
   - resumable
   - complete
   - failed_retryable
   - failed_manual_attention
5. do not delete original media

RETRY

Provide technical commands such as:
- recorandro resume <session_id>
- recorandro retry <session_id> [stage]

Exact CLI may adapt to current architecture.

Rules:

- reuse verified previous artifacts
- regenerate only invalid/missing regenerable outputs
- never recopy original unless original import itself never completed
- never overwrite a verified protected original
- downstream derived artifacts whose source revision changed must be invalidated deterministically

DUPLICATE PROCESSING PREVENTION

Prevent two simultaneous processing runs for the same session.

Use a small local mechanism suitable for Termux/Android, such as:
- lock file with PID/process validation
- atomic exclusive lock
- another simple local lock primitive

Requirements:
- stale lock must be detectable/recoverable
- active lock blocks duplicate processing
- no permanent deadlock after process death

ATOMIC PUBLICATION

For all regenerable final artifacts:
- generate under temp/staging name/location
- verify
- atomically publish
- only then update artifact registry/state

This applies to:
- normalized audio
- part audio
- later manifests/reports
- later ZIP/archive outputs

A process death during generation must not leave a partial artifact looking final.

RECOVERY SCENARIOS

Test:
- kill/fail during normalization
- kill/fail during segmentation planning
- kill/fail during part export
- partial temp file
- missing regenerable artifact after metadata says previous stage finished
- corrupted regenerable artifact
- active duplicate process attempt
- stale lock
- complete session resume call
- original remains safe

Do not add visual-specific recovery complexity.
Visual failures will later be non-blocking.

Before edits:
- show the recovery decision algorithm
- show the locking strategy
- explain how stale locks are handled
- list planned files

After edits:
- run tests
- demonstrate one simulated interrupted session + resume
- demonstrate duplicate-run rejection
- stop before manifest/package implementation
```

## Codex'in üretmesi gerekenler

- resume/retry logic
- duplicate-run prevention
- stale lock recovery
- artifact validation before reuse
- atomic publication discipline
- tests

## Şimdi senin yapman gereken

Gerçek cihazda kontrollü bir recovery testi yap.

Önerilen:

1. Test session başlat.
2. Uzun bir derived operation sırasında Termux/process'i kontrollü kapat.
3. RecorAndro'yu tekrar aç.
4. `status`.
5. `resume`.
6. Daha önce doğrulanmış stage tekrar yapılıyor mu gözlemle.
7. Original hash kontrol et.

Bu testi gerçek tek kopya önemli lecture üzerinde ilk kez yapma; kopya/test session kullan.

## Test prosedürü

Gerçek cihaz + automated failure simulation.

## Başarı kriterleri

- [ ] Interrupted session tanınıyor.
- [ ] Partial final görünmüyor.
- [ ] Resume son verified stage'den ilerliyor.
- [ ] Duplicate run engelli.
- [ ] Stale lock recoverable.
- [ ] Original korunuyor.
- [ ] Derived corruption yalnız ilgili downstream'i invalidate ediyor.
- [ ] Visual subsystem recovery için zorunlu değil.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only RecorAndro recovery/resume/locking behavior.

Failure:
[PASTE EXACT SCENARIO]

Do not change media algorithms.

Preserve:
- resume from last verified artifact
- protected originals never regenerated/deleted
- partial temp output never canonical
- duplicate run prevention
- stale lock recovery
- minimal local architecture

Add a regression test for the exact interruption pattern and make the smallest fix.
```

## Sonraki adıma geçiş koşulu

Gerçek cihazdaki kontrollü interrupt/resume testi PASS olmalı.

---

# FAZ 4 — Manifest, report, package ve archive capability

# Adım 4.1 — Canonical manifest + human-readable processing report

## Amaç

Her RecorAndro session ve audio part'ın kendi kendini açıklayan deterministik metadata çıktısına sahip olması.

## Neden

ChatGPT'ye:
- audio part,
- global range,
- overlap,
- source identity

bilgisini açık şekilde vermek gerekir.

Ayrıca kullanıcı/debug için insan okunabilir rapor gereklidir.

## Ön koşullar

- Audio core PASS.
- Session/artifact model PASS.
- State/recovery PASS.

## Model / Efor

**GPT-6 Sol — Medium**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- media/behavior contracts
- session-state model
- artifact registry
- current part metadata

Goal:
Implement canonical deterministic manifests and a human-readable processing report.

Do not implement ZIP packaging yet.

MANIFEST VERSIONING

Define a simple manifest schema version.

Generate:

1. session/lecture-level manifest.json
2. session/lecture-level manifest.md
3. one part manifest.json per generated part
4. one part manifest.md per generated part
5. processing_report.md

Keep schemas small and explicit.

LECTURE/SESSION MANIFEST

Include where relevant:

- schema_version
- session_id
- profile
- created_at
- title/course if supplied
- original filename
- original size
- original SHA-256
- media probe summary:
  - container
  - codec
  - sample rate
  - channels
  - duration
- normalization:
  - requested mode
  - applied/skipped
  - reason
  - source artifact
  - normalized artifact if any
- segmentation:
  - requested mode
  - single/segmented
  - target/window summary
  - part count
  - overlap
  - source/global timeline semantics
  - tiny-part adjustment if any
- visual_count
- visual handling status:
  - none when zero photos
  - optional summary when photos are later present
- artifact summary
- completion status
- warnings/errors

IMPORTANT ZERO-PHOTO RULE

For visual_count=0:
- this is normal
- do not add "missing visuals" warning
- do not add visual-specific required fields
- do not imply degraded output

PART MANIFEST

Include:

- schema_version
- session_id
- part_index
- filename
- SHA-256
- size
- codec/container summary
- global_start_seconds
- global_end_seconds
- global_start_human
- global_end_human
- local duration
- overlap_before
- overlap_after
- source artifact identity
- source/global timeline note

Canonical semantics:
- GLOBAL = immutable lecture/source timeline
- LOCAL = current part timeline only
- overlap does not change global timeline ownership

PROCESSING REPORT

Generate concise human-readable Markdown.

Include:

- session summary
- input
- storage-preflight summary
- probe summary
- normalization decision
- segmentation decision
- part table
- integrity verification summary
- visual summary only when visuals exist
- warnings/errors

Do not include:
- transcript
- AI summary
- interpretation of lecture content

DETERMINISM

Given identical canonical session metadata/artifacts, generated manifest/report content should be stable aside from explicitly allowed generation timestamps.

TESTING

- audio-only session
- single-part
- multi-part
- normalization skipped/applied
- tiny-part adjustment
- failure/warning representation
- JSON/MD consistency
- zero-photo session has no missing-visual warning

Create:
docs/MANIFEST_SCHEMA.md

Before edits:
- propose the manifest schema
- explain which data is canonical vs derived display
- list files

After edits:
- run tests
- show a complete small audio-only manifest example
- show a processing report example
- stop before ZIP creation
```

## Codex'in üretmesi gerekenler

```text
manifests/
├── session_manifest.json
├── session_manifest.md
├── part_01.json
├── part_01.md
└── ...

reports/
└── processing_report.md
```

ve schema doc.

## Şimdi senin yapman gereken

Gerçek 0-photo lecture session manifest/report'unu oku.

Kontrol et:

- original filename/hash doğru mu?
- duration doğru mu?
- normalization decision doğru mu?
- part count/ranges doğru mu?
- overlap doğru mu?
- `visual_count: 0` normal görünüyor mu?
- "missing photo" tarzı gereksiz warning var mı?

Olmamalı.

## Test prosedürü

Primary fixture:

```text
1 audio
0 photos
```

ile manifest/report.

## Başarı kriterleri

- [ ] JSON manifest var.
- [ ] MD manifest var.
- [ ] Part manifestleri var.
- [ ] Report var.
- [ ] Global/local semantics açık.
- [ ] JSON/MD aynı gerçekleri taşıyor.
- [ ] 0-photo warning üretmiyor.
- [ ] AI/transcript içeriği yok.

## Sorun çıkarsa — düzeltme promptu

```text
Fix only RecorAndro manifest/report generation.

Problem:
[PASTE ISSUE]

Do not change audio processing or state/recovery logic.

Preserve:
- canonical global timeline
- part-local navigation semantics
- deterministic metadata
- zero-photo normal behavior
- no AI-derived lecture content

Add/update tests for the mismatch.
```

## Sonraki adıma geçiş koşulu

Audio-only gerçek session yalnız manifest/report ile bile dışarıdan anlaşılabilir olmalı.

---

# Adım 4.2 — Part ZIP packaging + Full Archive capability

## Amaç

Her audio part'ı ChatGPT'ye/share workflow'una uygun tek bir ZIP paketi haline getirmek ve gerektiğinde tam session arşivi oluşturabilmek.

## Neden

Final günlük akışta kullanıcı:
- klasör avlamamalı,
- audio + manifest eşleşmesini elle yapmamalı.

Ancak full archive'ın storage maliyeti part ZIP'lerden daha yüksek olabilir; bu nedenle capability ve default kararı ayrılmalıdır.

## Ön koşullar

- Manifest/report tamam.
- Artifact registry/recovery tamam.
- Audio-only session PASS.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- current manifests/reports
- artifact registry
- storage-preflight logic
- media contracts

Goal:
Implement deterministic audio-first part ZIP packaging and optional full-session archive capability.

PART ZIP

For every generated audio part create:

part_01.zip
part_02.zip
...

Core ZIP content:

- part audio
- part manifest.json
- part manifest.md

Optionally include a small deterministic report excerpt only if it materially helps and does not duplicate large data.

Do NOT require visual files in part ZIPs.

Important:
Audio-only packages are canonical and complete.

ZIP requirements:

- deterministic safe relative member paths
- no absolute paths
- no path traversal
- no unrelated session files
- verify referenced files before archive creation
- generate temp ZIP
- verify member list
- verify ZIP integrity
- atomically publish
- calculate archive size/hash
- register artifact

If packaging fails:
- audio parts/manifests remain valid
- bad ZIP is not canonical
- retry can regenerate ZIP only

FULL ARCHIVE CAPABILITY

Implement full archive generation as an OPTIONAL capability.

Do NOT hardcode Lecture default ON.

The request must come from an explicit resolved archive decision.

Before generating a full archive:
perform a SECOND-STAGE storage check using current actual artifact sizes.

Reason:
initial preflight is an estimate; by archive time real normalized/part/ZIP sizes are known.

If space is insufficient:
- do not delete existing artifacts
- do not create partial canonical archive
- report required/free bytes
- session audio/package success remains valid
- archive status may be skipped_due_to_storage or equivalent nonfatal status

Suggested full archive content:

- managed original audio
- managed original photos if they exist later
- normalized audio if generated
- audio parts
- canonical manifests
- processing report
- part ZIPs if the contract chooses to include them
- session metadata snapshot appropriate for archive

Avoid pointless nested duplication if it makes the archive excessively wasteful.
If including part ZIPs plus their unpacked content causes major duplicate storage, define a compact archive layout and document it.

The priority is:
- complete recoverable session archive
- understandable structure
- reasonable storage duplication

Create:
docs/PACKAGE_AND_ARCHIVE.md

Document:
- part ZIP canonical contents
- full archive capability
- second-stage storage preflight
- full archive default remains pending real-device measurements
- protected vs regenerable files

TESTING

- audio-only one-part package
- audio-only multi-part packages
- ZIP member safety
- archive integrity
- packaging failure
- second-stage insufficient storage
- full archive optional skip
- original hashes preserved
- no visual dependency

Before edits:
- propose ZIP member layout
- propose full-archive layout
- explicitly estimate duplication tradeoff
- list planned changes

After edits:
- run tests
- show one audio-only part ZIP member list
- show one full archive member tree
- show one insufficient-storage archive case
- stop before visual subsystem
```

## Codex'in üretmesi gerekenler

Örnek:

```text
packages/
├── part_01.zip
├── part_02.zip
└── part_03.zip

archives/
└── optional_full_archive.zip
```

Ayrıca:

```text
docs/PACKAGE_AND_ARCHIVE.md
```

## Şimdi senin yapman gereken

Gerçek audio-only lecture üzerinde:

1. `part_01.zip` aç.
2. İçinde yalnız beklenen:
   - audio
   - manifest JSON
   - manifest MD
   olduğunu doğrula.
3. Diğer part ZIP'leri kontrol et.
4. Full archive capability'yi bir kez manuel ON ile test et.
5. Archive member tree'yi incele.
6. ZIP içinde gereksiz dev duplicate yapı oluşmuş mu bak.

Ayrıca gerçek cihaz storage ekranında:
- archive öncesi boş alan,
- archive sonrası boş alan

not al.

Bu ölçüm PART 3'te full archive default kararına girdi olacaktır.

## Test prosedürü

Primary:

```text
1 audio
0 photos
multi-part
```

ile part ZIP + optional archive.

## Başarı kriterleri

- [ ] Part ZIP audio-first.
- [ ] Visual dependency yok.
- [ ] ZIP güvenli relative member paths.
- [ ] ZIP integrity PASS.
- [ ] Package failure audio core'u geçersiz yapmıyor.
- [ ] Full archive explicit capability.
- [ ] Full archive default hâlâ unfrozen.
- [ ] Archive öncesi second-stage storage check var.
- [ ] Storage yetmezse audio/package success korunuyor.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only RecorAndro packaging/archive behavior.

Problem:
[PASTE FAILURE]

Do not modify audio algorithms.

Preserve:
- audio-only package is complete
- no mandatory visuals
- safe ZIP paths
- temp -> verify -> atomic publish
- full archive optional
- second-stage storage check
- archive failure is nonfatal to already valid audio packages

Add a regression test and make the smallest fix.
```

## Sonraki adıma geçiş koşulu

Gerçek audio-only session doğru part ZIP'lere dönüşebilmeli.

---

# FAZ 5 — Optional visual attachment subsystem

# Adım 5.1 — Fotoğrafları küçük, non-blocking optional attachment subsystem olarak ekle

## Amaç

Fotoğraf seçildiğinde orijinalleri korumak ve daha sonra ChatGPT bağlamı için yararlı hafif metadata üretmek; fotoğrafı RecorAndro çekirdeğinin merkezi haline getirmemek.

## Neden

Gerçek kullanımda fotoğraf:
- seyrek olabilir,
- hiç olmayabilir,
- çekim saati anlatımın kesin zamanı değildir.

Bu nedenle v0.1'de:

> **Visual capture time is a hint, not authoritative lecture timing.**

## Ön koşullar

- Audio-only pipeline package seviyesine kadar PASS.
- Görselsiz session tam ve kullanılabilir.

## Model / Efor

**GPT-6 Sol — Medium**

## Codex Promptu

```text
Continue the RecorAndro repository.

Goal:
Implement a SMALL OPTIONAL visual-attachment subsystem.

This is intentionally secondary to the audio pipeline.

Core rule:

A session with ZERO photos is fully normal and complete.
No warning, no prompt, no missing-feature state, no degraded package.

Do not redesign the core state machine around visuals.

INPUT

Canonical session input remains:
- exactly 1 audio
- optionally 0..N photos

When photos are supplied:

IMPORT

- perform safe managed import/preservation
- preserve original bytes
- calculate size/hash
- use safe filenames
- preserve original filename in metadata
- assign stable visual IDs such as V001, V002...
- handle Turkish/Unicode/long filenames
- use temp -> verify -> atomic publish

STORAGE

Visual import must be included in the resolved session storage calculation when photos are actually selected.

If adding photos changes required space beyond available space:
- fail visual intake clearly before destructive/partial canonical import
- do not corrupt the already valid audio session
- define whether user can continue audio-only when visuals cannot be imported
- prefer preserving a usable audio-only session

METADATA

Extract only lightweight metadata useful for future context where available:

- visual_id
- original filename
- size
- SHA-256
- format
- dimensions if easy
- EXIF DateTimeOriginal if available
- timezone/offset metadata if available
- metadata source/status

TIMING POLICY

If capture time exists:
- store it as optional metadata
- optionally compute an approximate offset hint only if an audio start reference exists and doing so is straightforward
- mark timing_role = "hint_only"

Do NOT:
- treat capture time as authoritative lecture timing
- hard-map visuals to exact audio timestamps
- force visual -> audio part assignment
- duplicate visuals into part ZIPs by default
- fail the audio pipeline because EXIF is missing
- add OCR
- add image understanding
- add semantic matching

MISSING/BAD METADATA

If EXIF is missing or malformed:
- keep the original photo
- metadata_status may indicate unavailable/partial
- this is not an audio-session failure

SESSION / REPORT INTEGRATION

For zero photos:
- visual_count = 0
- no visual-specific warning
- no visual-specific report section required

For photos:
- visual_count = N
- include concise optional visual summary
- maintain a visual_index.json and/or visual_index.md only if useful
- keep it session-level

PACKAGE / ARCHIVE

Part ZIPs remain audio-first.
Do not add visuals to specific parts.

If full archive is requested:
- include original managed visuals and visual index at session level.

STATE / RECOVERY

Do not create a complex visual state machine.

A small status is enough:
- not_present
- indexed
- partial_warning
- failed_nonblocking

If one photo metadata parse fails:
- other visuals continue
- audio packages remain valid

TESTING

PRIMARY fixture:
- 1 audio
- 0 photos

It must complete the entire pipeline with:
- no visual files
- no visual warnings
- no visual prompts
- no degraded output

SECONDARY fixtures:
- 1 photo
- multiple photos
- JPEG
- HEIC/HEIF storage/indexing if practical
- missing EXIF
- malformed EXIF
- Unicode filename
- long filename
- one bad photo among valid photos
- visual import storage failure
- audio-only continuation after nonfatal visual failure

Before edits:
- explain the minimal visual data model
- state explicitly how zero-photo behavior remains unchanged
- list planned changes

After edits:
- run tests
- show zero-photo output tree before vs after this feature
- prove there is no unnecessary visual artifact/warning for zero photos
- show one photo-session visual index
- stop after this step
```

## Codex'in üretmesi gerekenler

Opsiyonel:

```text
originals/photos/
visual_index.json
```

ve/veya:

```text
visual_index.md
```

Ama **0-photo session'da bu dosyalar zorunlu değildir**.

## Şimdi senin yapman gereken

İki gerçek test yap.

### Test A — Birincil

```text
1 audio
0 photos
```

Bütün pipeline:

```text
import
probe
normalization
segmentation
parts
manifest/report
ZIP
optional archive decision
complete
```

tamamlanmalı.

Kontrol:
- visual prompt yok
- visual warning yok
- gereksiz boş visual dosyaları yok
- part ZIP'ler aynı kalitede

### Test B — İkincil

```text
1 audio
birkaç gerçek fotoğraf
```

Kontrol:
- originals korunuyor
- visual ID var
- capture time varsa hint olarak saklanıyor
- hard audio mapping yok
- part ZIP'e zorla görsel konmamış
- kötü metadata audio pipeline'ı bozmuyor

## Test prosedürü

Audio-only fixture **önce**.

Sonra optional-photo fixture.

## Başarı kriterleri

- [ ] 0-photo first-class davranış korunuyor.
- [ ] Visual subsystem core pipeline'a dependency eklemiyor.
- [ ] Photo originals korunuyor.
- [ ] Metadata lightweight.
- [ ] Capture time hint_only.
- [ ] Hard audio mapping yok.
- [ ] Forced part assignment yok.
- [ ] Visual metadata failure non-blocking.
- [ ] Part ZIP audio-first.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only the optional RecorAndro visual-attachment subsystem.

Problem:
[PASTE FAILURE]

Do not modify audio processing, segmentation, manifests or package semantics unless the bug is proven to originate there.

Preserve:
- zero-photo first-class workflow
- visuals optional/non-blocking
- original photos preserved
- timing_role=hint_only
- no hard visual->audio mapping
- no forced part assignment
- no visual requirement in part ZIPs

Add a regression test and make the smallest fix.
```

## Sonraki adıma geçiş koşulu

Audio-only pipeline görseller eklendikten sonra bile davranış olarak değişmemiş olmalı.

---

# PART 2 — Final Acceptance Gate

PART 3'e geçmeden önce aşağıdakiler tamam olmalıdır.

## Session state

- [ ] Finite state model var.
- [ ] Artifact registry var.
- [ ] Protected/regenerable ayrımı var.
- [ ] Atomic session metadata write var.
- [ ] 0-photo state normal.

## Recovery

- [ ] Process kill sonrası session tanınıyor.
- [ ] Resume last verified artifact'tan ilerliyor.
- [ ] Partial output canonical değil.
- [ ] Duplicate processing engelli.
- [ ] Stale lock recoverable.
- [ ] Original hiçbir recovery senaryosunda kaybolmuyor.

## Manifest/report

- [ ] Session manifest JSON var.
- [ ] Session manifest MD var.
- [ ] Part manifestleri var.
- [ ] processing_report.md var.
- [ ] Global/local timestamp semantiği açık.
- [ ] Audio-only manifest eksiksiz.
- [ ] 0-photo missing-feature warning üretmiyor.

## Packaging

- [ ] Her part için ZIP var.
- [ ] Part ZIP audio + manifest merkezli.
- [ ] Visual dependency yok.
- [ ] ZIP güvenli.
- [ ] Temp -> verify -> publish.
- [ ] Full archive capability var.
- [ ] Lecture full archive default hâlâ measurement sonrası freeze edilecek.
- [ ] Archive öncesi second-stage storage check var.
- [ ] Archive failure audio/package success'i bozmuyor.

## Visuals

- [ ] 0-photo birincil acceptance case.
- [ ] 0-photo full pipeline PASS.
- [ ] Görsel seçilirse originals korunuyor.
- [ ] Lightweight metadata/index var.
- [ ] EXIF timing authoritative değil.
- [ ] timing_role = hint_only.
- [ ] Hard visual->audio mapping yok.
- [ ] Forced part assignment yok.
- [ ] Visual metadata hatası audio pipeline'ı fail ettirmiyor.

---

# PART 2 birincil end-to-end acceptance fixture

Özellikle şu fixture kullanılmalıdır:

```text
1 real lecture audio
0 photos
45–70 MB
~1–1.5 hours
```

Beklenen zincir:

```text
storage preflight
↓
immutable import
↓
probe
↓
normalization
↓
segmentation
↓
parts
↓
state/artifact registration
↓
manifest/report
↓
part ZIPs
↓
optional archive decision
↓
complete
```

Şunların hiçbiri olmamalı:

```text
visual warning
visual confirmation
visual-specific blocker
photo placeholder requirement
degraded-output status because photos are absent
```

Bu test PASS olmadan PART 3'e geçme.

---

# PART 2 secondary acceptance fixture

```text
1 real lecture audio
3–10 photos
```

Beklenen:

```text
same audio pipeline
+
optional visual import/index
```

Görseller:
- session-level,
- non-blocking,
- hint_only.

---

# PART 2 tamamlandığında frozen kabul edilecekler

PART 3 artık şunları yeniden tasarlamamalıdır:

```text
session state semantics
artifact protected/regenerable classification
resume/retry principles
duplicate-run prevention
atomic publication
manifest schema v0.1
part package structure
audio-first ZIP behavior
full archive capability
second-stage archive storage check
visual optional/non-blocking policy
visual hint_only policy
zero-photo acceptance behavior
```

PART 3 şu konulara odaklanacaktır:

```text
real-device performance measurements
hotspot-active scenario
screen-off/background/MIUI behavior
battery/temperature/thermal
full archive default freeze
Android integration method selection
daily UX
edge-case/reliability pass
real lecture field acceptance
v0.1 freeze
```

---

# PART 2 geliştirme sırası

```text
3.1 Session state + artifact registry
↓
3.2 Recovery / resume / locking
↓
4.1 Manifest + report
↓
4.2 Part ZIP + optional full archive
↓
5.1 Optional visual attachments
↓
PART 2 audio-only acceptance
↓
PART 2 optional-photo acceptance
```

Toplam:

**5 orta büyüklükte Codex geliştirme adımı + 2 acceptance fixture.**

---

# PART 2 sonunda beklenen teknik kullanım

Henüz final Android UX değildir.

Teknik kullanım kabaca:

```text
RecorAndro CLI
↓
session process
↓
verified parts
↓
manifest/report
↓
part ZIPs
↓
optional archive
```

Görseller seçilmişse:

```text
+
session-level optional visual index
```

PART 3'te hedef:

```text
Audio seç
Photos optional
PROCESS
↓
Ready
↓
Share Part 1
Share Part 2
Share Part 3
```

seviyesine inmektir.

---

**Dosya sonu — RecorAndro v0.1 SETUP PART 2 / 3**


# RecorAndro v0.1 — Teknik Kurulum ve Codex Geliştirme Planı
## PART 3 / 3 — Faz 6–7
### Real-device ölçüm → Android integration → Daily UX → Reliability → Field acceptance → v0.1 freeze

**Proje:** RecorAndro  
**Hedef sürüm:** v0.1  
**Bu dosya:** PART 3 / 3  
**Kapsam:** Faz 6 ve Faz 7  
**Önceki dosya:** `RECORANDRO_V0.1_SETUP_PART2.md`  
**Bu seri:** 3 / 3

---

# 0. Bu bölümün amacı

PART 1 sonunda RecorAndro'nun media-processing çekirdeği hazırdır.

PART 2 sonunda:
- session state,
- recovery,
- artifact registry,
- manifest/report,
- part ZIP,
- optional full archive capability,
- optional visual attachment subsystem

hazırdır.

PART 3'ün amacı artık yeni core feature eklemek değildir.

Bu bölüm:

1. gerçek Redmi Note 10 Pro üzerinde performans ve stabiliteyi ölçer,
2. screen-off/background/MIUI/hotspot koşullarını test eder,
3. Full Archive profile default kararını gerçek storage footprint üzerinden freeze eder,
4. günlük kullanım için en küçük Android integration yöntemini seçer,
5. teknik CLI'ı minimum günlük UX'e dönüştürür,
6. Android-specific edge-case ve reliability turunu yapar,
7. gerçek ders günü field acceptance ile v0.1'i dondurur.

Bu bölüm tamamlandığında hedef kullanıcı akışı:

```text
Audio seç
Photos optional
↓
PROCESS
↓
Ready
↓
Share Part 1
Share Part 2
Share Part 3
↓
Optional Full Archive
```

Core processing için:
- PC gerekmez,
- server gerekmez,
- Cloudflare gerekmez,
- internet gerekmez.

---

# 1. PART 3 boyunca değiştirilmeyecek çekirdek kontratlar

PART 1 ve PART 2'de freeze edilmiş şu alanlar artık ancak gerçek bir blocker varsa değiştirilebilir:

```text
media input contract
normalization semantics
normalization output contract
segmentation semantics
tiny-part policy
part media format
overlap
source/global timeline
source-end coverage
immutable original model
storage-preflight ordering
session state semantics
artifact registry
resume/retry principles
manifest schema
part ZIP structure
visual optional/non-blocking policy
visual hint_only policy
zero-photo first-class workflow
```

PART 3'te amaç bunları yeniden tasarlamak değil, **gerçek Android koşullarında doğrulamak ve usable UX'e bağlamak**.

---

# 2. PART 3 acceptance önceliği

Başarı sırası:

1. audio processing correctness
2. process survival / resumability
3. storage safety
4. Android usability
5. battery / thermal acceptability
6. hotspot coexistence
7. visual attachment convenience
8. polish

UI güzelliği bu sıranın sonlarındadır.

---

# FAZ 6 — Real-device ölçüm ve Android günlük kullanım katmanı

# Adım 6.1 — Redmi Note 10 Pro gerçek-device performance / survival benchmark

## Amaç

RecorAndro'nun gerçek hedef cihaz üzerinde:
- processing süresi,
- peak storage,
- battery,
- sıcaklık,
- thermal throttling,
- process survival,
- screen-off/background,
- hotspot coexistence

davranışını ölçmek.

## Neden

Desktop üzerinde doğru çalışan media pipeline'ın Android'de pratik olması garanti değildir.

Özellikle Xiaomi/MIUI:
- aggressive background management,
- battery optimization,
- thermal throttling

uygulayabilir.

Ayrıca cihaz aynı zamanda iPhone için hotspot görevi görebilir.

Bu nedenle gerçek acceptance ölçümü zorunludur.

## Ön koşullar

- PART 1 PASS.
- PART 2 PASS.
- Audio-only end-to-end session tamamlanabiliyor.
- Gerçek 1–1.5 saat lecture audio mevcut.
- Hedef cihaz final OTA/build üzerinde.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Do NOT redesign media algorithms.

Goal:
Add lightweight measurement/instrumentation and a repeatable real-device benchmark protocol for the Xiaomi Redmi Note 10 Pro.

Create:

docs/DEVICE_PERFORMANCE_TEST.md

and, if useful, a small technical benchmark command such as:

recorandro benchmark <session_id>

or an equivalent reporting mechanism.

Do not add a synthetic performance framework if existing session processing can already record the required metrics.

MEASURE PER STAGE

For a real lecture session record:

- source audio duration
- source audio size
- free storage before session
- storage-preflight estimate
- import time
- probe time
- normalization measurement time
- normalization processing time if applied
- segmentation analysis time
- part export time
- manifest/report time
- ZIP packaging time
- full archive time if explicitly tested
- total elapsed processing time
- generated artifact sizes
- observed peak/approximate storage footprint
- free storage after processing

DEVICE / POWER METRICS

Where available without adding heavy dependencies:

- battery percentage before
- battery percentage after
- approximate battery drain
- device/battery temperature before
- peak or sampled temperature during processing
- temperature after
- evidence of thermal throttling if detectable
- unexpected process termination
- FFmpeg/process errors

Do not pretend unavailable Android thermal metrics are exact.
Clearly label:
- measured
- estimated
- unavailable

REQUIRED REAL-DEVICE SCENARIOS

A. Foreground / screen on
- RecorAndro/Termux remains active
- process a real lecture

B. Screen off
- start processing
- turn screen off
- verify completion or failure

C. Background app switch
- start processing
- switch to another app
- return later
- verify process survival

D. Hotspot active + screen off + RecorAndro processing
This is a first-class real-use scenario.

Measure:
- process survival
- processing time
- temperature
- battery drain
- thermal throttling signs
- hotspot stability
- whether connected iPhone loses connectivity
- whether RecorAndro processing causes unacceptable hotspot degradation

E. Optional full archive ON
- explicitly enable archive
- measure extra time
- measure extra storage
- record peak footprint

MIUI / ANDROID NOTES

Document current battery/background settings relevant to Termux.

Do NOT automatically disable system protections.
Do NOT require root to perform the benchmark.

If screen-off/background execution fails:
- record the exact failure first
- do not immediately add hacks
- defer mitigation to the Android integration step

FULL ARCHIVE DECISION INPUT

At the end, calculate/report enough evidence to decide:

Lecture profile Full Archive default:
- ON
- OFF
- ASK/PROFILE-CONTROLLED

Do not make the product decision automatically unless the existing behavior contract already defines objective thresholds.

TEST DATA

Primary benchmark:
- real lecture audio
- approximately 45–70 MB
- approximately 1–1.5 hours
- zero photos

Secondary benchmark:
- same/similar lecture with a few optional photos if useful

Zero-photo benchmark is primary.

Before edits:
- explain what metrics can actually be measured reliably on this Android environment
- list any metrics that require manual observation
- keep instrumentation lightweight

After edits:
- run automated tests
- provide the exact real-device benchmark checklist
- stop before changing Android UX/integration
```

## Codex'in üretmesi gerekenler

En az:

```text
docs/DEVICE_PERFORMANCE_TEST.md
```

ve mümkünse session/report içinde performance ölçümleri.

Gereksiz benchmark framework eklenmemeli.

## Şimdi senin yapman gereken

Aynı veya benzer gerçek lecture ile sırayla test yap:

### Test A — Screen ON

```text
hotspot OFF
screen ON
foreground
```

Kaydet:
- total time
- battery %
- temperature
- storage

### Test B — Screen OFF

```text
hotspot OFF
screen OFF
```

Kontrol:
- process hayatta kaldı mı?
- tamamlandı mı?
- Termux öldürüldü mü?

### Test C — Background

Processing sırasında başka uygulamaya geç.

Sonra dön.

### Test D — Gerçek hotspot senaryosu

```text
hotspot ON
+
iPhone connected
+
screen OFF
+
RecorAndro processing
```

Ölç:

- process survival
- total processing time
- temperature
- battery drain
- thermal throttling belirtileri
- hotspot kopması var mı?
- iPhone internetinde ciddi bozulma oluyor mu?

### Test E — Full Archive

Aynı/benzer session'da Full Archive explicit ON.

Ölç:
- ek süre
- ek storage
- peak storage
- archive boyutu

## Test prosedürü

Primary fixture:

```text
1 real lecture audio
0 photos
~45–70 MB
~1–1.5 h
```

Fotoğraflı fixture secondary.

## Başarı kriterleri

- [ ] Foreground processing PASS.
- [ ] Screen-off sonucu ölçülmüş.
- [ ] Background sonucu ölçülmüş.
- [ ] Hotspot-active + screen-off sonucu ölçülmüş.
- [ ] Battery drain kaydedilmiş.
- [ ] Temperature kaydedilmiş.
- [ ] Thermal davranış not edilmiş.
- [ ] Storage footprint ölçülmüş.
- [ ] Full Archive maliyeti ölçülmüş.
- [ ] Zero-photo benchmark ana referans.
- [ ] Root benchmark için gerekmedi.

## Sorun çıkarsa — düzeltme promptu

```text
Analyze only the real-device RecorAndro performance/survival failure.

Scenario:
[PASTE SCENARIO]

Observed:
[PASTE METRICS / FAILURE]

Do not change media algorithms.

Determine whether the issue is primarily:
- Android/MIUI background management
- Termux process lifecycle
- FFmpeg resource use
- storage pressure
- thermal throttling
- hotspot coexistence
- another measured platform constraint

Do not implement a large workaround yet.

First document the likely layer and the smallest mitigation candidates for the next Android-integration step.
```

## Sonraki adıma geçiş koşulu

Gerçek cihaz davranışı ölçülmüş ve bilinmeyen kritik performans alanı kalmamış olmalı.

---

# Adım 6.2 — Full Archive profile default freeze + Android integration yöntemi seçimi

## Amaç

İki açık product/technical kararı gerçek ölçümler üzerinden kapatmak:

1. Lecture profile için Full Archive default ne olacak?
2. Günlük Android UX hangi integration katmanı üzerinden kurulacak?

## Neden

Bu kararlar teorik değil, gerçek cihaz davranışına bağlıdır.

## Ön koşullar

- Adım 6.1 tamam.
- Full archive storage/time ölçümü var.
- Screen-off/background/hotspot sonucu var.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

This is a DECISION/FREEZE step, not a broad implementation step.

Read:
- docs/DEVICE_PERFORMANCE_TEST.md
- actual benchmark results
- current behavior/media contracts
- current session/package/archive implementation
- current Termux environment docs

Goal:
Freeze two v0.1 decisions based on real-device evidence.

PART A — FULL ARCHIVE PROFILE DEFAULT

Choose and document the Lecture profile default as one of:

- ON
- OFF
- ASK / PROFILE-CONTROLLED

Base the decision on:
- measured peak storage
- archive duplication cost
- archive generation time
- available device storage
- recovery value
- typical lecture size
- expected weekly usage

Do not select ON merely because archive capability exists.

Update:
docs/BEHAVIOR_CONTRACT.md
docs/PACKAGE_AND_ARCHIVE.md

Record:
- chosen default
- evidence
- override behavior
- when storage preflight blocks archive

PART B — ANDROID DAILY INTEGRATION METHOD

Evaluate the smallest implementation that can meet the target UX:

Target UX:

1. user intentionally selects one audio
2. optionally selects photos
3. chooses/accepts profile
4. starts processing
5. can leave the screen if real-device behavior allows
6. sees progress/status
7. receives Ready/Failed state
8. can share part ZIPs
9. can open output folder
10. does not need to type Termux commands in daily use

Candidate approaches may include:

- Termux:API + scripts/shortcuts
- Tasker + Termux integration
- Termux Widget / shortcut-style launcher
- a very thin native Android shell that invokes the existing core
- another minimal Android integration if objectively simpler

Decision criteria:

1. reliability on the actual Redmi/MIUI build
2. minimum complexity
3. ability to select Android files
4. ability to trigger existing RecorAndro core
5. progress/status visibility
6. share/open-output support
7. screen-off/background behavior
8. maintainability
9. no need to rewrite media core
10. root must remain optional unless a specific integration capability truly needs it

Do not choose a native app merely for polish.

Create:

docs/ANDROID_INTEGRATION_DECISION.md

It must contain:
- measured constraints
- selected integration method
- rejected alternatives and concise reasons
- root requirement: yes/no/optional
- process-lifecycle strategy
- file-selection strategy
- output/share strategy
- daily user flow
- known limitations

Do not implement the selected UX in this step beyond tiny proof-of-concept checks if necessary for the decision.

Before writing:
- use the actual Redmi measurements
- distinguish measured facts from assumptions

After writing:
- list the two frozen decisions
- stop before full UX implementation
```

## Codex'in üretmesi gerekenler

Güncellenmiş:

```text
docs/BEHAVIOR_CONTRACT.md
docs/PACKAGE_AND_ARCHIVE.md
docs/ANDROID_INTEGRATION_DECISION.md
```

## Şimdi senin yapman gereken

İki kararı kontrol et.

### Full Archive

Karar gerçekten ölçümlere dayanıyor mu?

Örneğin:
- storage çok düşükse OFF,
- kabul edilebilirse ON,
- değişken ise ASK/profile-controlled

olabilir.

### Android integration

Seçilen yöntem:
- günlük terminal komutu gerektiriyor mu?
- gereksiz native app complexity yaratıyor mu?
- mevcut Python core'u tekrar yazıyor mu?

İstemiyoruz.

## Test prosedürü

Dokümantasyon/decision review.

Gerekirse seçilen integration için küçük proof-of-concept manual check.

## Başarı kriterleri

- [ ] Full Archive Lecture default artık frozen.
- [ ] Karar gerçek storage ölçümüne dayalı.
- [ ] Android integration yöntemi frozen.
- [ ] Media core yeniden yazılmıyor.
- [ ] Root gerekmedikçe dependency değil.
- [ ] Daily terminal typing final UX değil.

## Sorun çıkarsa — düzeltme promptu

```text
Revisit only the RecorAndro v0.1 decision in question:

[Full Archive default OR Android integration method]

Use the measured Redmi Note 10 Pro data.

Do not redesign the media core.

Explain:
- evidence
- candidate options
- tradeoff
- selected decision

Prefer the smallest reliable solution over the most polished architecture.
```

## Sonraki adıma geçiş koşulu

Full Archive default ve Android integration yöntemi net/frozen olmalı.

---

# Adım 6.3 — Günlük Android UX implementation

## Amaç

Teknik CLI tabanlı sistemi gerçek günlük kullanıma uygun minimum Android flow'a çevirmek.

## Neden

Final kullanıcı davranışı:

```text
Termux aç
cd ...
python ...
path yaz
```

olmamalıdır.

## Ön koşullar

- Android integration yöntemi Adım 6.2'de frozen.
- Core/session/package davranışı stabil.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Continue the RecorAndro repository.

Read:
- docs/ANDROID_INTEGRATION_DECISION.md
- docs/BEHAVIOR_CONTRACT.md
- docs/PACKAGE_AND_ARCHIVE.md
- current CLI/core/session implementation

Goal:
Implement the MINIMUM reliable Android daily UX defined by the frozen integration decision.

Do not rewrite the media engine.

The UI/integration is a thin orchestration layer over the existing RecorAndro core.

TARGET DAILY FLOW

Start:

New Processing

Profile:
[ Lecture ]
[ Quick / Other ]

Audio:
[ Select Audio ]

Photos:
[ Optional ]

Advanced:
collapsed by default

Main action:
[ PROCESS ]

ADVANCED

Expose only the controls already supported by frozen contracts:

Normalization:
- Auto
- Force
- Off

Segmentation:
- Auto
- Force
- Off

Full Archive:
- use frozen profile default
- allow explicit override if contract allows

Do not expose raw FFmpeg parameters.

PROCESSING STATUS

Show/communicate at least:

- importing
- probing
- normalization: applied/skipped
- segmentation: single / N parts
- packaging
- optional archive
- ready
- failed

Do not surface internal stack traces in normal UI.

RESULT

When complete, provide easy actions:

- Share Part 1
- Share Part 2
- Share Part 3...
- Open Output
- Share/Open Full Archive when generated
- View Processing Report if useful

ZERO-PHOTO UX

This is critical:

If no photos are selected:
- do not ask again
- do not show a warning
- do not show an empty visual screen
- do not show "0 photos missing"
- proceed directly

If photos are selected:
- show only minimal optional photo count/status

FILE SELECTION

Use the selected Android integration method to make selecting audio/photos practical.

Do not require users to manually type file paths in daily use.

RECOVERY

If the user reopens a partially processed session:
- surface Resume when appropriate
- do not force a new session
- do not expose complex internal state-machine details

BACKGROUND / SCREEN OFF

Use only the minimum mitigation justified by real-device tests.

If the chosen integration requires:
- wake lock
- battery-optimization exclusion guidance
- foreground notification/service
- Termux wake-lock
- another mechanism

implement only what the measured device behavior requires.

Do not add root unless the frozen integration decision explicitly requires a narrow root helper.

SHARE

Use Android sharing/opening mechanisms supported by the chosen integration.

The final share target may be ChatGPT or another app, but RecorAndro must not depend on any specific cloud service/API.

ERROR UX

Examples:
- insufficient storage
- unsupported audio
- FFmpeg failure
- interrupted session
- archive skipped due to storage

Messages should be concise and actionable.

Do not create a settings-heavy product.

TESTING

Automated/unit where practical plus real-device manual tests:

- audio-only Lecture
- audio + photos Lecture
- Quick profile
- Auto normalization
- Off normalization
- Auto segmentation
- Off segmentation
- storage failure
- resume interrupted session
- share each part
- open output
- no-photo path has no visual UI friction

Before edits:
- show the exact daily flow
- list the minimum integration files/components
- explicitly state what remains in Python core vs Android wrapper

After edits:
- run automated tests
- provide exact real-device UX test steps
- stop before broad reliability review
```

## Codex'in üretmesi gerekenler

Seçilen integration yöntemine göre:
- launcher/shortcut/UI wrapper
- file selection
- processing trigger
- status/progress
- share/open output
- resume surface

Ama media core'u duplicate etmemeli.

## Şimdi senin yapman gereken

Gerçek cihazda **hiç terminal komutu yazmadan** test et.

### Test A — Audio-only Lecture

1. RecorAndro'yu günlük giriş noktasından aç.
2. Lecture.
3. Audio seç.
4. Fotoğraf seçme.
5. Process.
6. Ready.
7. Part 1 share.
8. Part 2 share.
9. Output aç.

Kontrol:
- photo prompt çıktı mı? Çıkmamalı.
- path yazmak gerekti mi? Gerekmemeli.

### Test B — Optional photos

Aynı akış, birkaç fotoğraf ile.

### Test C — Resume

Processing'i kontrollü kes.
Tekrar aç.
Resume görünmeli.

## Test prosedürü

Gerçek Android UI/integration.

## Başarı kriterleri

- [ ] Günlük terminal typing yok.
- [ ] Audio seçimi kolay.
- [ ] Photos gerçekten optional.
- [ ] Process tek ana action.
- [ ] Progress/status anlaşılır.
- [ ] Ready state açık.
- [ ] Part share kolay.
- [ ] Open Output var.
- [ ] Resume kullanılabilir.
- [ ] Advanced default collapsed.
- [ ] Root only if genuinely required.
- [ ] Core duplicate edilmemiş.

## Sorun çıkarsa — düzeltme promptu

```text
Debug only the RecorAndro Android daily UX/integration layer.

Problem:
[PASTE UX OR INTEGRATION FAILURE]

Do not rewrite media-processing code.

Preserve:
- existing Python/core behavior
- audio-first workflow
- zero-photo no-friction path
- minimal interface
- user-triggered processing
- Android-local execution

Make the smallest integration-layer fix and add tests where practical.
```

## Sonraki adıma geçiş koşulu

Audio-only gerçek session günlük UI üzerinden terminal kullanmadan tamamlanmalı.

---

# FAZ 7 — Reliability, gerçek ders field test ve v0.1 freeze

# Adım 7.1 — Android-focused reliability / edge-case review

## Amaç

Public bir servis için gereksiz security engineering yapmadan, kişisel local kullanımda veri kaybı veya günlük failure yaratabilecek edge-case'leri kapatmak.

## Neden

RecorAndro public değildir.

Bu nedenle v0.1 için:
- auth,
- network attack surface,
- multi-user isolation,
- cloud hardening

gereksizdir.

Ama:
- original loss,
- bad path,
- corrupt package,
- process kill,
- low storage,
- Android filename/path issues

önemlidir.

## Ön koşullar

- Daily UX çalışıyor.
- Core freeze edilmiş.

## Model / Efor

**GPT-6 Sol — High**

## Codex Promptu

```text
Perform a focused RecorAndro v0.1 reliability review.

This is a PERSONAL LOCAL Android utility.

Do NOT add:
- authentication
- network security systems
- multi-user permissions
- cloud threat modeling
- database
- server
- enterprise hardening

Do NOT redesign working media algorithms.

Review only failures that matter for:
- data integrity
- Android local filesystem safety
- process survival/recovery
- package correctness
- daily usability

TEST / REVIEW MATRIX

MEDIA INPUT
- 5 min audio
- around one-part threshold
- ~25–30 min
- ~61 min
- ~90 min
- quiet audio
- already loud audio
- no suitable silence
- malformed audio
- supported secondary input format

FILENAMES / PATHS
- Turkish characters
- spaces
- emoji
- very long filename
- duplicate filenames
- path traversal-like names
- Android shared-storage paths if applicable

STORAGE
- insufficient space before import
- insufficient space before full archive
- temp growth
- archive optional skip
- protected originals never deleted

PROCESS FAILURE
- FFmpeg unavailable
- ffprobe unavailable
- FFmpeg returns failure
- generated output invalid
- process killed during normalization
- process killed during part export
- process killed during ZIP
- stale lock
- duplicate run
- resume

PACKAGES
- one-part ZIP
- multi-part ZIP
- ZIP integrity
- manifest/audio match
- archive integrity
- no unexpected visual dependency

VISUALS
PRIMARY:
- zero photos
SECONDARY:
- one photo
- several photos
- missing EXIF
- malformed EXIF
- bad image among valid images

Zero-photo must remain the primary acceptance path.

ANDROID
- screen off
- app switch/background
- hotspot active
- hotspot active + screen off
- battery optimization condition as actually configured
- selected integration/share flow

SAFE SUBPROCESS / FILESYSTEM

Verify:
- shell=True is not used
- user filenames are not interpolated into shell commands
- managed paths stay inside data root
- original media are not overwritten
- atomic publication is preserved

Do not perform an enterprise security audit.

Create:

docs/V0_1_RELIABILITY_REVIEW.md

For each issue:
- reproduce when practical
- make the smallest fix
- add regression test
- avoid refactoring unrelated working modules

After fixes:
- run full automated test suite
- list manual real-device tests still required
- list known limitations
- stop before final field acceptance
```

## Codex'in üretmesi gerekenler

```text
docs/V0_1_RELIABILITY_REVIEW.md
```

ve gerekli küçük bugfix/regression testleri.

## Şimdi senin yapman gereken

Manual-required maddeleri gerçek Redmi üzerinde uygula.

Özellikle:
- screen off
- hotspot + screen off
- share
- resume
- low-storage davranışı
- 0-photo

testlerini atlama.

## Test prosedürü

Automated suite + gerçek Android manual subset.

## Başarı kriterleri

- [ ] Critical data-loss bug yok.
- [ ] Original overwrite yok.
- [ ] Low storage güvenli.
- [ ] Recovery güvenli.
- [ ] Part ZIP'ler doğru.
- [ ] 0-photo primary workflow PASS.
- [ ] Hotspot scenario ölçülmüş/acceptable.
- [ ] Bilinen limitation'lar dokümante.
- [ ] Gereksiz public-service security eklenmemiş.

## Sorun çıkarsa — düzeltme promptu

```text
RecorAndro reliability review found one concrete bug:

[DESCRIBE BUG]

Reproduce this exact behavior first.

Fix only the relevant layer.
Do not redesign the application.
Do not add public-service security or architecture.

Add a regression test and run the relevant suite.
```

## Sonraki adıma geçiş koşulu

Critical/major günlük kullanım problemi kalmamalı.

---

# Adım 7.2 — Gerçek ders field acceptance + v0.1 freeze

## Amaç

RecorAndro'nun gerçek günlük ihtiyacı karşıladığını tek bir tam ders günü zinciriyle kanıtlamak ve ardından v0.1 scope'u dondurmak.

## Neden

Laboratuvar testleri başarılı olsa bile final ürün kriteri:

> Gerçek ders sonrası Android üzerinde minimum eforla işlenip ChatGPT'ye paylaşılabilir audio part'lar üretmek.

## Ön koşullar

- Faz 6 tamam.
- Reliability review tamam.
- Günlük UX kullanılabilir.

## Model / Efor

**GPT-6 Sol — High**  
(Yalnız acceptance hazırlığı ve hata analizi için; başarılı akışta kod yazılması gerekmez.)

## Codex Promptu

```text
Prepare RecorAndro v0.1 for final real-world field acceptance.

Do not add new product features.

Create:

docs/FIELD_ACCEPTANCE_V0_1.md

The primary field test must be AUDIO-ONLY.

PRIMARY REAL-LECTURE ACCEPTANCE

Input:
- one real university lecture audio
- zero photos
- realistic duration around 1–1.5 hours
- realistic file size

Daily user flow:

1. open the RecorAndro daily entry point
2. choose Lecture profile
3. select audio
4. do not select photos
5. start processing
6. optionally turn screen off / use the normal real-world phone pattern
7. hotspot may be active if this is the real-use condition
8. processing completes or resumes cleanly if interrupted
9. Ready state appears
10. share/open Part 1
11. share/open remaining parts
12. inspect processing report
13. optionally generate/use Full Archive according to frozen profile default

Verify:

- no PC
- no server
- no Cloudflare
- no internet required for processing
- no terminal command typing in daily flow
- no visual warning/prompt
- original preserved
- correct normalization decision
- sensible parts
- no tiny residual part
- overlap correct
- source-end covered
- manifests match parts
- ZIPs open correctly
- share works
- storage behavior acceptable
- temperature/battery acceptable
- hotspot remains acceptable when used

SECONDARY ACCEPTANCE

Repeat with:
- a few optional photos

Verify:
- audio behavior remains unchanged
- visual originals preserved
- visuals remain session-level optional attachments
- timing metadata is hint_only
- no forced visual->part mapping

FAILURE ACCEPTANCE

At least one controlled recoverability check:
- interrupt a disposable/test session
- reopen
- resume
- verify protected original
- verify no fake-complete artifact

Create a concise result section:

FINAL RESULT:
- PASS
- PASS WITH MINOR KNOWN LIMITATIONS
- FAIL

BLOCKERS:
...

MINOR ISSUES:
...

MEASURED METRICS:
...

KNOWN LIMITATIONS:
...

V0.1 FREEZE

If final result is PASS or PASS WITH MINOR KNOWN LIMITATIONS:

Create:
docs/V0_1_FREEZE.md

Document:

1. frozen v0.1 feature set
2. frozen behavior contracts
3. daily user workflow
4. target device/build
5. chosen Android integration method
6. Full Archive profile default
7. known limitations
8. accepted manual requirements if any
9. changes allowed after freeze:
   - bug fixes
   - data-integrity fixes
   - Android compatibility fixes
   - high-impact daily UX friction fixes
10. changes deferred beyond v0.1:
   - transcription
   - OpenAI/ChatGPT API automation
   - Notion API
   - OCR
   - semantic visual matching
   - cloud sync
   - server
   - database
   - broad native-app redesign unless real need appears

Do not refactor working code merely for style.

If final result is FAIL:
- do not create a release freeze pretending success
- list blockers only

Before changes:
- verify current scope and acceptance prerequisites

After:
- report acceptance checklist
- report whether v0.1 is eligible to freeze
```

## Codex'in üretmesi gerekenler

```text
docs/FIELD_ACCEPTANCE_V0_1.md
```

Başarılıysa ayrıca:

```text
docs/V0_1_FREEZE.md
```

## Şimdi senin yapman gereken

Gerçek ders günü birincil acceptance'ı yap.

### Primary — Audio only

```text
1 gerçek ders
0 fotoğraf
```

Normal günlük şekilde.

Processing sırasında gerçekten yaptığın davranışı uygula:
- hotspot kullanıyorsan hotspot açık,
- ekran kapatıyorsan kapalı,
- başka app'e geçiyorsan geç.

Laboratuvar gibi telefonu masaya bırakmak yerine **gerçek davranışı** test et.

Sonuçta:

- part ZIP'leri paylaş,
- seslerin başlangıç/sonlarını spot-check et,
- report'u kontrol et.

### Secondary — Fotoğraflı

Başka bir session veya aynı dönemde gerçek fotoğraflı lecture ile test et.

### Recovery

Önemli olmayan/test session'da kontrollü interrupt/resume yap.

## Test prosedürü

Gerçek field test.

## Başarı kriterleri

### Core

- [ ] PC yok.
- [ ] Server yok.
- [ ] Cloudflare yok.
- [ ] Processing internet bağımsız.
- [ ] Günlük terminal typing yok.
- [ ] Original korunmuş.
- [ ] Normalization doğru.
- [ ] Segmentation doğru.
- [ ] Tiny residual part yok.
- [ ] Overlap doğru.
- [ ] Source end tam.
- [ ] ZIP'ler açılıyor.
- [ ] Share çalışıyor.

### Android

- [ ] Real daily behavior altında process survive ediyor veya düzgün resume ediyor.
- [ ] Battery kabul edilebilir.
- [ ] Temperature kabul edilebilir.
- [ ] Hotspot gerekiyorsa stabil.
- [ ] MIUI blocker yok veya belgelenmiş minimal mitigation yeterli.

### Visual policy

- [ ] 0-photo primary flow eksiksiz.
- [ ] Photo absence hiçbir prompt/warning üretmiyor.
- [ ] Optional photos audio behaviorını değiştirmiyor.
- [ ] Hard mapping yok.

### Storage

- [ ] Preflight doğru.
- [ ] Archive default gerçek ölçümle uyumlu.
- [ ] Peak footprint kabul edilebilir.

### Freeze

- [ ] Critical blocker yok.
- [ ] v0.1 freeze oluşturulabilir.

## Sorun çıkarsa — düzeltme promptu

```text
RecorAndro final field acceptance found a concrete blocker:

Scenario:
[DESCRIBE REAL USE]

Expected:
[EXPECTED]

Actual:
[ACTUAL]

Relevant metrics/logs:
[PASTE]

Fix this blocker only.

Do not broaden scope.
Do not add deferred v0.1+ features.
Preserve all frozen media/data-integrity contracts.

Reproduce where practical, add regression coverage, and update the field acceptance result.
```

## Sonraki adıma geçiş koşulu

Final result:

```text
PASS
```

veya kullanıcı tarafından kabul edilmiş küçük limitation'larla:

```text
PASS WITH MINOR KNOWN LIMITATIONS
```

olmalı.

---

# PART 3 — Final Acceptance Gate

RecorAndro v0.1 tamamlanmış sayılmadan önce:

## Device / performance

- [ ] Final Redmi build kayıtlı.
- [ ] Real lecture benchmark tamam.
- [ ] Screen-on ölçüldü.
- [ ] Screen-off ölçüldü.
- [ ] Background/app-switch ölçüldü.
- [ ] Hotspot ON + screen OFF + processing ölçüldü.
- [ ] Hotspot stability kontrol edildi.
- [ ] Battery drain kaydedildi.
- [ ] Temperature kaydedildi.
- [ ] Thermal throttling değerlendirilmiş.
- [ ] Peak storage footprint ölçülmüş.

## Full Archive

- [ ] Capability çalışıyor.
- [ ] Second-stage storage check çalışıyor.
- [ ] Lecture profile default gerçek ölçümle freeze edilmiş.
- [ ] Default kararı gerekçeli.

## Android integration

- [ ] Integration yöntemi gerçek cihaz verisiyle seçilmiş.
- [ ] Core yeniden yazılmamış.
- [ ] Root gereksiz dependency değil.
- [ ] Daily terminal typing yok.

## Daily UX

- [ ] Audio seçilebiliyor.
- [ ] Photos optional.
- [ ] Process tek ana işlem.
- [ ] Status/progress anlaşılır.
- [ ] Ready state var.
- [ ] Share Part çalışıyor.
- [ ] Open Output çalışıyor.
- [ ] Resume erişilebilir.
- [ ] Advanced default collapsed/minimal.

## Audio-only primary acceptance

- [ ] 1 gerçek lecture.
- [ ] 0 photos.
- [ ] Full pipeline PASS.
- [ ] Visual warning yok.
- [ ] Visual prompt yok.
- [ ] Visual placeholder dependency yok.

## Optional visuals

- [ ] Fotoğraflı session ayrıca PASS.
- [ ] Original photos korunuyor.
- [ ] Metadata lightweight.
- [ ] timing_role=hint_only.
- [ ] Audio behavior değişmiyor.

## Reliability

- [ ] Low storage güvenli.
- [ ] Process kill recoverable.
- [ ] Stale lock recoverable.
- [ ] Package integrity doğru.
- [ ] Unicode/long filenames safe.
- [ ] Original overwrite yok.
- [ ] Unsafe shell construction yok.

## Final freeze

- [ ] `FIELD_ACCEPTANCE_V0_1.md` tamam.
- [ ] Sonuç PASS veya kabul edilmiş minor limitation.
- [ ] `V0_1_FREEZE.md` oluşturuldu.
- [ ] Scope v0.1 için kapatıldı.

---

# RecorAndro v0.1 final günlük mimari

```text
ANDROID
  │
  ├── Select Audio
  ├── Optional Photos
  └── Profile
        │
        ▼
Storage Preflight
        │
        ▼
Immutable Managed Import
        │
        ▼
ffprobe
        │
        ▼
Normalization
Auto / Force / Off
        │
        ▼
Segmentation
Auto / Force / Off
        │
        ▼
Verified Audio Parts
        │
        ▼
Manifest + Report
        │
        ▼
Part ZIPs
        │
        ├── Optional Visual Attachments
        │
        └── Optional Full Archive
        │
        ▼
READY
        │
        ├── Share Part 1
        ├── Share Part 2
        ├── Share Part 3
        └── Open Output
```

---

# 3 parçalık teknik setup serisinin özeti

## PART 1 — Faz 0–2

```text
Device baseline
Recora actual implementation extraction
Behavior/media contract freeze
Termux/Python/FFmpeg scaffold
Storage preflight
Immutable import
ffprobe
Normalization
Segmentation planner
Part export
Recora behavioral parity
```

## PART 2 — Faz 3–5

```text
Session state
Artifact registry
Recovery/resume
Duplicate-run prevention
Atomic publication
Manifest/report
Part ZIP
Full Archive capability
Second-stage archive storage check
Optional visual attachments
Audio-only package acceptance
```

## PART 3 — Faz 6–7

```text
Redmi real-device benchmark
Screen/background/MIUI
Hotspot ON + screen OFF + processing
Battery / temperature / thermal
Full Archive default freeze
Android integration selection
Daily UX
Reliability review
Real lecture field acceptance
v0.1 freeze
```

---

# v0.1 sonrasında bilinçli olarak ertelenenler

Aşağıdakiler gerçek kullanım açıkça gerektirmedikçe v0.1'e geri sokulmamalıdır:

```text
OpenAI API
ChatGPT automatic upload
transcription engine
Whisper
Notion API
PACE integration
OCR
semantic visual matching
hard visual/audio alignment
cloud sync
server
database
multi-device orchestration
automatic folder watcher
large native-app redesign
complex root automation
```

---

# Geliştirme disiplini

RecorAndro artık bir feature-development projesinden çok günlük utility olarak ele alınmalıdır.

Final acceptance sonrası öncelik:

```text
bug fix
>
data integrity
>
Android compatibility
>
high-impact UX friction
>
new feature
```

Çalışan media core yalnız "daha temiz kod" uğruna yeniden yazılmamalıdır.

---

**Dosya sonu — RecorAndro v0.1 SETUP PART 3 / 3**
