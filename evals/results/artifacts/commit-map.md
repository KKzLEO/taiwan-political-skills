# commit 編號對照表

2026-11-20 公開這個 repo 之前，把每一筆 commit 的作者欄和提交者欄改成專案名義。改寫作者欄會讓所有 commit 的編號改變，但內容和時間都沒有變：

- **文件和評測紀錄裡寫的是改寫前的編號**（左欄）。這些檔案沒有為了換編號而修改，所以開跑前登記的檔案仍然是當時 commit 進去的那一份。
- 要在這個 repo 裡找到對應的 commit，查右邊的新編號。
- 每一筆的內容編號（tree）和提交時間，改寫前後完全相同。用 `git log --format='%h %t %ci'` 可以自己核對內容編號和時間。

| 改寫前的編號 | 現在的編號 | 內容編號（tree） | 提交時間（+08:00） | 說明 |
|---|---|---|---|---|
| `0a4a736` | `a513369` | `dab406ab50` | 2026-11-20 16:28 | Quick mode measured once on a real host; where each release criterion stands |
| `5dd4030` | `1dde466` | `95e76a4676` | 2026-11-20 16:08 | Real hosts: both ran the skill end to end; the seat loops now start together in zsh |
| `d484fa7` | `1c0c61e` | `d3a9a4f9ac` | 2026-11-20 13:07 | After the re-review (3 of 3): the fixes it asked for |
| `f9c9af7` | `81ab3ef` | `4775d0354a` | 2026-11-20 12:25 | Review fixes: nothing the program writes in report.md depends on tactic tags |
| `6fb0639` | `03cf96d` | `988dd564f8` | 2026-11-20 11:46 | After the blind batch: results recorded; a report no longer lists tactic tags unless asked |
| `9964286` | `3a9f70d` | `577e4b625f` | 2026-11-20 02:58 | Pre-register the final blind batch for 0.2.0 (code at d838c71) |
| `d838c71` | `c8561bf` | `e0536bf370` | 2026-11-20 02:58 | Before the blind batch: a seat that fails again keeps the report; a deadline needs no citation |
| `903c669` | `d01c52f` | `453d95f61b` | 2026-11-20 02:37 | Final review fixes: a redone step removes what later steps built on the old one |
| `b2ad749` | `c941463` | `f10b345ff0` | 2026-11-20 02:28 | Keep the recovered eval records in the repo; say what set-aside keeps for the judge's file |
| `27d685e` | `b0fdf4d` | `2e146fe821` | 2026-11-20 02:26 | Docs and packaging brought in line with the code |
| `17fafc2` | `2ada141` | `e6b1f697b1` | 2026-11-20 02:26 | Roles are not told what a time verdict does to the score; the publication time must be a date |
| `0cea757` | `12fbbaa` | `77803f5ee6` | 2026-11-20 02:25 | Eval harness: survive a stuck step; count every requested case; show failed seats and content-only scores |
| `62cb57a` | `31e3d09` | `dbaedd3a85` | 2026-11-20 01:54 | Eval harness: run the leading-question and injection probes; list split-only runs |
| `c2b057b` | `6f97f45` | `2ba8418eea` | 2026-11-20 01:51 | Version 0.2.0 in the script and the plugin manifest, with a test that they agree |
| `33fbeb5` | `49e669e` | `5eeaccbb80` | 2026-11-20 01:50 | Report: keep the time-claim line apart from the seat table |
| `0dfa999` | `c80f4e2` | `5732bb8bee` | 2026-11-20 01:50 | Audit fixes: role calls, run flow and video |
| `31ee229` | `0ef7d24` | `9368016838` | 2026-11-20 01:40 | Audit fixes: report wording and safety |
| `84b07fc` | `544a845` | `83232cdfd7` | 2026-11-20 01:28 | Add twelve new blind cases (027-038) with independently audited answer keys |
| `ed17bfb` | `ba5afcd` | `3a6b2f2e59` | 2026-11-20 01:02 | Review fixes for the core-code audit package |
| `09ed779` | `94ba7d8` | `4219f72a0e` | 2026-11-20 00:33 | WIP: audit fixes for the core code (not yet independently reviewed) |
| `b064733` | `bbde32a` | `10273006b6` | 2026-11-19 23:07 | Eval runner: add --prep-only to look at how a message is split |
| `7a82d7b` | `9447cca` | `c8d5052c10` | 2026-11-19 22:57 | Time claims only lower a result; motive guesses are opinions; publishable only at the two ends |
| `9f3221e` | `f38846e` | `753249a03d` | 2026-11-19 20:37 | Add release criteria, an in-repo eval harness and a time-rule symmetry probe |
| `d29c72e` | `3021b35` | `f3b4f52163` | 2026-11-19 17:30 | Record the second holdout run (cases 021-026) |
| `7d4da62` | `35596ef` | `be5aa2f797` | 2026-11-19 16:25 | Main-claims-first scoring, time rule, isolated ingest-and-split step |
| `ab12063` | `7d5e153` | `b00ff6a183` | 2026-11-19 14:28 | Review judge-only label changes; record the holdout run |
| `c5e4b85` | `ee4d980` | `947bb82394` | 2026-11-19 13:12 | Round 3: unscored opinion claims, judge URL fallback, isolated Claude host roles |
| `8d4a5fa` | `634128b` | `2d875b6843` | 2026-11-19 02:09 | Round 2: stop double-counted claims, share one tagging standard, isolate claude -p |
| `a282766` | `a40ed5d` | `46d3703e84` | 2026-11-18 03:34 | Fix five issues found in the first full eval run; record results |
| `0f6b79a` | `4c31d4d` | `580b5f2409` | 2026-11-17 22:41 | Correct the run-time estimate with measured numbers |
| `6b835b8` | `dfbc3c2` | `54252cfcaf` | 2026-11-17 22:14 | Raise external-model timeout to 20 min and stop retrying timeouts |
| `d6571d8` | `2135ffb` | `6cfb5bede1` | 2026-11-17 21:49 | Fix two scoring/report issues found in the first real run; add example |
| `6782f36` | `6d3ad7d` | `d80f1fba6f` | 2026-11-17 21:28 | Tell internal opponent seats which engine to record |
| `e72be1d` | `3ef75a3` | `0f817a88f7` | 2026-11-17 21:18 | Add Taiwan fact-check skill v0.1.0 |
