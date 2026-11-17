"""A complete, valid run directory used across tests. Mutate copies, never the originals."""

import copy

RUN = {"mode": "full", "host": "claude", "created_at": "2026-11-17T10:00:00+08:00",
       "skill_version": "0.1.0", "slug": "test-case"}

MODELS = {
    "host": "claude",
    "host_vendor": "anthropic",
    "engines": [
        {"engine": "codex", "vendor": "openai", "available": True, "cross_model": True,
         "can_search": True, "same_tier": True, "isolation": "partial", "probe": "ok"},
    ],
}

SOURCE = {"input_type": "text", "original_text": "某部長說：明年油價一定漲三成，快轉傳！",
          "url": None, "outlet": None, "byline": None, "published_at": None,
          "retrieved_at": "2026-11-17T10:00:00+08:00", "notes": ""}

CLAIMS = {
    "prompt_was_leading": True,
    "claims": [
        {"id": "C1", "original": "某部長說明年油價一定漲三成", "neutral": "某部長曾公開表示明年油價會上漲三成",
         "type": "F", "importance": 5, "core": True, "legal": False,
         "time_place": "2026 台灣", "entities": ["某部長"],
         "search_seeds": {"pro": ["部長 油價 三成"], "con": ["部長 否認 油價"]}},
        {"id": "C2", "original": "快轉傳！", "neutral": "呼籲轉傳", "type": "O", "importance": 1,
         "core": False, "legal": False, "time_place": "", "entities": [], "search_seeds": {"pro": [], "con": []}},
    ],
}

TRACE = {
    "first_seen": {"date": "2026-11-10", "url": "https://example.org/post", "platform": "LINE", "note": ""},
    "variants": [],
    "prior_factchecks": [{"org": "台灣事實查核中心", "url": "https://tfc-taiwan.org.tw/x", "label": "錯誤", "date": "2026-11-12"}],
    "publisher": {"kind": "anonymous", "name": "匿名轉傳", "outlet_id": None, "byline": "n/a",
                  "wording_issues": [], "flagged": []},
    "spread_signals": [],
    "attribution": [],
    "tactics": [{"tactic_id": "TW-T01", "quote": "快轉傳！", "explanation": "急迫轉傳"}],
    "limits": [],
}

LEDGER = [
    {"id": "S1", "claim_ids": ["C1"], "url": "https://ivod.ly.gov.tw/x", "title": "質詢影片",
     "publisher": "立法院", "accessed": "2026-11-17", "tier": 1, "chain": "ly-ivod",
     "stance": "refutes", "excerpt": "部長：油價會視國際情勢調整，沒有說三成", "access_note": "full"},
    {"id": "S2", "claim_ids": ["C1"], "url": "https://www.cna.com.tw/x", "title": "中央社報導",
     "publisher": "中央社", "accessed": "2026-11-17", "tier": 3, "chain": "cna",
     "stance": "refutes", "excerpt": "部長表示未曾預測漲幅", "access_note": "full"},
]

PROPONENT = {
    "ledger": copy.deepcopy(LEDGER),
    "verdicts": [
        {"claim_id": "C1", "label": "false", "reasoning": "完整質詢影片中部長沒有說三成",
         "evidence_ids": ["S1", "S2"], "context_flags": [], "law_text_obtained": None},
        {"claim_id": "C2", "label": "not_factual", "reasoning": "呼籲轉傳不是事實陳述",
         "evidence_ids": [], "context_flags": [], "law_text_obtained": None},
    ],
    "prior_factchecks_rechecked": [
        {"org": "台灣事實查核中心", "url": "https://tfc-taiwan.org.tw/x", "their_label": "錯誤",
         "claim_ids": ["C1"], "agree": True, "note": "已獨立核對其引用的 1 項原始資料"}],
}

OPP_A = {"seat": "A", "engine": "claude", "lens": "evidence", "status": "ok", "searches_run": 3,
         "attacks": [{"id": "A-1", "claim_id": "C1", "target": "reasoning",
                      "argument": "中央社報導日期早於影片，不能互相印證", "proposed_label": None, "evidence": []}]}
OPP_B = {"seat": "B", "engine": "claude", "lens": "counter", "status": "ok", "searches_run": 5,
         "attacks": [{"id": "B-1", "claim_id": "C1", "target": "label",
                      "argument": "部長在另一場記者會說過類似的話", "proposed_label": "misleading",
                      "evidence": [{"url": "https://example.org/presser", "excerpt": "油價可能上漲兩到三成"}]}]}
OPP_C = {"seat": "C", "engine": "claude", "lens": "stance", "status": "ok", "searches_run": 1, "attacks": []}
OPP_X1 = {"seat": "X1", "engine": "codex", "lens": "external", "status": "ok", "searches_run": 4, "attacks": []}

REBUTTAL = {"responses": [
    {"attack_id": "A-1", "accept": False, "response": "兩者是獨立來源，日期不影響", "evidence": []},
    {"attack_id": "B-1", "accept": True, "response": "確有此發言，但說的是『可能』", "evidence": []},
]}

JUDGMENT = {
    "rulings": [
        {"attack_id": "A-1", "upheld": False, "reason": "日期先後不影響來源獨立性", "verified_urls": []},
        {"attack_id": "B-1", "upheld": True, "reason": "已打開記者會逐字稿，確有『可能上漲兩到三成』",
         "verified_urls": ["https://example.org/presser"]},
    ],
    "verdicts": [
        {"claim_id": "C1", "label": "misleading", "reasoning": "部長說的是『可能上漲兩到三成』，訊息改成『一定漲三成』",
         "evidence_ids": ["S1", "S3"], "context_flags": ["out_of_context"], "law_text_obtained": None},
        {"claim_id": "C2", "label": "not_factual", "reasoning": "呼籲轉傳不是事實陳述",
         "evidence_ids": [], "context_flags": [], "law_text_obtained": None},
    ],
    "ledger": copy.deepcopy(LEDGER) + [
        {"id": "S3", "claim_ids": ["C1"], "url": "https://example.org/presser", "title": "記者會逐字稿",
         "publisher": "經濟部", "accessed": "2026-11-17", "tier": 1, "chain": "moea",
         "stance": "refutes", "excerpt": "油價可能上漲兩到三成", "access_note": "full"}],
}

REVIEW_B = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": True, "reason": "改判誤導合理"}]}


def run_files(**overrides):
    files = {
        "run.json": RUN, "models.json": MODELS, "source.json": SOURCE, "claims.json": CLAIMS,
        "trace.json": TRACE, "proponent.json": PROPONENT, "opponent-A.json": OPP_A,
        "opponent-B.json": OPP_B, "opponent-C.json": OPP_C, "opponent-X1.json": OPP_X1,
        "rebuttal.json": REBUTTAL, "judgment.json": JUDGMENT, "review-B.json": REVIEW_B,
    }
    files = copy.deepcopy(files)
    for k, v in overrides.items():
        name = k.replace("__", "-").replace("_json", ".json")
        if v is None:
            files.pop(name, None)
        else:
            files[name] = v
    return files
