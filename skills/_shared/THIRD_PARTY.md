# Third-party source and provenance

`vendor/memtx/` contains nine files copied **without modification** from
[lxy1134/MEMTX_](https://github.com/lxy1134/MEMTX_/tree/4e1124ccd5fd384857463020e3497aa73ec93be6),
commit `4e1124ccd5fd384857463020e3497aa73ec93be6`.
See [UPSTREAM.json](vendor/memtx/UPSTREAM.json) for the exact file inventory,
SHA-256 digests and original Git blob identities. Copyright remains with the
upstream authors. This is the execution core and its README, not the full
benchmark repository, datasets or a reproduction of the paper's experiments.

At that commit the upstream repository declares **no license**. Its status is
`NOASSERTION`, not MIT. The GResearchEvolver MIT license applies to this project's
own work and does not relicense the copied upstream files. Local integration was
explicitly requested; a public redistribution license for these files has not
been established. Keep this notice and the upstream manifest with any local build.

`runtime/gresearch/memtx.py` and `memtx_worker.py` are integration code. The copied
manager performs staging, commits, conflict detection, lifecycle transitions and
typed cascading rollback. The bridge adds JSON process isolation, durable CAS
snapshots, exact revisions, actor binding, stricter premise checks and research
graph projection. No upstream mock tool is executed. An upstream `compensated`
receipt records a decision only; it does not undo real files, SSH jobs or external
effects.

Other long-horizon code references are documented in
[the design report](../../docs/long-horizon/01-design/report.md). DeepRewind,
GRACE and JANUS informed the design; their implementations are not vendored here.
The context handoff is deterministic archival, not a reproduction of Slipstream's
asynchronous compression algorithm.
