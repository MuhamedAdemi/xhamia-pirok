// Pagesa e antarësisë: shuma e dytë (p.sh. 150 € + 3.700 den) dhe "Shuma ndryshon sipas viteve".
// Përdoret te forma e plotë dhe te dritarja ⊕. Elementet gjenden sipas emrit brenda formës:
//   viti, viti_deri, shuma_hyrese, monedha, shuma_2, monedha_2, vitet_shumat (hidden)
//   [data-vs] — mbajtësi me data-kategorite='{"kufijte": [...], "kurset": {...}}'
window.VitetShumat = function (forma) {
  var mbajtesi = forma.querySelector('[data-vs]');
  if (!mbajtesi) return null;
  var te_dhenat = JSON.parse(mbajtesi.dataset.kategorite || '{"kufijte": [], "kurset": {}}');
  var kufijte = te_dhenat.kufijte, kurset = te_dhenat.kurset;
  var SIMBOLI = { MKD: 'den', EUR: '€', CHF: 'CHF', USD: '$' };
  var ndarje = mbajtesi.querySelector('[data-vs-ndarje]');
  var tabela = mbajtesi.querySelector('[data-vs-tabela]');
  var permbledhja = mbajtesi.querySelector('[data-vs-kategoria]');
  var fsheh = forma.elements['vitet_shumat'];
  var vlerat = {};        // {viti: {monedha: 'tekst'}} — çka ka shkruar përdoruesi
  var edituar = false;    // pa shkruar asgjë → ndahet njëlloj vetvetiu

  function el(emri) { return forma.elements[emri]; }
  function vlera(emri) {
    var e = el(emri);
    if (!e) return '';
    if (e.length !== undefined && e.tagName !== 'SELECT') {   // radio
      for (var i = 0; i < e.length; i++) if (e[i].checked) return e[i].value;
      return '';
    }
    return e.value;
  }
  function nr(t) { var n = parseFloat(String(t || '').replace(',', '.')); return isNaN(n) ? 0 : n; }
  function fmt(n, m) {
    var d = (m === 'MKD' || Math.round(n) === n) ? 0 : 2;
    return n.toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d }) + ' ' + SIMBOLI[m];
  }

  function vitet() {
    var a = parseInt(vlera('viti')), b = parseInt(vlera('viti_deri')) || a;
    if (!a || b < a || b - a > 49) return [];
    var l = [];
    for (var v = a; v <= b; v++) l.push(v);
    return l;
  }
  function shumat() {   // [[monedha, shuma], ...]
    var l = [[vlera('monedha') || 'MKD', nr(vlera('shuma_hyrese'))]];
    if (nr(vlera('shuma_2')) > 0) l.push([vlera('monedha_2') || 'MKD', nr(vlera('shuma_2'))]);
    return l;
  }

  function kategoria(pjeset) {   // {monedha: shuma} → {nr, emri} | null
    var eur = 0, mkd = 0, kEur = +kurset.EUR || 61.5;
    Object.keys(pjeset).forEach(function (m) {
      var s = pjeset[m] || 0;
      if (m === 'MKD') mkd += s; else if (m === 'EUR') eur += s; else eur += s * (+kurset[m] || kEur) / kEur;
    });
    if (!kufijte.length || (eur <= 0 && mkd <= 0)) return null;
    for (var i = 0; i < kufijte.length; i++) {
      if (eur / +kufijte[i].eur + mkd / +kufijte[i].mkd >= 0.99999) return kufijte[i];
    }
    return kufijte[kufijte.length - 1];
  }
  function etiketa(k) { return k ? 'Kategoria ' + k.nr + (k.emri ? ' · ' + k.emri : '') : ''; }

  function ndajNjelloj() {
    var vv = vitet(), ss = shumat();
    vlerat = {};
    vv.forEach(function (v) { vlerat[v] = {}; });
    ss.forEach(function (p) {
      var m = p[0], total = p[1], d = m === 'MKD' ? 1 : 100;
      var pjesa = Math.floor(total * d / vv.length) / d, mbetja = total;
      vv.forEach(function (v, i) {
        var s = i === vv.length - 1 ? Math.round(mbetja * d) / d : pjesa;
        mbetja -= s;
        vlerat[v][m] = String(s).replace('.', ',');
      });
    });
  }

  function vizato() {
    var vv = vitet(), ss = shumat();
    var aktiv = ndarje && ndarje.checked && vv.length > 0;
    tabela.hidden = !aktiv;
    if (aktiv && !edituar) ndajNjelloj();
    if (!aktiv) {
      fsheh.value = '';
      permbledhja.classList.remove('vs-gabim');
      // pa ndarje: e njëjta shumë për çdo vit — kategoria e vitit të fundit
      var p = {};
      ss.forEach(function (x) { p[x[0]] = x[1] / (vv.length || 1); });
      var k = kategoria(p);
      permbledhja.textContent = k && vv.length ? etiketa(k) + ' (' + (vv.length > 1 ? 'për çdo vit' : 'për ' + vv[0]) + ')' : '';
      return;
    }
    var html = '<table class="vs-tabela"><thead><tr><th>Viti</th>';
    ss.forEach(function (p) { html += '<th>' + SIMBOLI[p[0]] + '</th>'; });
    html += '<th>Kategoria</th></tr></thead><tbody>';
    var totalet = ss.map(function () { return 0; });
    vv.forEach(function (v) {
      var rreshti = vlerat[v] || {}, pjeset = {};
      html += '<tr><td>' + v + '</td>';
      ss.forEach(function (p, i) {
        var t = rreshti[p[0]] || '';
        totalet[i] += nr(t);
        pjeset[p[0]] = nr(t);
        html += '<td><input inputmode="decimal" data-vs-viti="' + v + '" data-vs-monedha="' + p[0] + '" value="' + String(t).replace(/"/g, '&quot;') + '"></td>';
      });
      html += '<td class="vs-kat">' + (etiketa(kategoria(pjeset)) || '—') + '</td></tr>';
    });
    html += '</tbody><tfoot><tr><td>Totali</td>';
    var ok = true;
    ss.forEach(function (p, i) {
      var diff = Math.round((p[1] - totalet[i]) * 100) / 100;
      if (diff !== 0) ok = false;
      html += '<td>' + fmt(totalet[i], p[0]) + (diff !== 0 ? '<br><span class="vs-gabim">' + (diff > 0 ? 'mungojnë ' : 'tepër ') + fmt(Math.abs(diff), p[0]) + '</span>' : ' ✓') + '</td>';
    });
    html += '<td><button type="button" class="btn-dytësor btn-sm" data-vs-ndaj>Ndaj njëlloj</button></td></tr></tfoot></table>';
    tabela.innerHTML = html;
    var vitiFundit = vv[vv.length - 1], kf = {};
    ss.forEach(function (p) { kf[p[0]] = nr((vlerat[vitiFundit] || {})[p[0]]); });
    permbledhja.textContent = etiketa(kategoria(kf)) ? etiketa(kategoria(kf)) + ' (sipas vitit ' + vitiFundit + ')' : '';
    permbledhja.classList.toggle('vs-gabim', !ok);
    var json = {};
    vv.forEach(function (v) { json[v] = {}; ss.forEach(function (p) { json[v][p[0]] = String((vlerat[v] || {})[p[0]] || '').replace(',', '.'); }); });
    fsheh.value = JSON.stringify(json);
  }

  tabela.addEventListener('input', function (e) {
    var i = e.target.closest('[data-vs-viti]');
    if (!i) return;
    edituar = true;
    vlerat[i.dataset.vsViti] = vlerat[i.dataset.vsViti] || {};
    vlerat[i.dataset.vsViti][i.dataset.vsMonedha] = i.value;
    // rifreskon vetëm totalet/kategoritë, pa e humbur kursorin
    var poz = i.selectionStart, viti = i.dataset.vsViti, m = i.dataset.vsMonedha;
    vizato();
    var iRi = tabela.querySelector('[data-vs-viti="' + viti + '"][data-vs-monedha="' + m + '"]');
    if (iRi) { iRi.focus(); try { iRi.setSelectionRange(poz, poz); } catch (x) {} }
  });
  tabela.addEventListener('click', function (e) {
    if (e.target.closest('[data-vs-ndaj]')) { edituar = false; vizato(); }
  });
  ['viti', 'viti_deri', 'shuma_hyrese', 'shuma_2', 'monedha', 'monedha_2'].forEach(function (emri) {
    var e = el(emri);
    if (!e) return;
    var lista = (e.length !== undefined && e.tagName !== 'SELECT') ? Array.prototype.slice.call(e) : [e];
    // ndryshimi i viteve ose i monedhave e rindan shumën; ndryshimi i shumës i ruan vlerat e shkruara
    var rindaj = emri !== 'shuma_hyrese' && emri !== 'shuma_2';
    lista.forEach(function (x) {
      ['input', 'change'].forEach(function (ngjarja) {
        x.addEventListener(ngjarja, function () { if (rindaj) edituar = false; vizato(); });
      });
    });
  });
  if (ndarje) ndarje.addEventListener('change', function () { edituar = false; vizato(); });

  // Pas gabimit të formës: rikthe ndarjen që u dërgua
  if (fsheh.value) {
    try {
      var vjetra = JSON.parse(fsheh.value);
      Object.keys(vjetra).forEach(function (v) { vlerat[v] = {}; Object.keys(vjetra[v]).forEach(function (m) { vlerat[v][m] = String(vjetra[v][m]).replace('.', ','); }); });
      edituar = true;
      if (ndarje) ndarje.checked = true;
    } catch (x) {}
  }
  vizato();
  return { rifresko: function () { edituar = false; vizato(); }, pastro: function () { vlerat = {}; edituar = false; if (ndarje) ndarje.checked = false; vizato(); } };
};
