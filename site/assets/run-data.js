// Written by site/tools/build_run.py from examples/. Do not edit by hand.
window.FACTCHECK_RUN = {
 "folder": "20261120-1441-機車大燈罰三千",
 "host": "Claude Code",
 "mode": "完整模式",
 "at": "2026-11-20 14:41",
 "steps": [
  {
   "id": "input",
   "name": "讀入",
   "file": "input.json",
   "does": "收下來的時候一個字都不改。",
   "summary": "貼上的文字，完整模式",
   "kind": "message",
   "text": "立法院昨天三讀通過，以後騎機車一律要開大燈，沒開罰三千！快轉給家人。",
   "raw": {
    "file": "input.json",
    "href": "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/20261120-1441-機車大燈罰三千/input.json",
    "total": 6,
    "lines": [
     "{",
     "  \"input_type\": \"text\",",
     "  \"content\": \"立法院昨天三讀通過，以後騎機車一律要開大燈，沒開罰三千！快轉給家人。\\n\",",
     "  \"prompt\": \"用 factcheck 幫我查核這則 LINE 轉傳的訊息，用完整模式。我現在不在電腦前，中途不要問我問題，照 skill 的步驟一路做到報告出來，最後照規定…",
     "  \"url\": null",
     "}"
    ]
   }
  },
  {
   "id": "claims",
   "name": "拆題",
   "file": "claims.json",
   "does": "由一個看不到你怎麼問的獨立程序，拆成可以查證的說法，改寫成不帶立場的句子。",
   "summary": "拆成 6 條說法，其中 1 條是意見，不計分",
   "kind": "claims",
   "rows": [
    {
     "id": "C1",
     "quote": "立法院昨天三讀通過",
     "text": "立法院三讀通過一項法案，內容與騎機車開大燈有關。",
     "type": "事實",
     "importance": 4
    },
    {
     "id": "C2",
     "quote": "以後騎機車一律要開大燈",
     "text": "往後騎機車一律要開大燈。",
     "type": "事實",
     "importance": 5
    },
    {
     "id": "C3",
     "quote": "沒開罰三千",
     "text": "騎機車沒開大燈會被罰三千元。",
     "type": "事實",
     "importance": 3
    },
    {
     "id": "C4",
     "quote": "以後騎機車一律要開大燈",
     "text": "騎機車一律要開大燈、沒開要罰的規定已經生效，現在就適用。",
     "type": "隱含",
     "importance": 3
    },
    {
     "id": "C5",
     "quote": "立法院昨天三讀通過",
     "text": "這次三讀是查核日期的前一天（2026 年 11 月 19 日）發生的。",
     "type": "隱含",
     "importance": 3
    },
    {
     "id": "C6",
     "quote": "快轉給家人",
     "text": "呼籲讀者把這則訊息轉傳給家人。",
     "type": "意見",
     "importance": 1
    }
   ],
   "raw": {
    "file": "claims.json",
    "href": "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/20261120-1441-機車大燈罰三千/claims.json",
    "total": 161,
    "lines": [
     "{",
     "  \"prompt_was_leading\": false,",
     "  \"time_claims\": {",
     "    \"deadline\": null,",
     "    \"relative\": \"C5\"",
     "  },",
     "  \"claims\": [",
     "    {",
     "      \"id\": \"C1\",",
     "      \"original\": \"立法院昨天三讀通過\",",
     "      \"neutral\": \"立法院三讀通過一項法案，內容與騎機車開大燈有關。\",",
     "      \"type\": \"F\",",
     "      \"importance\": 4,",
     "      \"core\": true,",
     "      \"legal\": true,",
     "      \"time_place\": \"發布時間不明；台灣（立法院）\","
    ]
   }
  },
  {
   "id": "trace",
   "name": "溯源",
   "file": "trace.json",
   "does": "最早在哪裡出現、有沒有別的版本、有沒有人查過。查核機構的結論只當線索。",
   "summary": "查不到最早的出處；有 2 個相近的舊版本、2 份別人的查核報告",
   "kind": "notes",
   "rows": [
    {
     "tag": "相近的舊版本",
     "when": "2016-12-27",
     "text": "較早的相近傳言，不是同一段文字：當時在 LINE 流傳的是「2017 年元旦起汽機車上路要開大燈，否則罰款」，對象包含汽車，沒有提到立法院三讀，也沒有「罰三千」。報導沒有附傳言全文。"
    },
    {
     "tag": "相近的舊版本",
     "when": "2023-06-16",
     "text": "較早的相近傳言，不是同一段文字：內容是「台北市自 6 月 20 日起下午 5 時至翌日上午 7 時未開大燈罰 600 元」，限台北市、限時段、不限機車，沒有提到立法院三讀…"
    },
    {
     "tag": "台灣事實查核中心",
     "when": "2023-06-20",
     "text": "錯誤（查的是 2023 年「台北市未開大燈罰 600 元」版本，不是這一則）"
    },
    {
     "tag": "MyGoPen",
     "when": "2023-06-22",
     "text": "錯誤（查的是 2023 年「台北不開大燈罰 600 元」版本，不是這一則）"
    }
   ],
   "raw": {
    "file": "trace.json",
    "href": "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/20261120-1441-機車大燈罰三千/trace.json",
    "total": 125,
    "lines": [
     "{",
     "  \"first_seen\": null,",
     "  \"variants\": [",
     "    {",
     "      \"url\": \"https://www.storm.mg/article/206132\",",
     "      \"date\": \"2016-12-27\",",
     "      \"difference\": \"較早的相近傳言，不是同一段文字：當時在 LINE 流傳的是「2017 年元旦起汽機車上路要開大燈，否則罰款」，對象包含汽車，沒有提到立法院三讀…",
     "    },",
     "    {",
     "      \"url\": \"https://tfc-taiwan.org.tw/fact-check-reports/migration-9273/\",",
     "      \"date\": \"2023-06-16\",",
     "      \"difference\": \"較早的相近傳言，不是同一段文字：內容是「台北市自 6 月 20 日起下午 5 時至翌日上午 7 時未開大燈罰 600 元」，限台北市、限時段、…",
     "    }",
     "  ],",
     "  \"prior_factchecks\": [",
     "    {"
    ]
   }
  },
  {
   "id": "proponent",
   "name": "正方查證",
   "file": "proponent.json",
   "does": "逐句去找第一手資料：法條原文、立法院紀錄、官方說明。",
   "summary": "21 筆來源，其中 11 筆是第一手原始資料",
   "kind": "sources",
   "rows": [
    {
     "id": "S1",
     "title": "道路交通安全規則 第109條（法規修正日期：民國115年11月06日）",
     "by": "全國法規資料庫（法務部）",
     "tier": "第一手原始資料"
    },
    {
     "id": "S2",
     "title": "道路交通安全規則 沿革（最近一次修正為第134次…",
     "by": "全國法規資料庫（法務部）",
     "tier": "第一手原始資料"
    },
    {
     "id": "S3",
     "title": "道路交通管理處罰條例 第42條（法規修正日期：民國115年08月17日）",
     "by": "全國法規資料庫（法務部）",
     "tier": "第一手原始資料"
    },
    {
     "id": "S4",
     "title": "道路交通管理處罰條例 全文（修正日期：民國115年08月17日）第93條",
     "by": "全國法規資料庫（法務部）",
     "tier": "第一手原始資料"
    },
    {
     "id": "S5",
     "title": "道路交通管理處罰條例 沿革（最近一次修正公布：民國115年8月17日…",
     "by": "全國法規資料庫（法務部）",
     "tier": "第一手原始資料"
    },
    {
     "id": "S6",
     "title": "議案詳情：報告併案審查行政院函請審議等多案「道路交通管理處罰條例」修正草案（議案編號20…",
     "by": "立法院議事暨公報資訊網",
     "tier": "第一手原始資料"
    },
    {
     "id": "S7",
     "title": "立法院會議資料查詢：2026-11-19（回傳共8筆，7場委員會、1場黨團協商…",
     "by": "ly.govapi.tw（民間整理的立法院開…",
     "tier": "獨立可靠媒體"
    }
   ],
   "more": 14,
   "raw": {
    "file": "proponent.json",
    "href": "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/20261120-1441-機車大燈罰三千/proponent.json",
    "total": 455,
    "lines": [
     "{",
     "  \"ledger\": [",
     "    {",
     "      \"id\": \"S1\",",
     "      \"claim_ids\": [",
     "        \"C2\",",
     "        \"C4\"",
     "      ],",
     "      \"url\": \"https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=K0040013&flno=109\",",
     "      \"title\": \"道路交通安全規則 第109條（法規修正日期：民國115年11月06日）\",",
     "      \"publisher\": \"全國法規資料庫（法務部）\",",
     "      \"accessed\": \"2026-11-20\",",
     "      \"tier\": 1,",
     "      \"chain\": \"moj-道路交通安全規則\",",
     "      \"stance\": \"refutes\",",
     "      \"excerpt\": \"一、夜間應開亮頭燈。 二、行經隧道、調撥車道應開亮頭燈。 三、遇濃霧、雨、雪、天色昏暗或視線不清時，應開亮頭燈。\","
    ]
   }
  },
  {
   "id": "opponents",
   "name": "反方",
   "file": "opponent-*.json",
   "does": "三席各自檢查證據、找反證、看有沒有偏向哪一方；再請另一家公司的模型從頭挑一次。",
   "summary": "四席共搜尋 48 次，提出 11 條質疑，其中 7 條來自另一家公司的模型",
   "kind": "attacks",
   "seats": [
    {
     "seat": "A",
     "role": "反方 A：證據",
     "engine": "claude",
     "searches": 3,
     "attacks": 1
    },
    {
     "seat": "B",
     "role": "反方 B：反證",
     "engine": "claude",
     "searches": 13,
     "attacks": 0
    },
    {
     "seat": "C",
     "role": "反方 C：立場",
     "engine": "claude",
     "searches": 2,
     "attacks": 3
    },
    {
     "seat": "X1",
     "role": "外部反方",
     "engine": "codex",
     "searches": 30,
     "attacks": 7
    }
   ],
   "rows": [
    {
     "id": "A-1",
     "seat": "A",
     "on": "C2",
     "text": "正方在 C2 的理由寫「全天開頭燈的現行規定只適用大型重型機車行駛快速公路」，範圍說得太窄。高速公路及快速公路交通管制規則第20條第2項規定…"
    },
    {
     "id": "C-1",
     "seat": "C",
     "on": "手法標記",
     "text": "「舊聞新炒」這個標記的兩項特徵裡，查證得到的那一項「同樣的內容過去已經被查核過」不成立。溯源附的證據是 2016 年 12 月的風傳媒報導和交通部說明…"
    },
    {
     "id": "C-2",
     "seat": "C",
     "on": "C4",
     "text": "C4 的改寫比原文說得更強。原文是「以後騎機車一律要開大燈」，只說往後要開，沒有說規定「已經生效」或「現在就適用」；改寫卻寫成「規定已經生效，現在就適用」…"
    },
    {
     "id": "C-3",
     "seat": "C",
     "on": "C4",
     "text": "正方在 C4 標了「法案階段混淆」，理由是訊息把三讀通過直接說成以後一律要開。但正方在 C1 已經判定查不到這項三讀…"
    },
    {
     "id": "X1-1",
     "seat": "X1",
     "on": "C3",
     "text": "裁罰基準表確實列有大型重型機車行駛快速公路未開頭燈、期限內繳納或到案時罰 3,000 元的情形，適用《道路交通管理處罰條例》第 33 條第 1 項第 6 款…"
    },
    {
     "id": "X1-2",
     "seat": "X1",
     "on": "C2",
     "text": "正方說全天開頭燈的條文只適用於快速公路，漏了《高速公路及快速公路交通管制規則》第 20 條第 2 項…"
    },
    {
     "id": "X1-3",
     "seat": "X1",
     "on": "C1",
     "text": "「內容與騎機車開大燈有關」把原訊息擴大成任何涉及機車頭燈的法案，連燈具設備或特定道路管制的修法也可能算進去。建議改成「立法院三讀通過一項要求騎機車一律開大燈的法案」…"
    },
    {
     "id": "X1-4",
     "seat": "X1",
     "on": "C4",
     "text": "原文寫「以後」，沒有交代哪一天開始適用。C4 加入「已經生效，現在就適用」，把可能的讀者解讀寫成原訊息的主張。建議刪除這條隱含命題，由 C2 查核原文所稱將來一律開燈的義務。"
    },
    {
     "id": "X1-5",
     "seat": "X1",
     "on": "C5",
     "text": "正方主要靠民間整理的會議資料推定 2026 年 11 月 19 日沒有院會。立法院的一手議程可直接核對，第 7 次院會排在 11 月 13 日、17 日…"
    },
    {
     "id": "X1-6",
     "seat": "X1",
     "on": "手法標記",
     "text": "建議移除「舊聞新炒」標記。特徵 a 成立，原文只寫「昨天」，但這只是線索。特徵 b 的資料查的是 2017 年元旦起汽機車白天開燈的傳言…"
    },
    {
     "id": "X1-7",
     "seat": "X1",
     "on": "溯源",
     "text": "兩則 Cofacts 紀錄的繁體中文版可讀到回報內容、首次回報的相對時間、標籤及查核回應。溯源可以補上這些資料，並註明它們是相近訊息的回報紀錄，無法用來確定本次訊息的首發時間。"
    }
   ],
   "raw": {
    "file": "opponent-X1.json",
    "href": "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/20261120-1441-機車大燈罰三千/opponent-X1.json",
    "total": 98,
    "lines": [
     "{",
     "  \"seat\": \"X1\",",
     "  \"lens\": \"external\",",
     "  \"engine\": \"codex\",",
     "  \"searches_run\": 30,",
     "  \"attacks\": [",
     "    {",
     "      \"id\": \"X1-1\",",
     "      \"claim_id\": \"C3\",",
     "      \"target\": \"evidence\",",
     "      \"argument\": \"裁罰基準表確實列有大型重型機車行駛快速公路未開頭燈、期限內繳納或到案時罰 3,000 元的情形，適用《道路交通管理處罰條例》第 33 條第 1 項…",
     "      \"evidence\": [",
     "        {",
     "          \"url\": \"https://ou3.npa.gov.tw/law/Law/GetFile/1KWEDVT\",",
     "          \"excerpt\": \"大型重型機車行駛高速、快速公路，未開亮頭燈 | 第三十三條第一項第六款 | 三〇〇〇<br>｜<br>六〇〇〇 | 空白 | 三〇〇〇 | …",
     "        },"
    ]
   }
  },
  {
   "id": "rebuttal",
   "name": "正方答辯",
   "file": "rebuttal.json",
   "does": "每一條質疑都要回應：接受，或是拿出證據反駁。",
   "summary": "11 條質疑：接受 8 條，反駁 3 條",
   "kind": "rulings",
   "rows": [
    {
     "id": "A-1",
     "yes": true,
     "word": "接受",
     "text": "接受。已打開兩條條文核對，反方引文和現行條文一致。C2 的理由更正兩處：一、全天開亮頭燈不只限快速公路：高速公路及快速公路交通管制規則第20條第1項第3款適用大型重型機車行駛快速公路…"
    },
    {
     "id": "C-1",
     "yes": true,
     "word": "接受",
     "text": "接受，TW-T04 應拿掉。已打開風傳媒報導和交通部105年12月27日說明核對：當時的傳言是「明年元旦起」汽機車白天沒開大燈要罰，機車600元、汽車1200元…"
    },
    {
     "id": "C-2",
     "yes": true,
     "word": "接受",
     "text": "接受措辭修正，不併回 C2。原文是「三讀通過，以後……一律要」，沒有用「已經生效」這個說法；C4 的改寫應改成原文撐得住的寫法，例如「三讀通過之後…"
    },
    {
     "id": "C-3",
     "yes": true,
     "word": "接受",
     "text": "接受，C4 拿掉 legal_stage_confusion。已打開 CS3 核對：這件排入院會的修正草案（和 S9 是同一案）案由談的是微型電動二輪車的管理…"
    },
    {
     "id": "X1-1",
     "yes": true,
     "word": "接受",
     "text": "接受，C3 的理由要更正，判定維持「錯誤」。已核對道路交通管理處罰條例第33條：汽車（依道路交通安全規則第2條包括機車）在高速公路、快速公路不依規定使用燈光…"
    },
    {
     "id": "X1-2",
     "yes": true,
     "word": "接受",
     "text": "接受，和 A-1 第一點相同。已核對第20條：第1項第3款規定大型重型機車行駛快速公路「全天開亮頭燈」，第2項規定550立方公分以上大型重型機車行駛高速公路「除前項規定外」另守三款…"
    },
    {
     "id": "X1-3",
     "yes": false,
     "word": "反駁",
     "text": "不接受。C1 查的是「有沒有這次三讀」，「一律要開」的內容由 C2 查；照反方建議把「一律」寫進 C1，兩條會重疊，C1 也會變成因為內容細節、而不是三讀本身被判錯…"
    },
    {
     "id": "X1-4",
     "yes": false,
     "word": "反駁",
     "text": "不接受刪除，但措辭已在 C-2 接受修正。共同規則要求三讀和施行分開判斷；「三讀通過，以後一律要、沒開罰三千，快轉給家人」沒有寫施行日期，讀者會理解成三讀後就適用…"
    },
    {
     "id": "X1-5",
     "yes": true,
     "word": "接受",
     "text": "接受。已打開三個立法院議事暨公報資訊網頁面核對：第11屆第6會期第7次會議是115年11月13日、17日，第8次會議是11月20日、12月1日…"
    },
    {
     "id": "X1-6",
     "yes": true,
     "word": "接受",
     "text": "接受，理由同 C-1：TW-T04 拿掉。已打開中央社2016年12月27日報導核對，當時的傳言是106年1月1日後白天不開亮頭燈要罰款，沒有提到立法院三讀，也沒有三千元…"
    },
    {
     "id": "X1-7",
     "yes": false,
     "word": "反駁",
     "text": "無法核對，暫不接受。這次打開 zh.cofacts.tw、cofacts.tw、en.cofacts.tw 的這兩則頁面，都回傳 HTTP 403，讀不到回報時間、標籤和回應內容…"
    }
   ],
   "raw": {
    "file": "rebuttal.json",
    "href": "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/20261120-1441-機車大燈罰三千/rebuttal.json",
    "total": 146,
    "lines": [
     "{",
     "  \"responses\": [",
     "    {",
     "      \"attack_id\": \"A-1\",",
     "      \"accept\": true,",
     "      \"response\": \"接受。已打開兩條條文核對，反方引文和現行條文一致。C2 的理由更正兩處：一、全天開亮頭燈不只限快速公路：高速公路及快速公路交通管制規則第20條第1…",
     "      \"evidence\": [",
     "        {",
     "          \"url\": \"https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=K0040019&flno=20\",",
     "          \"excerpt\": \"汽缸總排氣量五百五十立方公分以上之大型重型機車行駛於高速公路，除前項規定外，並應遵守下列規定\"",
     "        },",
     "        {",
     "          \"url\": \"https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=K0040019&flno=20\",",
     "          \"excerpt\": \"全天開亮頭燈。\"",
     "        },",
     "        {"
    ]
   }
  },
  {
   "id": "judgment",
   "name": "裁判",
   "file": "judgment.json",
   "does": "一個沒有參與辯論的 AI 逐條裁決。判質疑成立時，要列出自己實際打開核對過的網址。",
   "summary": "質疑成立 8 條，不成立 3 條；來源增加到 30 筆",
   "kind": "rulings",
   "rows": [
    {
     "id": "A-1",
     "yes": true,
     "word": "成立",
     "text": "成立，判定不變。高速公路及快速公路交通管制規則第20條第1項第3款規定大型重型機車行駛快速公路要全天開亮頭燈…"
    },
    {
     "id": "C-1",
     "yes": true,
     "word": "成立",
     "text": "成立，「舊聞新炒」不列為已辨識的手法。2016年12月的風傳媒報導和交通部說明，處理的是「2017年元旦起汽機車白天沒開大燈要罰，機車600元、汽車1200元」的傳言…"
    },
    {
     "id": "C-2",
     "yes": true,
     "word": "成立",
     "text": "成立，判定不變。原文是「三讀通過，以後騎機車一律要開大燈」，沒有說規定「已經生效」；隱含命題寫成「已經生效，現在就適用」比原文強，正方也同意修正…"
    },
    {
     "id": "C-3",
     "yes": true,
     "word": "成立",
     "text": "成立，拿掉「法案階段混淆」的標註，判定不變。立法院紀錄裡查不到機車開大燈的提案、草案或三讀，沒有一件實際存在的法案被講錯進度…"
    },
    {
     "id": "X1-1",
     "yes": true,
     "word": "成立",
     "text": "成立，理由更正，判定不變。道路交通管理處罰條例第33條第1項第6款規定，汽車（包括機車）在高速公路、快速公路不依規定使用燈光，處3,000元以上6,000元以下罰鍰…"
    },
    {
     "id": "X1-2",
     "yes": true,
     "word": "成立",
     "text": "成立，判定不變。高速公路及快速公路交通管制規則第20條第2項規定，550立方公分以上大型重型機車行駛高速公路「除前項規定外」另須遵守三款，所以第1項的全天開亮頭燈在高速公路同樣適用…"
    },
    {
     "id": "X1-3",
     "yes": false,
     "word": "不成立",
     "text": "不成立。這一條查的是「有沒有這次三讀」，「一律要開」的內容由另一條查；把「一律」寫進來，兩條會重疊。現行寫法比原文寬，對訊息較有利，沒有加重原文的說法…"
    },
    {
     "id": "X1-4",
     "yes": false,
     "word": "不成立",
     "text": "不成立。改寫比原文強這一點是對的，已經修正成「三讀通過之後就開始適用」；但刪掉整條沒有必要。三讀、公布、施行是不同階段…"
    },
    {
     "id": "X1-5",
     "yes": true,
     "word": "成立",
     "text": "成立，判定不變，證據改以立法院第一手紀錄為主。立法院議事暨公報資訊網顯示：第11屆第6會期第7次會議是115年11月13日（五）、17日（二）…"
    },
    {
     "id": "X1-6",
     "yes": true,
     "word": "成立",
     "text": "成立，「舊聞新炒」不列為已辨識的手法。中央社2016年12月27日報導的傳言是「106年1月1日後，白天不開亮頭燈要罰款」，沒有提到立法院三讀或三千元，和這一則的說法不同…"
    },
    {
     "id": "X1-7",
     "yes": false,
     "word": "不成立",
     "text": "不成立。這次打開 Cofacts 這兩則頁面（zh.cofacts.tw、cofacts.tw、en.cofacts.tw）都回傳 HTTP 403，讀不到回報時間、標籤和回應內容…"
    }
   ],
   "raw": {
    "file": "judgment.json",
    "href": "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/20261120-1441-機車大燈罰三千/judgment.json",
    "total": 694,
    "lines": [
     "{",
     "  \"rulings\": [",
     "    {",
     "      \"attack_id\": \"A-1\",",
     "      \"upheld\": true,",
     "      \"reason\": \"成立，判定不變。高速公路及快速公路交通管制規則第20條第1項第3款規定大型重型機車行駛快速公路要全天開亮頭燈，第2項規定550立方公分以上大型重型機車…",
     "      \"verified_urls\": [",
     "        \"https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=K0040019&flno=20\",",
     "        \"https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=K0040013&flno=109\"",
     "      ]",
     "    },",
     "    {",
     "      \"attack_id\": \"C-1\",",
     "      \"upheld\": true,",
     "      \"reason\": \"成立，「舊聞新炒」不列為已辨識的手法。2016年12月的風傳媒報導和交通部說明，處理的是「2017年元旦起汽機車白天沒開大燈要罰，機車600元、汽車1…",
     "      \"verified_urls\": ["
    ]
   }
  },
  {
   "id": "review",
   "name": "覆核",
   "file": "review-*.json",
   "does": "提出質疑的那幾席回頭檢查裁判改過的地方。沒有通過的，那一條改列「無法證實」。",
   "summary": "回頭檢查了 5 處，全部通過",
   "kind": "rulings",
   "rows": [
    {
     "id": "A → C2",
     "yes": true,
     "word": "通過",
     "text": "修改後的理由已照條文更正，判「錯誤」有第一手法條支持。重新查核全國法規資料庫確認：道路交通安全規則第109條第1項第1至3款規定夜間、行經隧道與調撥車道、遇濃霧雨雪天色昏暗或視線不清時…"
    },
    {
     "id": "C → C4",
     "yes": true,
     "word": "通過",
     "text": "修改後的判定已處理兩項質疑：這一條改照「三讀通過之後就開始適用」判斷，不再讀成「已經生效」；「法案階段混淆」的標註也已拿掉…"
    },
    {
     "id": "X1 → C2",
     "yes": true,
     "word": "通過",
     "text": "維持「錯誤」合理。修正後已納入大型重型機車在快速公路的全天開燈義務，以及汽缸總排氣量達550立方公分者在高速公路適用同一義務…"
    },
    {
     "id": "X1 → C3",
     "yes": true,
     "word": "通過",
     "text": "維持「錯誤」合理。修正後已說明，大型重型機車在高速公路或快速公路違規未開頭燈，法定罰鍰為3,000至6,000元…"
    },
    {
     "id": "X1 → C5",
     "yes": true,
     "word": "通過",
     "text": "維持「錯誤」合理。裁判已將立法院第一手會議紀錄列為主要證據。第7次院會列有「115年11月17日 (二) 09:00-18:00」…"
    }
   ],
   "raw": {
    "file": "review-X1.json",
    "href": "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/20261120-1441-機車大燈罰三千/review-X1.json",
    "total": 20,
    "lines": [
     "{",
     "  \"seat\": \"X1\",",
     "  \"reviews\": [",
     "    {",
     "      \"claim_id\": \"C2\",",
     "      \"pass\": true,",
     "      \"reason\": \"維持「錯誤」合理。修正後已納入大型重型機車在快速公路的全天開燈義務，以及汽缸總排氣量達550立方公分者在高速公路適用同一義務。第20條寫明「全天開亮頭…",
     "    },",
     "    {",
     "      \"claim_id\": \"C3\",",
     "      \"pass\": true,",
     "      \"reason\": \"維持「錯誤」合理。修正後已說明，大型重型機車在高速公路或快速公路違規未開頭燈，法定罰鍰為3,000至6,000元。覆核時直接查到裁罰基準表，該項期限內…",
     "    },",
     "    {",
     "      \"claim_id\": \"C5\",",
     "      \"pass\": true,"
    ]
   }
  },
  {
   "id": "score",
   "name": "程式算分",
   "file": "score.json、report.md",
   "does": "可信度、信心度、能不能公開引用，都由程式照固定規則算，不是 AI 給的。",
   "summary": "同一份判定，每次算出來都是同樣的分數",
   "kind": "report",
   "result": "不符",
   "credibility": 0,
   "confidence": 100,
   "level": "高",
   "publishable": true,
   "rows": [
    {
     "id": "C1",
     "text": "立法院三讀通過一項法案，內容與騎機車開大燈有關。",
     "label": "錯誤",
     "revised": false,
     "reviewed": "不需覆核",
     "scored": true
    },
    {
     "id": "C2",
     "text": "往後騎機車一律要開大燈。",
     "label": "錯誤",
     "revised": false,
     "reviewed": "覆核通過",
     "scored": true
    },
    {
     "id": "C3",
     "text": "騎機車沒開大燈會被罰三千元。",
     "label": "錯誤",
     "revised": false,
     "reviewed": "覆核通過",
     "scored": true
    },
    {
     "id": "C4",
     "text": "騎機車一律要開大燈、沒開要罰的規定已經生效，現在就適用。",
     "label": "錯誤",
     "revised": true,
     "reviewed": "覆核通過",
     "scored": true
    },
    {
     "id": "C5",
     "text": "這次三讀是查核日期的前一天（2026 年 11 月 19 日）發生的。",
     "label": "錯誤",
     "revised": false,
     "reviewed": "覆核通過",
     "scored": true
    },
    {
     "id": "C6",
     "text": "呼籲讀者把這則訊息轉傳給家人。",
     "label": "非事實陳述",
     "revised": false,
     "reviewed": "不需覆核",
     "scored": false
    }
   ],
   "raw": {
    "file": "score.json",
    "href": "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/20261120-1441-機車大燈罰三千/score.json",
    "total": 63,
    "lines": [
     "{",
     "  \"credibility\": {",
     "    \"score\": 0,",
     "    \"raw\": 0.0,",
     "    \"main_claims\": [",
     "      \"C2\"",
     "    ],",
     "    \"main_accuracy\": 0.0,",
     "    \"overall_accuracy\": 0.0,",
     "    \"capped\": false,",
     "    \"context_flags\": [],",
     "    \"show_on_spectrum\": true",
     "  },",
     "  \"result\": \"不符\",",
     "  \"result_reason\": null,",
     "  \"confidence\": {"
    ]
   }
  }
 ]
};
