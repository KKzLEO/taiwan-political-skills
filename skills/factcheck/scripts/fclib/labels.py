"""Fixed vocabularies shared by every script. Changing a value here changes scoring."""

from decimal import Decimal

# Claim verdict labels → scoring factor (None = not scored).
FACTORS = {
    "true": Decimal("1.00"),
    "mostly_true": Decimal("0.80"),
    "mixed": Decimal("0.50"),
    "unverified": Decimal("0.35"),
    "misleading": Decimal("0.25"),
    "false": Decimal("0.00"),
    "not_factual": None,
}

ZH_LABELS = {
    "true": "正確",
    "mostly_true": "大致正確",
    "mixed": "部分錯誤",
    "unverified": "無法證實",
    "misleading": "誤導",
    "false": "錯誤",
    "not_factual": "非事實陳述",
}

CONTEXT_FLAGS = {
    "out_of_context": "斷章取義",
    "time_shift": "時間錯置",
    "missing_denominator": "數字缺少分母",
    "recycled_media": "舊圖新用",
    "legal_stage_confusion": "法案階段混淆",
    "old_news": "舊聞新炒",
}

CLAIM_TYPES = {
    "F": "事實",
    "S": "統計",
    "I": "隱含",
    "O": "意見",
    "P": "預測",
    "U": "無法查證",
}

# Opinion, prediction and vague claims never count, whatever label the judge gives them: they may share
# text with scored claims (spans only checks F/S and I), so scoring them would count one sentence twice.
UNSCORED_TYPES = {"O", "P", "U"}

STANCES = {"supports", "refutes", "context"}
DIRECT_STANCES = {"supports", "refutes"}
ACCESS_NOTES = {"full", "paywall", "blocked", "archived", "snippet", "not_original", "no_transcript"}
PRIMARY_TIERS = {1, 2}
TIER_NAMES = {
    1: "第一手原始資料",
    2: "官方說明",
    3: "獨立可靠媒體",
    4: "具名專家與查核機構",
    5: "利害關係人自述",
    6: "來源不明",
}
ATTACK_TARGETS = {"label", "evidence", "reasoning", "neutral_rewrite", "trace", "tactic"}
REVIEW_STATUSES = {"none", "passed", "failed"}
PUBLISHER_KINDS = {"news", "public_figure", "official", "anonymous", "content_farm",
                   "private_individual", "unknown"}
TARGET_CAMPS = {"國民黨", "民進黨", "民眾黨", "時代力量", "政府機關", "中國官方", "外國政府", "非政黨"}
TACTIC_LAYERS = {"content", "spread", "attribution"}
MODES = {"quick", "full"}
HOSTS = {"claude", "codex"}
