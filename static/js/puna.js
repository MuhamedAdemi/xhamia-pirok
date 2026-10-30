// Kërkim i menjëhershëm në tabelat e "Punës së përditshme" (si te Masjid Manager):
// çdo fjalë e shkruar duhet të gjendet në rresht (pa dallim ë/e, ç/c), shkronjat e kërkuara theksohen.
(function () {
  function normalizo(t) { return (t || '').toLowerCase().replace(/ë/g, 'e').replace(/ç/g, 'c'); }
  function escape(t) { return t.replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }

  function thekso(el, fjalet) {
    if (el.dataset.o === undefined) el.dataset.o = el.textContent;
    var teksti = el.dataset.o, norm = normalizo(teksti);
    if (!fjalet.length) { el.textContent = teksti; return; }
    var shenja = new Array(teksti.length).fill(false);
    fjalet.forEach(function (f) {
      for (var i = norm.indexOf(f); i !== -1; i = norm.indexOf(f, i + f.length)) {
        for (var k = i; k < i + f.length; k++) shenja[k] = true;
      }
    });
    var html = '', hapur = false;
    for (var i = 0; i < teksti.length; i++) {
      if (shenja[i] !== hapur) { html += shenja[i] ? '<mark>' : '</mark>'; hapur = shenja[i]; }
      html += escape(teksti[i]);
    }
    el.innerHTML = html + (hapur ? '</mark>' : '');
  }

  document.querySelectorAll('[data-kerko-tabela]').forEach(function (input) {
    var tabela = document.querySelector(input.dataset.kerkoTabela);
    if (!tabela) return;
    var rreshtat = Array.prototype.slice.call(tabela.tBodies[0].rows).filter(function (r) { return !r.dataset.bosh; });
    rreshtat.forEach(function (r) { r.dataset.t = normalizo(r.textContent); });
    var pastro = document.querySelector('[data-pastro="' + input.id + '"]');

    function filtro() {
      var fjalet = normalizo(input.value).split(/\s+/).filter(Boolean);
      var statusi = tabela.dataset.statusi || '';
      var n = 0;
      rreshtat.forEach(function (r) {
        var ok = fjalet.every(function (f) { return r.dataset.t.indexOf(f) !== -1; })
          && (!statusi || r.dataset.statusi === statusi);
        r.hidden = !ok;
        if (ok) n++;
        r.querySelectorAll('[data-th]').forEach(function (td) { thekso(td, ok ? fjalet : []); });
      });
      document.querySelectorAll('[data-numri="' + tabela.id + '"]').forEach(function (e) { e.textContent = n.toLocaleString('de-DE'); });
      var bosh = tabela.querySelector('[data-asnje]');
      if (bosh) bosh.hidden = n > 0;
      if (pastro) pastro.hidden = !input.value;
    }
    input.addEventListener('input', filtro);
    tabela.addEventListener('filtro', filtro);
    if (pastro) pastro.addEventListener('click', function () { input.value = ''; filtro(); input.focus(); });
    filtro();
  });

  // Butonat Gjitha / Të paguar / Pa paguar
  document.querySelectorAll('[data-segment]').forEach(function (grupi) {
    var tabela = document.querySelector(grupi.dataset.segment);
    grupi.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () {
        grupi.querySelectorAll('button').forEach(function (x) { x.classList.toggle('aktiv', x === b); });
        tabela.dataset.statusi = b.dataset.vlera;
        tabela.dispatchEvent(new Event('filtro'));
      });
    });
  });
})();
