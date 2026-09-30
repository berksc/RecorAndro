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
