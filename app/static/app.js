(function () {
  var csrf = (document.querySelector('meta[name=csrf-token]') || {}).content;

  // --- aggiornamento automatico dei blocchi [data-refresh], con "pop" sui punteggi cambiati
  function snapshot(root) {
    var m = {};
    root.querySelectorAll('[data-k]').forEach(function (e) { m[e.dataset.k] = e.dataset.v; });
    return m;
  }
  document.querySelectorAll('[data-refresh]').forEach(function (el) {
    var every = parseInt(el.dataset.every || '5000', 10);
    var timer = null, last = el.innerHTML;
    function tick() {
      if (document.hidden) return;
      fetch(el.dataset.refresh, {headers: {'X-Requested-With': 'fetch'}})
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (html) {
          if (html === null || html === last) return;
          var before = snapshot(el);
          last = html;
          el.innerHTML = html;
          el.querySelectorAll('.stagger>*, main>*').forEach(function (n) { n.style.animation = 'none'; });
          el.querySelectorAll('[data-k]').forEach(function (e) {
            if (e.dataset.k in before && before[e.dataset.k] !== e.dataset.v) e.classList.add('bump');
          });
        }).catch(function () {});
    }
    timer = setInterval(tick, every);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) tick(); });
  });

  // --- modulo di iscrizione: aggiungi giocatore
  var add = document.getElementById('addp');
  if (add) add.addEventListener('click', function () {
    var box = document.getElementById('players');
    if (box.children.length >= parseInt(add.dataset.max, 10)) return;
    box.appendChild(box.children[0].cloneNode(true));
    box.lastElementChild.querySelectorAll('input').forEach(function (i) { i.value = ''; });
  });

  // --- pannello contapunti
  var panel = document.getElementById('panel');
  if (!panel) return;
  var id = panel.dataset.id, isBoss = panel.dataset.boss === '1', status = panel.dataset.status;
  var msg = document.getElementById('msg'), state = document.getElementById('state');
  var busy = false;

  function setScore(n, v) {
    var e = document.getElementById('s' + n);
    if (String(e.textContent) !== String(v)) {
      e.textContent = v;
      e.classList.remove('bump'); void e.offsetWidth; e.classList.add('bump');
    }
  }
  function render(d) {
    status = d.status;
    setScore(1, d.score1); setScore(2, d.score2);
    panel.querySelectorAll('.pt').forEach(function (b) { b.disabled = status !== 'live'; });
    document.getElementById('b-start').hidden = status !== 'scheduled';
    document.getElementById('b-finish').hidden = status !== 'live';
    document.getElementById('b-reopen').hidden = !(status === 'finished' && isBoss);
    state.textContent = {scheduled: 'Partita non iniziata',
      live: 'Partita in corso — i punti sono visibili in diretta al pubblico',
      finished: 'Partita conclusa — punti assegnati'}[status];
  }
  function call(action, body) {
    if (busy) return;
    busy = true;
    fetch('/api/match/' + id + '/' + action, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify(body || {})
    }).then(function (r) { return r.json().then(function (d) { return [r.ok, d]; }); })
      .then(function (res) {
        msg.hidden = res[0];
        if (res[0]) render(res[1]); else { msg.textContent = res[1].error || 'Errore'; if (navigator.vibrate) navigator.vibrate([60, 40, 60]); }
      }).catch(function () { msg.hidden = false; msg.textContent = 'Connessione assente: riprova.'; })
      .then(function () { busy = false; });
  }
  panel.querySelectorAll('.pt').forEach(function (b) {
    b.addEventListener('click', function () {
      if (navigator.vibrate) navigator.vibrate(12);
      call('point', {team: +b.dataset.team, delta: +b.dataset.delta});
    });
  });
  document.getElementById('b-start').addEventListener('click', function () { call('start'); });
  document.getElementById('b-finish').addEventListener('click', function () {
    if (confirm('Chiudere la partita e assegnare i punti?')) call('finish');
  });
  document.getElementById('b-reopen').addEventListener('click', function () {
    if (confirm('Riaprire la partita?')) call('reopen');
  });
  setInterval(function () {
    if (busy || document.hidden) return;
    fetch('/api/match/' + id).then(function (r) { return r.json(); }).then(function (d) { if (!busy) render(d); }).catch(function () {});
  }, 3000);
  render({status: status, score1: document.getElementById('s1').textContent, score2: document.getElementById('s2').textContent});
})();
