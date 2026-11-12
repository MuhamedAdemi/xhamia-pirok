// Pagesa e antarësisë: "Shuma ndryshon sipas viteve" dhe shuma në monedhë të dytë (p.sh. 300 € + 5.000 den).
//
// Kur ndarja është e ndezur, çdo vit ka dy kuti: € (ose monedha e pagesës: CHF/$) dhe den. Vitet mbushen
// vetvetiu me tarifën (p.sh. 50 € për vitet e kaluara, 70 € për vitin aktual); ju ndryshoni vetëm ato që duhen.
// Totalet e formës (Shuma + Shuma në monedhë tjetër) plotësohen vetë nga shumat e viteve.
//
// Elementet gjenden sipas emrit brenda formës: viti, viti_deri, shuma_hyrese, monedha, shuma_2, monedha_2,
// vitet_shumat (hidden); [data-vs] me data-kategorite='{"kufijte": [...], "kurset": {...}}' dhe data-tarifat.
window.VitetShumat = function (forma) {
  var mbajtesi = forma.querySelector('[data-vs]');
  if (!mbajtesi) return null;
  var te_dhenat = JSON.parse(mbajtesi.dataset.kategorite || '{"kufijte": [], "kurset": {}}');
  var kufijte = te_dhenat.kufijte, kurset = te_dhenat.kurset;
  var tarifat = mbajtesi.dataset.tarifat ? JSON.parse(mbajtesi.dataset.tarifat) : null;
  var SIMBOLI = { MKD: 'den', EUR: '€', CHF: 'CHF', USD: '$' };
  var ndarje = mbajtesi.querySelector('[data-vs-ndarje]');
  var tabela = mbajtesi.querySelector('[data-vs-tabela]');
  var permbledhja = mbajtesi.querySelector('[data-vs-kategoria]');
  var fsheh = forma.elements['vitet_shumat'];
  var vlerat = {};          // {viti: {monedha: 'tekst'}}
  var edituar = false;      // a ka shkruar përdoruesi në tabelë
  var duke_sinkronizuar = false;

  function el(emri) { return forma.elements[emri]; }
  function eshteRadio(e) { return e && e.length !== undefined && e.tagName !== 'SELECT'; }
  function vlera(emri) {
    var e = el(emri);
    if (!e) return '';
    if (eshteRadio(e)) { for (var i = 0; i < e.length; i++) if (e[i].checked) return e[i].value; return ''; }
    return e.value;
  }
  function vendos(emri, v) {
    var e = el(emri);
    if (!e) return;
    if (eshteRadio(e)) {
      for (var i = 0; i < e.length; i++) {
        if (e[i].value === v && !e[i].checked) { e[i].checked = true; e[i].dispatchEvent(new Event('change', { bubbles: true })); }
      }
    } else if (e.value !== v) {
      e.value = v;
      e.dispatchEvent(new Event('input', { bubbles: true }));
      e.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }
  function nr(t) { var n = parseFloat(String(t || '').replace(',', '.')); return isNaN(n) ? 0 : n; }
  function tekst(n) { return n ? String(Math.round(n * 100) / 100).replace('.', ',') : ''; }
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
  // Kolonat e tabelës: monedha "e fortë" (€, ose CHF/$ kur pagesa është në to) dhe denarët.
  // "Euro + Denar" (EUR_MKD) = euro si monedhë kryesore + denarët te kutia shuma_2
  function monedhaKryesore() { var m = vlera('monedha') || 'MKD'; return m === 'EUR_MKD' ? 'EUR' : m; }
  function kolonat() {
    var m1 = monedhaKryesore();
    return [m1 !== 'MKD' ? m1 : 'EUR', 'MKD'];
  }
  function totaletEFormes() {   // {monedha: shuma} siç janë shkruar lart
    var t = {}, m1 = monedhaKryesore();
    if (nr(vlera('shuma_hyrese')) > 0) t[m1] = (t[m1] || 0) + nr(vlera('shuma_hyrese'));
    if (vlera('monedha') === 'EUR_MKD' && nr(vlera('shuma_2')) > 0) t.MKD = (t.MKD || 0) + nr(vlera('shuma_2'));
    return t;
  }

  function kategoria(pjeset) {
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

  // Mbushja fillestare: nga totali i shkruar lart (pjesa në den shkon te viti i fundit), ose nga tarifat.
  function mbush() {
    var vv = vitet(), kk = kolonat(), t = totaletEFormes();
    vlerat = {};
    vv.forEach(function (v) { vlerat[v] = {}; });
    if (!vv.length) return;
    var forte = t[kk[0]] || 0, den = t.MKD || 0;
    if (!forte && !den && tarifat && kk[0] === 'EUR') {
      vv.forEach(function (v) { vlerat[v][kk[0]] = tekst(+(v >= tarifat.viti ? tarifat.aktual : tarifat.kaluara)); });
      return;
    }
    function ndaj(total, monedha, lista) {
      var d = monedha === 'MKD' ? 1 : 100, pjesa = Math.floor(total * d / lista.length) / d, mbetja = total;
      lista.forEach(function (v, i) {
        var s = i === lista.length - 1 ? Math.round(mbetja * d) / d : pjesa;
        mbetja -= s;
        vlerat[v][monedha] = tekst(s);
      });
    }
    if (forte && den && vv.length > 1) {      // p.sh. 300 € + 5000 den për 2020–2026 → € në vitet e para, den në 2026
      ndaj(forte, kk[0], vv.slice(0, -1));
      vlerat[vv[vv.length - 1]].MKD = tekst(den);
    } else {
      if (forte) ndaj(forte, kk[0], vv);
      if (den) ndaj(den, 'MKD', vv);
    }
  }

  // Shumat e viteve → fushat lart (Shuma + Shuma në monedhë tjetër)
  function sinkronizo() {
    var vv = vitet(), kk = kolonat(), forte = 0, den = 0;
    vv.forEach(function (v) { forte += nr((vlerat[v] || {})[kk[0]]); den += nr((vlerat[v] || {}).MKD); });
    forte = Math.round(forte * 100) / 100;
    den = Math.round(den);
    duke_sinkronizuar = true;
    if (forte > 0 && den > 0 && kk[0] === 'EUR') {
      vendos('monedha', 'EUR_MKD');
      vendos('shuma_hyrese', tekst(forte).replace(',', '.'));
      vendos('shuma_2', String(den));
    } else if (forte > 0) {
      vendos('monedha', kk[0]);
      vendos('shuma_hyrese', tekst(forte).replace(',', '.'));
      vendos('shuma_2', '');
    } else {
      vendos('monedha', 'MKD');
      vendos('shuma_hyrese', den > 0 ? String(den) : '');
      vendos('shuma_2', '');
    }
    duke_sinkronizuar = false;
  }

  function vizato() {
    var vv = vitet(), kk = kolonat();
    var aktiv = ndarje && ndarje.checked && vv.length > 0;
    tabela.hidden = !aktiv;
    if (!aktiv) {
      fsheh.value = '';
      var p = {}, t = totaletEFormes();
      Object.keys(t).forEach(function (m) { p[m] = t[m] / (vv.length || 1); });
      var k = kategoria(p);
      permbledhja.textContent = k && vv.length ? etiketa(k) + ' (' + (vv.length > 1 ? 'për çdo vit' : 'për ' + vv[0]) + ')' : '';
      return;
    }
    var html = '<table class="vs-tabela"><thead><tr><th>Viti</th>';
    kk.forEach(function (m) { html += '<th>' + SIMBOLI[m] + '</th>'; });
    html += '<th>Kategoria</th></tr></thead><tbody>';
    var totalet = [0, 0];
    vv.forEach(function (v) {
      var rreshti = vlerat[v] || {}, pjeset = {};
      html += '<tr><td><strong>' + v + '</strong></td>';
      kk.forEach(function (m, i) {
        var t = rreshti[m] || '';
        totalet[i] += nr(t);
        pjeset[m] = nr(t);
        html += '<td><input inputmode="decimal" placeholder="—" data-vs-viti="' + v + '" data-vs-monedha="' + m + '" value="'
          + String(t).replace(/"/g, '&quot;') + '"></td>';
      });
      html += '<td class="vs-kat">' + (etiketa(kategoria(pjeset)) || '—') + '</td></tr>';
    });
    html += '</tbody><tfoot><tr><td>Totali</td>';
    kk.forEach(function (m, i) { html += '<td>' + (totalet[i] ? fmt(totalet[i], m) : '—') + '</td>'; });
    html += '<td><button type="button" class="btn-dytësor btn-sm" data-vs-ndaj title="Mbush sërish vitet">↺ Mbush sërish</button></td></tr></tfoot></table>';
    tabela.innerHTML = html;

    // kontrolli: totalet e viteve = shumat lart (ndryshojnë vetëm kur shkruhet me dorë lart)
    var t = totaletEFormes(), ok = true;
    kk.forEach(function (m, i) { if (Math.round(((t[m] || 0) - totalet[i]) * 100) !== 0) ok = false; });
    Object.keys(t).forEach(function (m) { if (kk.indexOf(m) === -1) ok = false; });
    var vitiFundit = vv[vv.length - 1], kf = {};
    kk.forEach(function (m) { kf[m] = nr((vlerat[vitiFundit] || {})[m]); });
    var k = kategoria(kf);
    permbledhja.textContent = ok
      ? (k ? etiketa(k) + ' (sipas vitit ' + vitiFundit + ')' : '')
      : '⚠️ Shumat e viteve nuk përputhen me shumën lart — kliko "↺ Mbush sërish" ose ndrysho shumat e viteve.';
    permbledhja.classList.toggle('vs-gabim', !ok);

    var json = {};
    vv.forEach(function (v) {
      json[v] = {};
      kk.forEach(function (m) { var s = (vlerat[v] || {})[m]; if (s) json[v][m] = String(s).replace(',', '.'); });
    });
    fsheh.value = JSON.stringify(json);
  }

  tabela.addEventListener('input', function (e) {
    var i = e.target.closest('[data-vs-viti]');
    if (!i) return;
    edituar = true;
    vlerat[i.dataset.vsViti] = vlerat[i.dataset.vsViti] || {};
    vlerat[i.dataset.vsViti][i.dataset.vsMonedha] = i.value;
    var poz = i.selectionStart, viti = i.dataset.vsViti, m = i.dataset.vsMonedha;
    sinkronizo();
    vizato();
    var iRi = tabela.querySelector('[data-vs-viti="' + viti + '"][data-vs-monedha="' + m + '"]');
    if (iRi) { iRi.focus(); try { iRi.setSelectionRange(poz, poz); } catch (x) {} }
  });
  tabela.addEventListener('keydown', function (e) {   // Enter → kutia poshtë (si në Excel), pa e dërguar formën
    var i = e.target.closest('[data-vs-viti]');
    if (!i || e.key !== 'Enter') return;
    e.preventDefault();
    var poshte = tabela.querySelector('[data-vs-viti="' + (+i.dataset.vsViti + 1) + '"][data-vs-monedha="' + i.dataset.vsMonedha + '"]');
    if (poshte) poshte.focus();
  });
  tabela.addEventListener('click', function (e) {
    if (!e.target.closest('[data-vs-ndaj]')) return;
    edituar = false;
    mbush();
    sinkronizo();
    vizato();
  });

  ['viti', 'viti_deri', 'shuma_hyrese', 'shuma_2', 'monedha', 'monedha_2'].forEach(function (emri) {
    var e = el(emri);
    if (!e) return;
    var lista = eshteRadio(e) ? Array.prototype.slice.call(e) : [e];
    var jane_vitet = emri === 'viti' || emri === 'viti_deri';
    lista.forEach(function (x) {
      ['input', 'change'].forEach(function (ngjarja) {
        x.addEventListener(ngjarja, function () {
          if (duke_sinkronizuar) return;
          // vitet e reja → mbushen sërish; shumat e shkruara lart → rindahen vetëm pa ndryshime me dorë
          if (ndarje && ndarje.checked && (jane_vitet || !edituar)) {
            edituar = false;
            mbush();
            if (jane_vitet) sinkronizo();
          }
          vizato();
        });
      });
    });
  });
  if (ndarje) ndarje.addEventListener('change', function () {
    edituar = false;
    if (ndarje.checked) {
      mbush();
      sinkronizo();
    }
    vizato();
  });

  // Pas gabimit të formës: rikthe ndarjen që u dërgua
  if (fsheh.value) {
    try {
      var vjetra = JSON.parse(fsheh.value);
      Object.keys(vjetra).forEach(function (v) {
        vlerat[v] = {};
        Object.keys(vjetra[v]).forEach(function (m) { vlerat[v][m] = String(vjetra[v][m]).replace('.', ','); });
      });
      edituar = true;
      if (ndarje) ndarje.checked = true;
    } catch (x) {}
  }
  vizato();
  return { rifresko: function () { edituar = false; vizato(); } };
};
