// The one line on the opening screen: the command, and after it a question typed the way a person types it.
// When a question has stood for a moment, esc clears it and the next is typed.
(function () {
  'use strict';
  var line = document.querySelector('.prompt');
  if (!line) return;
  var slot = line.querySelector('.q'), key = line.querySelector('.esc');
  // Messages that really went round, from the twelve cases of the final blind batch and the worked example.
  // Their targets take turns: the governing party, the opposition parties, public agencies.
  var QUESTIONS = [
    '騎機車一律要開大燈，沒開罰三千？',
    '軍購清單只要 3000 億，預算卻編了 1.25 兆？',
    '邱鎮軍一選上立委，就赴中見中共政委？',
    '黃國昌提案刪了 41 億，租金補貼被砍光光？',
    '海鯤艦艙內進水、主機故障動不了？',
    '輝達留在北士科，跟北市府沒有關係？',
    '共諜案被告的刑度，二審真的大幅減輕？',
    '只剩八位大法官，修法卻規定十人才能開庭？',
    '高雄敬老卡 1 月底前要過卡，才有 1200 元？',
    '警消退休金從 80% 起算，每年再調升 1.25%？',
    '民生電價喊漲在即，形同剝人民多層皮？',
    '運動幣登記到 2 月 8 日，現在還來得及嗎？',
    '國軍 4 月起加薪，基層最多月增 1.2 萬？'
  ];
  var still = new URLSearchParams(location.search).has('still') || matchMedia('(prefers-reduced-motion: reduce)').matches;
  // On a narrow screen a question takes two lines, and the turn comes after its first comma, not wherever
  // the edge of the screen happens to fall. (The stylesheet shows this break only on narrow screens.)
  var turn = document.createElement('br');
  turn.className = 'turn';
  function write(text, n) {
    var cut = text.search(/[，、]/) + 1;
    if (!cut || n <= cut) { slot.textContent = text.slice(0, n); return; }
    slot.replaceChildren(text.slice(0, cut), turn, text.slice(cut, n));
  }
  if (still) { write(QUESTIONS[0], QUESTIONS[0].length); return; }

  var index = 0;
  function wait(ms) { return new Promise(function (done) { setTimeout(done, ms); }); }
  function pace(ch) {                       // people slow down at punctuation and speed through digits
    if ('，、'.indexOf(ch) >= 0) return 260 + Math.random() * 160;
    if ('？。'.indexOf(ch) >= 0) return 120;
    if (/[0-9A-Za-z .%]/.test(ch)) return 38 + Math.random() * 40;
    return 62 + Math.random() * 78;
  }
  async function run() {
    for (;;) {
      var text = QUESTIONS[index % QUESTIONS.length];
      line.classList.add('typing');
      for (var i = 1; i <= text.length; i++) {
        write(text, i);
        await wait(pace(text[i - 1]));
      }
      line.classList.remove('typing');
      await wait(2600);
      key.classList.add('down');          // esc
      await wait(150);
      slot.textContent = '';
      await wait(240);
      key.classList.remove('down');
      await wait(620);
      index++;
    }
  }
  run();
})();
