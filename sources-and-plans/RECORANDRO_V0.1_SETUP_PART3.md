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
