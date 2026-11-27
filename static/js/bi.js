/*
 * BI — pjesët e dashboardeve interaktive (në stilin e Power BI) për Antarësinë dhe Fondin.
 * Filtrat (slicers), KPI me sparkline, gauge, matricë me ngjyra, treemap, shirita renditjeje, shirit 100%,
 * tooltip i përbashkët dhe parazgjedhjet e Chart.js. Ngjyrat: paleta e validuar (blu, portokalli, gurkali…),
 * e njëjta ngjyrë ndjek gjithmonë të njëjtën kategori; vlerat dhe etiketat janë gjithmonë me ngjyrë teksti.
 */
window.BI = (function () {
  'use strict';

  const P = {
    s: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
    ink: '#0b0b0b', ink2: '#52514e', muted: '#898781', grid: '#e1e0d9', axis: '#c3c2b7', surface: '#fcfcfb',
    prev: '#b9b8b0', tjera: '#c3c2b7',
    // ramp sekuencial blu (100 → 700)
    seq: ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab',
          '#184f95', '#104281', '#0d366b'],
    good: '#0ca30c', critical: '#d03b3b', upText: '#006300', downText: '#b42318',
  };
  const MUAJT = ['Jan', 'Shk', 'Mar', 'Pri', 'Maj', 'Qer', 'Kor', 'Gus', 'Sht', 'Tet', 'Nën', 'Dhj'];
  const MUAJT_PLOTE = ['Janar', 'Shkurt', 'Mars', 'Prill', 'Maj', 'Qershor', 'Korrik', 'Gusht', 'Shtator', 'Tetor', 'Nëntor', 'Dhjetor'];
  const DITET = ['E hënë', 'E martë', 'E mërkurë', 'E enjte', 'E premte', 'E shtunë', 'E diel'];
  const DITET_SHKURT = ['Hën', 'Mar', 'Mër', 'Enj', 'Pre', 'Sht', 'Die'];

  // ── Formatet ────────────────────────────────────────────────────────────
  const nf0 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 });
  const eur = v => nf0.format(Math.round(v || 0)) + ' €';
  const eurK = v => Math.abs(v) >= 10000 ? nf1.format(v / 1000) + 'k €' : eur(v);
  const nr = v => nf0.format(v || 0);
  const pct = v => (v == null || !isFinite(v)) ? '—' : nf1.format(v) + '%';

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function svg(tag, attrs) {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  const shuma = a => a.reduce((s, x) => s + x, 0);
  // mbi ngjyrat e çelura (gurkali, e verdhë, rozë, gri) tekst i zi — që të lexohet
  const tekstNeNgjyre = hex => ([P.s[2], P.s[3], P.s[4], P.tjera, P.prev].includes(hex) ? P.ink : '#ffffff');

  // ── Tooltip i përbashkët për pjesët HTML ───────────────────────────────
  let tip;
  function tooltip(e, rreshtat) {   // rreshtat: [[vlera, etiketa, ngjyra?], ...] — vlera e para, me të trasha
    if (!tip) { tip = el('div', 'bi-tip'); document.body.appendChild(tip); }
    tip.replaceChildren();
    rreshtat.forEach(([v, t, c]) => {
      const r = el('div', 'bi-tip-r');
      if (c) { const k = el('span', 'bi-tip-k'); k.style.background = c; r.appendChild(k); }
      r.appendChild(el('strong', null, v));
      if (t) r.appendChild(el('span', null, ' ' + t));
      tip.appendChild(r);
    });
    tip.style.display = 'block';
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    const y = Math.min(e.clientY + 14, window.innerHeight - tip.offsetHeight - 8);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function fshehTip() { if (tip) tip.style.display = 'none'; }
  function meTooltip(nyja, fn) {
    nyja.addEventListener('pointermove', e => tooltip(e, fn()));
    nyja.addEventListener('pointerleave', fshehTip);
  }

  // ── Filtrat (slicers) ──────────────────────────────────────────────────
  // grupi({titulli, opsionet:[{v,t}], shume:true|false, vlera, ndrysho})
  function grupiIFiltrave(mbajtesi, cfg) {
    const g = el('div', 'bi-slicer');
    g.appendChild(el('div', 'bi-slicer-t', cfg.titulli));
    const rr = el('div', 'bi-chips');
    const butonat = cfg.opsionet.map(o => {
      const b = el('button', 'bi-chip', o.t);
      b.type = 'button';
      b.dataset.v = o.v;
      b.addEventListener('click', () => cfg.kliko(o.v));
      rr.appendChild(b);
      return b;
    });
    g.appendChild(rr);
    mbajtesi.appendChild(g);
    return { shfaq: aktive => butonat.forEach(b => b.classList.toggle('aktiv', aktive(b.dataset.v))) };
  }

  // ── KPI me sparkline ───────────────────────────────────────────────────
  function kpi(nyja, k) {
    nyja.replaceChildren();
    nyja.appendChild(el('div', 'bi-kpi-etiketa', k.etiketa));
    const rr = el('div', 'bi-kpi-rr');
    rr.appendChild(el('div', 'bi-kpi-vlera', k.vlera));
    if (k.spark && k.spark.some(v => v)) rr.appendChild(sparkline(k.spark, k.ngjyra || P.s[0]));
    nyja.appendChild(rr);
    if (k.delta != null && isFinite(k.delta)) {
      const mire = k.anasjelltas ? k.delta <= 0 : k.delta >= 0;
      const d = el('div', 'bi-delta ' + (mire ? 'mire' : 'keq'));
      d.appendChild(el('span', 'bi-delta-v', (k.delta >= 0 ? '▲ +' : '▼ ') + nf1.format(k.delta) + '%'));
      d.appendChild(el('span', 'bi-delta-t', ' ' + (k.deltaTekst || '')));
      nyja.appendChild(d);
    } else if (k.deltaTekst) {
      nyja.appendChild(el('div', 'bi-kpi-nen', k.deltaTekst));
    }
    if (k.nen) nyja.appendChild(el('div', 'bi-kpi-nen', k.nen));
  }
  function sparkline(vlerat, ngjyra) {
    const W = 96, H = 34, max = Math.max(...vlerat, 1), n = vlerat.length;
    const pikat = vlerat.map((v, i) => [i * W / (n - 1), H - 3 - (v / max) * (H - 6)]);
    const d = pikat.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
    const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: 'bi-spark', 'aria-hidden': 'true' });
    s.appendChild(svg('path', { d: d + ` L${W} ${H} L0 ${H} Z`, fill: ngjyra, opacity: '0.12' }));
    s.appendChild(svg('path', { d, fill: 'none', stroke: ngjyra, 'stroke-width': '2', 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    let iFundit = n - 1;
    while (iFundit > 0 && !vlerat[iFundit]) iFundit--;
    s.appendChild(svg('circle', { cx: pikat[iFundit][0], cy: pikat[iFundit][1], r: '3', fill: ngjyra, stroke: '#fff', 'stroke-width': '1.5' }));
    return s;
  }

  // ── Gauge (gjysmë rrethi) ──────────────────────────────────────────────
  function gauge(nyja, perqindja, qendra, nen) {
    nyja.replaceChildren();
    const R = 80, cx = 100, cy = 92, p = Math.max(0, Math.min(100, perqindja || 0));
    const pika = a => [cx - R * Math.cos(a), cy - R * Math.sin(a)];
    const hark = (nga, deri) => {
      const [x1, y1] = pika(nga), [x2, y2] = pika(deri);
      return `M${x1.toFixed(1)} ${y1.toFixed(1)} A${R} ${R} 0 ${deri - nga > Math.PI ? 1 : 0} 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`;
    };
    const s = svg('svg', { viewBox: '0 0 200 112', class: 'bi-gauge', role: 'img', 'aria-label': `${pct(p)} ${nen || ''}` });
    s.appendChild(svg('path', { d: hark(0, Math.PI), fill: 'none', stroke: '#ecebe6', 'stroke-width': '16', 'stroke-linecap': 'round' }));
    if (p > 0) s.appendChild(svg('path', { d: hark(0, Math.PI * p / 100), fill: 'none', stroke: P.s[0], 'stroke-width': '16', 'stroke-linecap': 'round' }));
    const t = svg('text', { x: cx, y: cy - 14, 'text-anchor': 'middle', class: 'bi-gauge-v' });
    t.textContent = pct(p);
    s.appendChild(t);
    const t2 = svg('text', { x: cx, y: cy + 8, 'text-anchor': 'middle', class: 'bi-gauge-t' });
    t2.textContent = qendra || '';
    s.appendChild(t2);
    [['0%', 20], ['100%', 180]].forEach(([tx, x]) => {
      const e = svg('text', { x, y: 110, 'text-anchor': 'middle', class: 'bi-gauge-a' });
      e.textContent = tx;
      s.appendChild(e);
    });
    nyja.appendChild(s);
    if (nen) nyja.appendChild(el('div', 'bi-gauge-nen', nen));
  }

  // ── Matrica me ngjyra (vite × muaj) ─────────────────────────────────────
  function matrica(nyja, cfg) {   // {rreshtat:[...], kolonat:[...], vlerat:[[...]], rreshtiAktiv, formati, kliko(r,c)}
    nyja.replaceChildren();
    const max = Math.max(1, ...cfg.vlerat.flat());
    const totalet = cfg.vlerat.map(shuma), maxT = Math.max(1, ...totalet);
    const t = el('table', 'bi-matrica');
    const kr = el('tr');
    kr.appendChild(el('th', null, ''));
    cfg.kolonat.forEach(k => kr.appendChild(el('th', null, k)));
    kr.appendChild(el('th', 'bi-m-tot', 'Gjithsej'));
    const thead = el('thead'); thead.appendChild(kr); t.appendChild(thead);
    const tb = el('tbody');
    cfg.rreshtat.forEach((r, i) => {
      const tr = el('tr', String(r) === String(cfg.rreshtiAktiv) ? 'aktiv' : '');
      tr.appendChild(el('th', null, r));
      cfg.vlerat[i].forEach((v, j) => {
        const td = el('td');
        if (v) {
          const hapi = Math.min(P.seq.length - 1, Math.round(1 + (v / max) * (P.seq.length - 2)));
          td.style.background = P.seq[hapi];
          td.style.color = hapi >= 6 ? '#fff' : P.ink;
          td.textContent = cfg.formati(v, true);
        }
        td.tabIndex = v ? 0 : -1;
        meTooltip(td, () => [[cfg.formati(v), `${MUAJT_PLOTE[j]} ${r}`]]);
        if (cfg.kliko) td.addEventListener('click', () => cfg.kliko(r, j));
        tr.appendChild(td);
      });
      const tot = el('td', 'bi-m-tot');
      const bar = el('span', 'bi-m-bar'); bar.style.width = (100 * totalet[i] / maxT) + '%';
      tot.appendChild(bar);
      tot.appendChild(el('span', 'bi-m-totv', cfg.formati(totalet[i], true)));
      tr.appendChild(tot);
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    nyja.appendChild(t);
    const leg = el('div', 'bi-m-legjenda');
    leg.appendChild(el('span', null, 'më pak'));
    [1, 3, 5, 7, 9, 11].forEach(h => { const s = el('i'); s.style.background = P.seq[h]; leg.appendChild(s); });
    leg.appendChild(el('span', null, 'më shumë'));
    nyja.appendChild(leg);
  }

  // ── Treemap (algoritmi "squarify") ──────────────────────────────────────
  function squarify(vlerat, x, y, w, h) {
    const dalje = [];
    let rreshti = [];
    const rest = vlerat.slice();
    const meIKeq = (rr, ana) => {
      const s = shuma(rr), mx = Math.max(...rr), mn = Math.min(...rr);
      return Math.max(ana * ana * mx / (s * s), (s * s) / (ana * ana * mn));
    };
    function vendos(rr) {
      const s = shuma(rr);
      if (w >= h) { const gw = s / h; let yy = y; rr.forEach(v => { dalje.push([x, yy, gw, v / gw]); yy += v / gw; }); x += gw; w -= gw; }
      else { const gh = s / w; let xx = x; rr.forEach(v => { dalje.push([xx, y, v / gh, gh]); xx += v / gh; }); y += gh; h -= gh; }
    }
    while (rest.length) {
      const ana = Math.min(w, h), v = rest[0];
      if (!rreshti.length || meIKeq(rreshti.concat(v), ana) <= meIKeq(rreshti, ana)) { rreshti.push(v); rest.shift(); }
      else { vendos(rreshti); rreshti = []; }
    }
    if (rreshti.length) vendos(rreshti);
    return dalje;
  }
  function treemap(nyja, artikujt, cfg) {   // artikujt: [{emri, vlera, ngjyra, aktiv}]
    nyja.replaceChildren();
    const lista = artikujt.filter(a => a.vlera > 0).sort((a, b) => b.vlera - a.vlera);
    if (!lista.length) { nyja.appendChild(el('div', 'bi-bosh', 'Asnjë e dhënë për këta filtra')); return; }
    const W = nyja.clientWidth || 400, H = nyja.clientHeight || 260, gjithsej = shuma(lista.map(a => a.vlera));
    const kutite = squarify(lista.map(a => a.vlera * W * H / gjithsej), 0, 0, W, H);
    const kaAktiv = lista.some(a => a.aktiv);
    lista.forEach((a, i) => {
      const [x, y, w, h] = kutite[i];
      const d = el('div', 'bi-tm');
      Object.assign(d.style, { left: x + 'px', top: y + 'px', width: Math.max(0, w - 2) + 'px', height: Math.max(0, h - 2) + 'px',
        background: a.ngjyra, color: tekstNeNgjyre(a.ngjyra), opacity: kaAktiv && !a.aktiv ? 0.35 : 1 });
      if (w > 70 && h > 38) {
        d.appendChild(el('div', 'bi-tm-e', a.emri));
        d.appendChild(el('div', 'bi-tm-v', `${eurK(a.vlera)} · ${pct(100 * a.vlera / gjithsej)}`));
      }
      meTooltip(d, () => [[eur(a.vlera), `${a.emri} · ${pct(100 * a.vlera / gjithsej)}`, a.ngjyra]]);
      if (cfg && cfg.kliko) d.addEventListener('click', () => cfg.kliko(a));
      nyja.appendChild(d);
    });
  }

  // ── Shiritat e renditjes (si tabela me "data bars" në Power BI) ─────────
  function renditja(nyja, artikujt, cfg) {   // [{emri, vlera, nen, ngjyra, aktiv}], cfg {formati, kliko, max}
    nyja.replaceChildren();
    cfg = cfg || {};
    const formati = cfg.formati || eur;
    const lista = artikujt.filter(a => a.vlera > 0);
    if (!lista.length) { nyja.appendChild(el('div', 'bi-bosh', 'Asnjë e dhënë për këta filtra')); return; }
    const max = Math.max(...lista.map(a => a.vlera)), kaAktiv = lista.some(a => a.aktiv);
    lista.forEach(a => {
      const r = el('div', 'bi-rr' + (cfg.kliko ? ' klikueshem' : '') + (kaAktiv && !a.aktiv ? ' zbehur' : ''));
      const em = el('div', 'bi-rr-e', a.emri);
      em.title = a.emri;
      r.appendChild(em);
      const sh = el('div', 'bi-rr-sh');
      const b = el('div', 'bi-rr-b'); b.style.width = (100 * a.vlera / max) + '%'; b.style.background = a.ngjyra || P.s[0];
      sh.appendChild(b);
      r.appendChild(sh);
      r.appendChild(el('div', 'bi-rr-v', formati(a.vlera)));
      meTooltip(r, () => [[formati(a.vlera), a.emri + (a.nen ? ' · ' + a.nen : ''), a.ngjyra || P.s[0]]]);
      if (cfg.kliko) r.addEventListener('click', () => cfg.kliko(a));
      nyja.appendChild(r);
    });
  }

  // ── Shiriti 100% (pjesë e së tërës) me legjendë ─────────────────────────
  function shiriti100(nyja, artikujt, formati) {
    nyja.replaceChildren();
    formati = formati || eur;
    const lista = artikujt.filter(a => a.vlera > 0), gj = shuma(lista.map(a => a.vlera));
    if (!gj) { nyja.appendChild(el('div', 'bi-bosh', 'Asnjë e dhënë')); return; }
    const bar = el('div', 'bi-100');
    lista.forEach(a => {
      const s = el('div', 'bi-100-s');
      s.style.width = (100 * a.vlera / gj) + '%';
      s.style.background = a.ngjyra;
      const p = 100 * a.vlera / gj;
      if (p >= 12) { s.textContent = pct(p); s.style.color = tekstNeNgjyre(a.ngjyra); }
      meTooltip(s, () => [[formati(a.vlera), `${a.emri} · ${pct(p)}`, a.ngjyra]]);
      bar.appendChild(s);
    });
    nyja.appendChild(bar);
    const leg = el('div', 'bi-legjenda');
    lista.forEach(a => {
      const i = el('span', 'bi-leg-i');
      const k = el('i'); k.style.background = a.ngjyra; i.appendChild(k);
      i.appendChild(el('span', null, `${a.emri} `));
      i.appendChild(el('strong', null, pct(100 * a.vlera / gj)));
      leg.appendChild(i);
    });
    nyja.appendChild(leg);
  }

  // ── Chart.js: parazgjedhjet + etiketat e zgjedhura ──────────────────────
  function konfiguroChartJs() {
    if (!window.Chart) return;
    Chart.defaults.font.family = "system-ui, -apple-system, 'Segoe UI', sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = P.muted;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.plugins.legend.labels.color = P.ink2;
    Object.assign(Chart.defaults.plugins.tooltip, {
      backgroundColor: '#ffffff', titleColor: P.ink2, bodyColor: P.ink, borderColor: 'rgba(11,11,11,0.12)', borderWidth: 1,
      padding: 10, cornerRadius: 8, usePointStyle: true, boxPadding: 4, titleFont: { weight: '500' }, bodyFont: { weight: '600' },
    });
    // Etiketat: vetëm aty ku i kërkon dataseti (etiketat: 'fundi' | 'max' | 'aktiv'), me ngjyrë teksti
    Chart.register({
      id: 'biEtiketat',
      afterDatasetsDraw(chart) {
        const { ctx } = chart;
        chart.data.datasets.forEach((ds, i) => {
          if (!ds.etiketat || chart.getDatasetMeta(i).hidden) return;
          const meta = chart.getDatasetMeta(i), vl = ds.data.map(v => (Array.isArray(v) ? v[1] - v[0] : v) || 0);
          let indekset = [];
          if (ds.etiketat === 'fundi') { let j = vl.length - 1; while (j > 0 && !vl[j]) j--; indekset = [j]; }
          else if (ds.etiketat === 'max') indekset = [vl.indexOf(Math.max(...vl))];
          else if (ds.etiketat === 'aktiv') indekset = (ds.aktive || []);
          else if (ds.etiketat === 'te_gjitha') indekset = vl.map((_, j) => j);
          ctx.save();
          ctx.font = "600 11.5px system-ui, -apple-system, 'Segoe UI', sans-serif";
          ctx.fillStyle = P.ink2;
          ctx.textAlign = 'center';
          indekset.forEach(j => {
            const el = meta.data[j];
            if (!el || !vl[j]) return;
            const tekst = (ds.formatiEtiketes || eurK)(vl[j], j);
            const y = ds.type === 'line' || chart.config.type === 'line' ? el.y - 10 : Math.min(el.y, el.base) - 6;
            ctx.fillText(tekst, el.x, y);
          });
          ctx.restore();
        });
      },
    });
  }
  function boshtet(formati, extra) {
    return Object.assign({
      x: { grid: { display: false }, border: { color: P.axis }, ticks: { color: P.muted } },
      y: { beginAtZero: true, grid: { color: P.grid, drawTicks: false }, border: { display: false },
           ticks: { color: P.muted, maxTicksLimit: 5, padding: 8, callback: formati || (v => v) } },
    }, extra || {});
  }
  const grafiket = {};
  function grafik(id, cfg) {
    if (grafiket[id]) grafiket[id].destroy();
    grafiket[id] = new Chart(document.getElementById(id), cfg);
    return grafiket[id];
  }

  return { P, MUAJT, MUAJT_PLOTE, DITET, DITET_SHKURT, eur, eurK, nr, pct, el, shuma, tooltip, fshehTip, meTooltip, grupiIFiltrave, kpi,
           sparkline, gauge, matrica, treemap, renditja, shiriti100, konfiguroChartJs, boshtet, grafik };
})();
