# Baseline (seed 1337)

Measured before integration changes on Windows with Python 3.13.5. Each row
uses the generated scenario's `disk.img` and `ground_truth.json`, a fresh
engine output directory, and `python -m scorer.score --strict`. Runtime is the
engine wall time; scoring time is excluded.

| Scenario | Precision | Recall | Completeness | False-positive rate | Metadata accuracy | Classification accuracy | Runtime (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| A — clean_deleted | 100% | 100% | 100% | 0% | 100% | 100% | 2.432 |
| B — corrupted_fs | 100% | 100% | 100% | 0% | 0% | 100% | 1.487 |
| C — fragmented | 100% | 100% | 100% | 0% | 100% | 100% | 2.038 |
| D — demo_mixed | 100% | 100% | 100% | 0% | 62.12% | 100% | 1.784 |
| E — empty_fs | 0% | 0% | 0% | 0% | 0% | 0% | 1.296 |
| F — not_fat | 0% | 0% | 0% | 0% | 0% | 0% | 0.736 |

E and F have zero expected recoverable files and zero results. The scorer
currently reports zero for their ratio metrics; those values do not mean a
recovery was missed. Scenario B has no recoverable directory metadata, and
scenario D exposes metadata reconstruction gaps despite exact file recovery.

Fixture generation reported image SHA-256 values:

| Scenario | SHA-256 |
|---|---|
| A | `c525b6f95e94dec02b6b6b7ee2435bf26fccfab6af1d11880e5b18fa25827ce6` |
| B | `16cf732cf919c2f86d73fe3b3c4ad41dea74207d31b4cc91ac655ddb990d2342` |
| C | `05c432ea3b86584e036efef6b41a753d07c93d1cb3650b8c13b1efe3df30fdec` |
| D | `b1ec7cb63456ba5c729122da5dead109f64d73188fbbce427fe35b571899d43b` |
| E | `61c2bc7510c705f2bc6b7a0dd11ace5e3cca055e8630c83f9b8fa902da2e3d45` |
| F | `41699d1afc96ebe002aad73070708e0a7ef1614725f6d57001ac657baf502004` |

The optional `fsck.fat`, `mdir`, and `mcopy` checks were unavailable; the
generator used its internal re-parse validation. This is a tuning baseline,
not a holdout result.
