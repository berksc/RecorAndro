# RecorAndro v0.1 scope

RecorAndro is a separate Android project. Recora remains a frozen Windows/server reference implementation. RecorAndro does not inherit Recora's server, Cloudflare, Windows deployment, remote-upload, or web architecture.

RecorAndro v0.1 is Android-first, local-first, user-triggered, and audio-first. A canonical session contains exactly **1 audio** file and optionally **0..N photos**. A session with zero photos is complete and valid. Normal use requires no PC.

The v0.1 scope has no server, Cloudflare, database, OpenAI API, Notion API, transcription engine, OCR, or cloud sync.

> Recora parity means media-processing behavior and invariants only. It does not imply code, filesystem, state-machine, deployment or architecture parity.
