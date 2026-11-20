// The front page's working parts: the window that replays a real run, the install tabs, and the copy buttons.
(function () {
  'use strict';
  var query = new URLSearchParams(location.search);
  var calm = matchMedia('(prefers-reduced-motion: reduce)').matches || query.has('still');

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function put(parent) {
    for (var i = 1; i < arguments.length; i++) if (arguments[i]) parent.appendChild(arguments[i]);
    return parent;
  }
  function icon(name) {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'), use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    svg.setAttribute('width', 16); svg.setAttribute('height', 16);
    use.setAttribute('href', '#' + name);
    svg.appendChild(use);
    return svg;
  }
  function wait(ms) { return new Promise(function (done) { setTimeout(done, ms); }); }

  // ---- one step of the run, drawn from the file it left ----------------------------------------------
  var ROWS = {
    claims: function (r) {
      return put(el('li', 'r-ask'), el('code', '', r.id), put(el('p', '', '「' + r.quote + '」'), el('small', '', r.text)),
        el('span', 'tag', r.type), el('span', 'num', '重要性 ' + r.importance));
    },
    notes: function (r) {
      return put(el('li', 'r-note'), el('span', 'tag', r.tag), el('time', '', r.when), el('p', '', r.text));
    },
    sources: function (r) {
      return put(el('li', 'r-src'), el('code', '', r.id), put(el('p', '', r.title), el('small', '', r.by)), el('span', 'tag', r.tier));
    },
    attacks: function (r) {
      return put(el('li', 'r-atk'), el('code', '', r.id), el('span', 'tag', r.on), el('p', '', r.text));
    },
    rulings: function (r) {
      return put(el('li', 'r-rule'), el('code', '', r.id), el('span', r.yes ? 'mark' : 'mark no', r.word), el('p', '', r.text));
    },
    report: function (r) {
      return put(el('li', r.scored ? 'r-claim' : 'r-claim off'), el('code', '', r.id),
        put(el('p', '', r.text), r.revised ? el('small', '', '問法在辯論中修正過') : null),
        el('span', r.scored ? 'mark bad' : 'mark no', r.label), el('span', 'num', r.reviewed));
    }
  };
  function tidy(step) {                        // the file's contents, laid out to be read
    var body = el('div');
    if (step.kind === 'message') return put(body, el('blockquote', 'msg', step.text));
    if (step.kind === 'attacks') {
      var seats = el('div', 'seats');
      step.seats.forEach(function (s) {
        put(seats, put(el('div'), el('b', '', s.role), el('span', '', s.engine + '・搜尋 ' + s.searches + ' 次・質疑 ' + s.attacks + ' 條')));
      });
      put(body, seats);
    }
    if (step.kind === 'report') {
      var stats = el('dl');
      put(stats, put(el('div'), el('dt', '', '可信度'), el('dd', '', String(step.credibility))),
        put(el('div'), el('dt', '', '信心度'), put(el('dd', '', String(step.confidence)), el('small', '', step.level))),
        put(el('div'), el('dt', '', '公開引用'), el('dd', 'word', step.publishable ? '可公開' : '不可公開')));
      var scale = put(el('p', step.credibility === null ? 'scale none' : 'scale'), el('span', '', '錯誤'), el('i'), el('span', '', '正確'));
      scale.style.setProperty('--at', step.credibility || 0);
      put(body, put(el('div', 'verdict'), el('p', 'verdict-word', step.result), stats, scale));
    }
    var list = el('ul', 'rows');
    step.rows.forEach(function (r) { put(list, ROWS[step.kind](r)); });
    if (step.more) put(list, put(el('li'), el('span', 'more', '還有 ' + step.more + ' 筆，都在 ' + step.file)));
    return put(body, list);
  }
  function untouched(step) {                   // the top of the file itself
    var link = put(el('a', 'link', '在 GitHub 打開完整檔案'), icon('i-out'));
    link.href = step.raw.href;
    return put(el('div', 'raw'), el('pre', '', step.raw.lines.join('\n')),
      put(el('p'), el('span', '', step.raw.file + ' 的前 ' + step.raw.lines.length + ' 行，全部 ' + step.raw.total + ' 行'), link));
  }
  function view(step) {
    var pane = el('div', 'pane'), body = tidy(step), toggle = el('button', 'pane-raw', '看原始檔');
    toggle.type = 'button';
    toggle.setAttribute('aria-pressed', 'false');
    toggle.addEventListener('click', function () {
      var raw = toggle.getAttribute('aria-pressed') !== 'true';
      toggle.setAttribute('aria-pressed', raw);
      toggle.textContent = raw ? '看整理過的' : '看原始檔';
      var next = raw ? untouched(step) : tidy(step);
      pane.replaceChild(next, body);
      body = next;
    });
    return put(pane, put(el('header'), el('h2', '', step.name), toggle, el('p', '', step.does), el('p', 'sum', step.summary)), body);
  }

  // ---- the window: it plays the run once, then every step can be opened ------------------------------
  function run(root, data) {
    var buttons = Array.prototype.slice.call(root.querySelectorAll('.run-steps button'));
    var pane = root.querySelector('.run-pane'), prompt = root.querySelector('.run-prompt');
    var line = root.querySelector('.run-msg'), again = root.querySelector('.run-again');
    var steps = buttons.map(function (b) { return data.steps.filter(function (s) { return s.id === b.dataset.step; })[0]; });
    var message = line.textContent, turn = 0;

    function mark(i) { buttons.forEach(function (b, k) { if (k === i) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); }); }
    function open(i) {
      mark(i);
      pane.replaceChildren(view(steps[i]));
      pane.scrollTop = 0;
    }
    function settle(i) {                       // the whole run is on the table; show step i
      turn++;
      buttons.forEach(function (b) { b.dataset.state = 'done'; });
      line.textContent = message;
      line.classList.remove('typing');
      prompt.style.setProperty('--playing', 0);
      again.hidden = calm;
      open(i);
    }
    // Playing: the message is typed, then each step reports in one line as its file lands. The whole run
    // took 48 minutes; this takes about nine seconds and ends on the result.
    async function play() {
      var mine = ++turn, i, n, log = el('ol', 'log');
      again.hidden = true;
      buttons.forEach(function (b) { b.dataset.state = 'todo'; b.removeAttribute('aria-current'); });
      pane.replaceChildren(put(el('div', 'pane'), log));
      prompt.style.setProperty('--done', 0);
      prompt.style.setProperty('--playing', 1);
      line.classList.add('typing');
      for (n = 1; n <= message.length; n++) {
        if (mine !== turn) return;
        line.textContent = message.slice(0, n);
        await wait('，！。'.indexOf(message[n - 1]) >= 0 ? 150 : 22);
      }
      await wait(380);
      line.classList.remove('typing');
      for (i = 0; i < steps.length; i++) {
        if (mine !== turn) return;
        buttons[i].dataset.state = 'run';
        mark(i);
        await wait(i === 4 ? 620 : 380);
        if (mine !== turn) return;
        buttons[i].dataset.state = 'done';
        put(log, put(el('li'), el('b', '', steps[i].name), el('span', '', steps[i].summary), el('code', '', steps[i].file)));
        prompt.style.setProperty('--done', (i + 1) / steps.length);
        pane.scrollTop = pane.scrollHeight;
        await wait(300);
      }
      await wait(700);
      if (mine !== turn) return;
      prompt.style.setProperty('--playing', 0);
      open(steps.length - 1);
      again.hidden = false;
    }
    buttons.forEach(function (b, i) { b.addEventListener('click', function () { settle(i); }); });
    again.addEventListener('click', play);

    var first = buttons.map(function (b) { return b.dataset.step; }).indexOf(query.get('step'));
    root.dataset.ready = '';
    if (calm || first >= 0 || !('IntersectionObserver' in window)) { settle(first >= 0 ? first : steps.length - 1); return; }
    buttons.forEach(function (b) { b.dataset.state = 'todo'; b.removeAttribute('aria-current'); });
    pane.replaceChildren();
    line.textContent = '';
    var seen = new IntersectionObserver(function (e) {
      if (!e[0].isIntersecting) return;
      seen.disconnect();
      play();
    }, { threshold: 0.3 });
    seen.observe(root);
  }
  if (window.FACTCHECK_RUN && document.getElementById('run')) run(document.getElementById('run'), window.FACTCHECK_RUN);

  // ---- install: two ways in, one shown at a time -----------------------------------------------------
  Array.prototype.forEach.call(document.querySelectorAll('.tabs'), function (bar) {
    var tabs = Array.prototype.slice.call(bar.querySelectorAll('[role="tab"]'));
    function pick(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute('aria-selected', on);
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
      });
      if (focus) tab.focus();
    }
    tabs.forEach(function (tab, i) {
      tab.addEventListener('click', function () { pick(tab); });
      tab.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') pick(tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length], true);
      });
    });
    pick(tabs[0]);
  });
  Array.prototype.forEach.call(document.querySelectorAll('.code'), function (box) {
    if (!navigator.clipboard) return;
    var button = put(el('button', 'copy'), icon('i-copy'), el('span', '', '複製'));
    button.type = 'button';
    button.addEventListener('click', function () {
      var commands = Array.prototype.map.call(box.querySelectorAll('pre span'), function (s) { return s.textContent; });
      navigator.clipboard.writeText(commands.join('\n')).then(function () {
        button.replaceChildren(icon('i-done'), el('span', '', '已複製'));
        setTimeout(function () { button.replaceChildren(icon('i-copy'), el('span', '', '複製')); }, 1600);
      });
    });
    box.appendChild(button);
  });
})();
