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
