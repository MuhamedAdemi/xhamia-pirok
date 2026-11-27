/* Dashboardi interaktiv i Antarësisë — çdo filtër (viti, muajt, monedha, kategoria) rifreskon gjithë faqen menjëherë.
   Klikimi mbi një muaj te kurba / matrica ose mbi një kategori filtron edhe pamjet e tjera (si "cross-filter" në Power BI). */
(function () {
  'use strict';
  const D = JSON.parse(document.getElementById('te-dhenat-bi').textContent);
  const { P, MUAJT, MUAJT_PLOTE, DITET, eur, eurK, nr, pct, el } = BI;
  BI.konfiguroChartJs();

  const sot = new Date(D.sot + 'T12:00:00');
  const VITI_SOT = sot.getFullYear();
  const mdSot = D.sot.slice(5);
  const pagesat = D.pagesat.map(([d, e, mon, kat, vitet]) => {
    const dt = new Date(d + 'T12:00:00');
    return { y: dt.getFullYear(), m: dt.getMonth(), md: d.slice(5), wd: (dt.getDay() + 6) % 7, eur: e, mon, kat, vitet };
  });
  const vitet = [...new Set(pagesat.map(p => p.y).concat([VITI_SOT]))].sort();
  const NGJYRA_MON = i => P.s[i % 8];   // monedha ndjek gjithmonë të njëjtën ngjyrë
  const rendiKat = D.kategorite.map((k, i) => i).sort((a, b) => D.kategorite[a].localeCompare(D.kategorite[b]));
  const NGJYRA_KAT = i => P.s[rendiKat.indexOf(i) % 8];

  const S = { viti: VITI_SOT, muajt: new Set(), monedhat: new Set(), kategorite: new Set(), metrika: 'eur' };

  // ── Filtrat ─────────────────────────────────────────────────────────────
  const shiriti = document.getElementById('biFiltrat');
  const fViti = BI.grupiIFiltrave(shiriti, { titulli: 'Viti', opsionet: vitet.map(v => ({ v, t: v })).concat([{ v: 'all', t: 'Të gjitha' }]),
    kliko: v => { S.viti = v === 'all' ? 'all' : +v; rifresko(); } });
  const fMuajt = BI.grupiIFiltrave(shiriti, { titulli: 'Muajt', opsionet: MUAJT.map((t, v) => ({ v, t })),
    kliko: v => { ndrysho(S.muajt, +v); rifresko(); } });
  const fMon = BI.grupiIFiltrave(shiriti, { titulli: 'Monedha', opsionet: D.monedhat.map((t, v) => ({ v, t })),
    kliko: v => { ndrysho(S.monedhat, +v); rifresko(); } });
  const fKat = BI.grupiIFiltrave(shiriti, { titulli: 'Kategoria e pagesës', opsionet: rendiKat.map(v => ({ v, t: D.kategorite[v] })),
    kliko: v => { ndrysho(S.kategorite, +v); rifresko(); } });
  document.getElementById('biPastro').addEventListener('click', () => {
    S.viti = VITI_SOT; S.muajt.clear(); S.monedhat.clear(); S.kategorite.clear(); rifresko();
  });
  document.querySelectorAll('#biMetrika button').forEach(b => b.addEventListener('click', () => { S.metrika = b.dataset.m; rifresko(); }));
  function ndrysho(set, v) { set.has(v) ? set.delete(v) : set.add(v); }

  const dimOk = p => (!S.monedhat.size || S.monedhat.has(p.mon)) && (!S.kategorite.size || S.kategorite.has(p.kat));
  const muajOk = p => !S.muajt.size || S.muajt.has(p.m);

  // ── Rifreskimi ──────────────────────────────────────────────────────────
  function rifresko() {
    const teGjitha = S.viti === 'all';
    const viti = teGjitha ? VITI_SOT : S.viti;
    const ytd = !teGjitha && viti === VITI_SOT && !S.muajt.size;
    const tani = pagesat.filter(p => (teGjitha || p.y === viti) && muajOk(p) && dimOk(p));
    const para = teGjitha ? [] : pagesat.filter(p => p.y === viti - 1 && muajOk(p) && dimOk(p) && (!ytd || p.md <= mdSot));
    const shumaEur = a => BI.shuma(a.map(p => p.eur));
    const eurTani = shumaEur(tani), eurPara = shumaEur(para);
    const ndr = (a, b) => (b ? 100 * (a - b) / b : null);
    const mujore = a => { const r = Array(12).fill(0); a.forEach(p => { r[p.m] += p.eur; }); return r; };
    const numriMujor = a => { const r = Array(12).fill(0); a.forEach(p => { r[p.m] += 1; }); return r; };

    fViti.shfaq(v => String(v) === String(S.viti));
    fMuajt.shfaq(v => S.muajt.has(+v));
    fMon.shfaq(v => S.monedhat.has(+v));
    fKat.shfaq(v => S.kategorite.has(+v));
    document.querySelectorAll('#biMetrika button').forEach(b => b.classList.toggle('aktiv', b.dataset.m === S.metrika));
    const pjeset = [teGjitha ? 'Të gjitha vitet' : String(viti)];
    if (S.muajt.size) pjeset.push([...S.muajt].sort((a, b) => a - b).map(m => MUAJT[m]).join(', '));
    if (S.monedhat.size) pjeset.push([...S.monedhat].map(i => D.monedhat[i]).join(', '));
    if (S.kategorite.size) pjeset.push([...S.kategorite].map(i => D.kategorite[i]).join(', '));
    document.getElementById('biPerzgjedhja').textContent = pjeset.join(' · ');
    const krahasim = ytd ? `kundrejt ${viti - 1} deri më ${sot.getDate()}.${sot.getMonth() + 1}` : `kundrejt ${viti - 1}`;

    // KPI
    BI.kpi(document.getElementById('kpiMbledhur'), { etiketa: 'Mbledhur', vlera: eur(eurTani), spark: mujore(tani),
      delta: teGjitha ? null : ndr(eurTani, eurPara), deltaTekst: teGjitha ? '' : krahasim });
    BI.kpi(document.getElementById('kpiPagesa'), { etiketa: 'Pagesa', vlera: nr(tani.length), spark: numriMujor(tani), ngjyra: P.s[6],
      delta: teGjitha ? null : ndr(tani.length, para.length), deltaTekst: teGjitha ? '' : `${nr(para.length)} vjet` });
    const mes = tani.length ? eurTani / tani.length : 0, mesPara = para.length ? eurPara / para.length : 0;
    BI.kpi(document.getElementById('kpiMesatarja'), { etiketa: 'Mesatarja për pagesë', vlera: eur(mes),
      delta: teGjitha ? null : ndr(mes, mesPara), deltaTekst: teGjitha ? '' : `${eur(mesPara)} vjet`,
      nen: `pagesa më e madhe: ${eur(Math.max(0, ...tani.map(p => p.eur)))}` });
    const mb = D.mbulimi.find(m => m.viti === viti);
    if (mb) BI.gauge(document.getElementById('kpiMbulimi'), mb.perqindja, `${nr(mb.paguar)} / ${nr(mb.paguar + mb.papaguar)}`,
      `shtëpi e kanë paguar ${viti} · ${nr(mb.papaguar)} ende jo`);

    // Kurba kryesore
    grafikuKryesor(tani, para, viti, teGjitha);
    // Matrica vite × muaj (pa filtrin e vitit / muajve)
    const vMat = vitet.slice().reverse();
    BI.matrica(document.getElementById('biMatrica'), {
      rreshtat: vMat, kolonat: MUAJT, rreshtiAktiv: teGjitha ? null : viti, formati: (v, shkurt) => (shkurt ? eurK(v).replace(' €', '') : eur(v)),
      vlerat: vMat.map(y => mujore(pagesat.filter(p => p.y === y && dimOk(p)))),
      kliko: (y, m) => { S.viti = +y; S.muajt = new Set([m]); rifresko(); },
    });
    // Mbulimi vit për vit
    BI.grafik('gMbulimi', {
      type: 'bar',
      data: { labels: D.mbulimi.map(m => m.viti), datasets: [{
        data: D.mbulimi.map(m => m.perqindja), borderRadius: 4, borderSkipped: 'start', maxBarThickness: 34,
        backgroundColor: D.mbulimi.map(m => (m.viti === viti ? P.s[0] : P.prev)),
        etiketat: 'aktiv', aktive: [D.mbulimi.findIndex(m => m.viti === viti)], formatiEtiketes: v => pct(v) }] },
      options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 18 } },
        plugins: { legend: { display: false }, tooltip: { callbacks: {
          label: c => { const m = D.mbulimi[c.dataIndex]; return ` ${pct(m.perqindja)} · ${nr(m.paguar)} paguar, ${nr(m.papaguar)} jo`; } } } },
        scales: BI.boshtet(v => v + '%', { y: { min: 0, max: 100, grid: { color: P.grid }, border: { display: false },
          ticks: { color: P.muted, stepSize: 25, callback: v => v + '%' } } }),
        onClick: (e, els) => { if (els.length) { S.viti = D.mbulimi[els[0].index].viti; rifresko(); } } },
    });
    // Për cilat vite u pagua
    const perVit = {};
    tani.forEach(p => p.vitet.forEach(([v, e]) => { perVit[v] = (perVit[v] || 0) + e; }));
    const vv = Object.keys(perVit).map(Number).sort();
    const ngjyraVit = v => (v < viti ? P.s[1] : v === viti ? P.s[0] : P.s[2]);
    BI.grafik('gPerVitet', {
      type: 'bar',
      data: { labels: vv, datasets: [{ data: vv.map(v => perVit[v]), backgroundColor: vv.map(ngjyraVit), borderRadius: 4,
        borderSkipped: 'start', maxBarThickness: 30, etiketat: 'max' }] },
      options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 18 } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ' ' + eur(c.raw) } } }, scales: BI.boshtet(eurK) },
    });
    const vjeter = BI.shuma(vv.filter(v => v < viti).map(v => perVit[v])), ardhme = BI.shuma(vv.filter(v => v > viti).map(v => perVit[v]));
    const gjPerVit = BI.shuma(Object.values(perVit));
    legjenda(document.getElementById('legPerVitet'), [
      [P.s[1], 'Borxh i viteve të kaluara', pct(gjPerVit ? 100 * vjeter / gjPerVit : 0)],
      [P.s[0], teGjitha ? 'Viti aktual' : `Viti ${viti}`, pct(gjPerVit ? 100 * (perVit[viti] || 0) / gjPerVit : 0)],
      [P.s[2], 'Paradhënie (vite të ardhshme)', pct(gjPerVit ? 100 * ardhme / gjPerVit : 0)]]);
    // Kategoritë e pagesave
    const sipasKat = {};
    tani.forEach(p => { sipasKat[p.kat] = (sipasKat[p.kat] || 0) + p.eur; });
    BI.renditja(document.getElementById('biKategorite'), rendiKat.map(i => ({ emri: D.kategorite[i], vlera: sipasKat[i] || 0,
      ngjyra: NGJYRA_KAT(i), aktiv: S.kategorite.has(i), i })), { kliko: a => { ndrysho(S.kategorite, a.i); rifresko(); } });
    // Ditët e javës
    const ditet = Array(7).fill(0);
    tani.forEach(p => { ditet[p.wd] += 1; });
    const iMax = ditet.indexOf(Math.max(...ditet));
    BI.grafik('gDitet', {
      type: 'bar',
      data: { labels: BI.DITET_SHKURT, datasets: [{ data: ditet, borderRadius: 4, borderSkipped: 'start', maxBarThickness: 30,
        backgroundColor: ditet.map((_, i) => (i === iMax ? P.s[0] : P.prev)), etiketat: 'max', formatiEtiketes: v => nr(v) }] },
      options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 18 } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: c => DITET[c[0].dataIndex], label: c => ` ${nr(c.raw)} pagesa` } } },
        scales: BI.boshtet(v => v) },
    });
    // Monedhat
    const sipasMon = {};
    tani.forEach(p => { sipasMon[p.mon] = (sipasMon[p.mon] || 0) + p.eur; });
    BI.shiriti100(document.getElementById('biMonedhat'), D.monedhat.map((emri, i) => ({ emri, vlera: sipasMon[i] || 0, ngjyra: NGJYRA_MON(i) })));
    // Borxhi (gjendja e sotme e shtëpive)
    BI.renditja(document.getElementById('biBorxhi'), D.borxhi.map((b, i) => ({
      emri: b.grupi === '0' ? '✓ Pa borxh' : `${b.grupi} ${b.grupi === '1' ? 'vit' : 'vite'}`, vlera: b.nr,
      ngjyra: i === 0 ? P.good : P.seq[Math.min(12, 3 + i * 1.5 | 0)] })), { formati: v => `${nr(v)} shtëpi` });

    // Përmbledhja me fjalë (si "Smart narrative" në Power BI)
    const fj = [];
    const periudha = teGjitha ? 'gjithë vitet' : (S.muajt.size ? `${pjeset[1]} ${viti}` : (ytd ? `${viti} (deri sot)` : String(viti)));
    let f1 = `Në ${periudha} u mblodhën ${eur(eurTani)} nga ${nr(tani.length)} pagesa`;
    const d = ndr(eurTani, eurPara);
    if (d != null && !teGjitha) f1 += `, ${d >= 0 ? 'më shumë' : 'më pak'} se ${viti - 1} (${d >= 0 ? '+' : ''}${pct(d)})`;
    fj.push(f1 + '.');
    const mj = mujore(tani), mMax = mj.indexOf(Math.max(...mj));
    if (mj[mMax] > 0 && !S.muajt.size) fj.push(`Muaji më i fortë: ${MUAJT_PLOTE[mMax]} (${eur(mj[mMax])}).`);
    if (gjPerVit) fj.push(`${pct(100 * vjeter / gjPerVit)} e shumës ishte për borxhe të vjetra, ${pct(100 * ardhme / gjPerVit)} paradhënie.`);
    if (ditet[iMax]) fj.push(`Paguhet më shumë ${DITET[iMax].toLowerCase()}.`);
    if (mb) fj.push(`Vitin ${viti} e kanë paguar ${nr(mb.paguar)} nga ${nr(mb.paguar + mb.papaguar)} shtëpi (${pct(mb.perqindja)}).`);
    document.getElementById('biNarrativa').textContent = fj.join(' ');
  }

  function grafikuKryesor(tani, para, viti, teGjitha) {
    const titulli = document.getElementById('titulliKryesor');
    if (teGjitha) {
      const sipasVitit = vitet.map(y => BI.shuma(tani.filter(p => p.y === y).map(p => S.metrika === 'nr' ? 1 : p.eur)));
      titulli.textContent = 'Vit për vit';
      BI.grafik('gKryesor', {
        type: 'bar',
        data: { labels: vitet, datasets: [{ data: sipasVitit, backgroundColor: P.s[0], borderRadius: 4, borderSkipped: 'start', maxBarThickness: 46,
          etiketat: 'te_gjitha', formatiEtiketes: S.metrika === 'nr' ? nr : eurK }] },
        options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 20 } }, plugins: { legend: { display: false },
          tooltip: { callbacks: { label: c => ' ' + (S.metrika === 'nr' ? nr(c.raw) + ' pagesa' : eur(c.raw)) } } },
          scales: BI.boshtet(S.metrika === 'nr' ? (v => v) : eurK),
          onClick: (e, els) => { if (els.length) { S.viti = vitet[els[0].index]; rifresko(); } } },
      });
      return;
    }
    const seri = a => {
      const r = Array(12).fill(0);
      a.forEach(p => { r[p.m] += S.metrika === 'nr' ? 1 : p.eur; });
      if (S.metrika === 'kumul') for (let i = 1; i < 12; i++) r[i] += r[i - 1];
      return r;
    };
    const tn = seri(tani), pr = seri(para);
    const kufiri = viti === VITI_SOT ? sot.getMonth() : 11;
    if (viti === VITI_SOT) for (let i = kufiri + 1; i < 12; i++) tn[i] = null;   // muajt që s'kanë ardhur ende
    const fmt = S.metrika === 'nr' ? nr : eurK;
    titulli.textContent = { eur: 'Euro të mbledhura muaj për muaj', nr: 'Numri i pagesave muaj për muaj', kumul: 'Të mbledhurat kumulative' }[S.metrika];
    const ctx = document.getElementById('gKryesor').getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 0, 300);
    grad.addColorStop(0, 'rgba(42,120,214,0.22)'); grad.addColorStop(1, 'rgba(42,120,214,0)');
    BI.grafik('gKryesor', {
      type: 'line',
      data: { labels: MUAJT, datasets: [
        { label: String(viti), data: tn, borderColor: P.s[0], backgroundColor: grad, fill: true, tension: 0.35, borderWidth: 2,
          pointRadius: tn.map((_, i) => (S.muajt.has(i) ? 6 : 3)), pointHoverRadius: 7, pointBackgroundColor: P.s[0],
          pointBorderColor: '#fff', pointBorderWidth: 2, etiketat: 'fundi', formatiEtiketes: fmt, spanGaps: false },
        { label: String(viti - 1), data: pr, borderColor: P.prev, backgroundColor: P.prev, fill: false, tension: 0.35, borderWidth: 2,
          pointRadius: 0, pointHoverRadius: 5 },
      ] },
      options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 16, right: 12 } },
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top', align: 'start', labels: { pointStyle: 'line' } },
          tooltip: { callbacks: { title: c => MUAJT_PLOTE[c[0].dataIndex],
            label: c => ` ${c.raw == null ? '—' : (S.metrika === 'nr' ? nr(c.raw) + ' pagesa' : eur(c.raw))}  ${c.dataset.label}` } } },
        scales: BI.boshtet(fmt),
        onClick: (e, els) => { if (els.length) { ndrysho(S.muajt, els[0].index); rifresko(); } } },
    });
  }

  function legjenda(nyja, artikujt) {
    nyja.replaceChildren();
    artikujt.forEach(([c, t, v]) => {
      const i = el('span', 'bi-leg-i');
      const k = el('i'); k.style.background = c; i.appendChild(k);
      i.appendChild(el('span', null, t + ' '));
      i.appendChild(el('strong', null, v));
      nyja.appendChild(i);
    });
  }

  rifresko();
})();
