/* Dashboardi interaktiv i Fondit — hyrjet (donacionet) dhe daljet (harxhimet nga Fondi), me filtra si Power BI.
   Klikimi mbi një lloj (treemap / shiritat), një muaj ose një qelizë të matricës filtron gjithë faqen. */
(function () {
  'use strict';
  const D = JSON.parse(document.getElementById('te-dhenat-bi').textContent);
  const { P, MUAJT, MUAJT_PLOTE, DITET, eur, eurK, nr, pct, el } = BI;
  BI.konfiguroChartJs();

  const sot = new Date(D.sot + 'T12:00:00');
  const VITI_SOT = sot.getFullYear();
  const mdSot = D.sot.slice(5);
  const zbero = (d) => { const dt = new Date(d + 'T12:00:00'); return { y: dt.getFullYear(), m: dt.getMonth(), md: d.slice(5), wd: (dt.getDay() + 6) % 7, d }; };
  const hyrjet = D.hyrjet.map(([d, e, lloji, zekat, mon, donatori, kodi, origjinale]) => Object.assign(zbero(d), { eur: e, lloji, zekat, mon, donatori, kodi, origjinale }));
  const daljet = D.daljet.map(([d, e, lloji, zekat]) => Object.assign(zbero(d), { eur: e, lloji, zekat }));
  const vitet = [...new Set(hyrjet.concat(daljet).map(p => p.y).concat([VITI_SOT]))].sort();
  // Ngjyrat ndjekin llojin (radhë e qëndrueshme: më i madhi gjithsej merr ngjyrën e parë); pas 7 llojeve: "Të tjera" gri
  const renditLlojet = (lista, emrat) => {
    const tot = emrat.map((_, i) => BI.shuma(lista.filter(p => p.lloji === i).map(p => p.eur)));
    return emrat.map((_, i) => i).sort((a, b) => tot[b] - tot[a]);
  };
  const rendiH = renditLlojet(hyrjet, D.llojet), rendiD = renditLlojet(daljet, D.llojet_dalje);
  const ngjyraH = i => (rendiH.indexOf(i) < 7 ? P.s[rendiH.indexOf(i)] : P.tjera);
  const ngjyraD = i => (rendiD.indexOf(i) < 7 ? P.s[rendiD.indexOf(i)] : P.tjera);

  const S = { viti: VITI_SOT, muajt: new Set(), llojet: new Set(), llojetD: new Set(), monedhat: new Set(), zekat: 'all', metrika: 'muaj' };
  const ndrysho = (set, v) => { set.has(v) ? set.delete(v) : set.add(v); };

  const shiriti = document.getElementById('biFiltrat');
  const fViti = BI.grupiIFiltrave(shiriti, { titulli: 'Viti', opsionet: vitet.map(v => ({ v, t: v })).concat([{ v: 'all', t: 'Të gjitha' }]),
    kliko: v => { S.viti = v === 'all' ? 'all' : +v; rifresko(); } });
  const fMuajt = BI.grupiIFiltrave(shiriti, { titulli: 'Muajt', opsionet: MUAJT.map((t, v) => ({ v, t })), kliko: v => { ndrysho(S.muajt, +v); rifresko(); } });
  const fZekat = BI.grupiIFiltrave(shiriti, { titulli: 'Paraja', opsionet: [{ v: 'all', t: 'Të gjitha' }, { v: 'lire', t: 'Fondi i lirë' }, { v: 'zekat', t: '🌙 Zekati' }],
    kliko: v => { S.zekat = v; rifresko(); } });
  const fLloji = BI.grupiIFiltrave(shiriti, { titulli: 'Lloji i donacionit', opsionet: rendiH.map(v => ({ v, t: D.llojet[v] })), kliko: v => { ndrysho(S.llojet, +v); rifresko(); } });
  const fMon = BI.grupiIFiltrave(shiriti, { titulli: 'Monedha', opsionet: D.monedhat.map((t, v) => ({ v, t })), kliko: v => { ndrysho(S.monedhat, +v); rifresko(); } });
  document.getElementById('biPastro').addEventListener('click', () => {
    Object.assign(S, { viti: VITI_SOT, zekat: 'all' }); [S.muajt, S.llojet, S.llojetD, S.monedhat].forEach(s => s.clear()); rifresko();
  });
  document.querySelectorAll('#biMetrika button').forEach(b => b.addEventListener('click', () => { S.metrika = b.dataset.m; rifresko(); }));

  const zekatOk = p => S.zekat === 'all' || (S.zekat === 'zekat' ? p.zekat : !p.zekat);
  const hOk = p => zekatOk(p) && (!S.llojet.size || S.llojet.has(p.lloji)) && (!S.monedhat.size || S.monedhat.has(p.mon));
  const dOk = p => zekatOk(p) && (!S.llojetD.size || S.llojetD.has(p.lloji));
  const muajOk = p => !S.muajt.size || S.muajt.has(p.m);
  const sh = a => BI.shuma(a.map(p => p.eur));
  const mujore = a => { const r = Array(12).fill(0); a.forEach(p => { r[p.m] += p.eur; }); return r; };

  function rifresko() {
    const teGjitha = S.viti === 'all', viti = teGjitha ? VITI_SOT : S.viti;
    const ytd = !teGjitha && viti === VITI_SOT && !S.muajt.size;
    const neVit = (p, y) => (teGjitha || p.y === y) && muajOk(p);
    const hT = hyrjet.filter(p => neVit(p, viti) && hOk(p)), dT = daljet.filter(p => neVit(p, viti) && dOk(p));
    const hP = teGjitha ? [] : hyrjet.filter(p => p.y === viti - 1 && muajOk(p) && hOk(p) && (!ytd || p.md <= mdSot));
    const dP = teGjitha ? [] : daljet.filter(p => p.y === viti - 1 && muajOk(p) && dOk(p) && (!ytd || p.md <= mdSot));
    const H = sh(hT), Dl = sh(dT), ndr = (a, b) => (b ? 100 * (a - b) / b : null);
    // Gjendja e arkës në fund të periudhës (gjithë historia, sipas filtrit zekat)
    const fundi = teGjitha ? '9999-12-31' : `${viti}-12-31`;
    const gjendja = deri => sh(hyrjet.filter(p => zekatOk(p) && p.d <= deri)) - sh(daljet.filter(p => zekatOk(p) && p.d <= deri));
    const gjendjaFillim = teGjitha ? 0 : gjendja(`${viti - 1}-12-31`), gjendjaFund = gjendja(fundi);

    fViti.shfaq(v => String(v) === String(S.viti)); fMuajt.shfaq(v => S.muajt.has(+v)); fZekat.shfaq(v => v === S.zekat);
    fLloji.shfaq(v => S.llojet.has(+v)); fMon.shfaq(v => S.monedhat.has(+v));
    document.querySelectorAll('#biMetrika button').forEach(b => b.classList.toggle('aktiv', b.dataset.m === S.metrika));
    const pjeset = [teGjitha ? 'Të gjitha vitet' : String(viti)];
    if (S.muajt.size) pjeset.push([...S.muajt].sort((a, b) => a - b).map(m => MUAJT[m]).join(', '));
    if (S.zekat !== 'all') pjeset.push(S.zekat === 'zekat' ? 'Zekati' : 'Fondi i lirë');
    if (S.llojet.size) pjeset.push([...S.llojet].map(i => D.llojet[i]).join(', '));
    if (S.llojetD.size) pjeset.push('daljet: ' + [...S.llojetD].map(i => D.llojet_dalje[i]).join(', '));
    if (S.monedhat.size) pjeset.push([...S.monedhat].map(i => D.monedhat[i]).join(', '));
    document.getElementById('biPerzgjedhja').textContent = pjeset.join(' · ');
    const krahasim = ytd ? `kundrejt ${viti - 1} në të njëjtën periudhë` : `kundrejt ${viti - 1}`;

    // në arkë sipas monedhës, siç janë marrë (den · € · CHF · $)
    const sipasKodit = {};
    hT.forEach(p => { sipasKodit[p.kodi] = (sipasKodit[p.kodi] || 0) + p.origjinale; });
    const arka = [['MKD', ' den'], ['EUR', ' €'], ['CHF', ' CHF'], ['USD', ' $']].filter(([k]) => sipasKodit[k])
      .map(([k, s]) => nr(sipasKodit[k]) + s).join(' · ');
    BI.kpi(document.getElementById('kpiHyrje'), { etiketa: 'Hyrje (donacione)', vlera: eur(H), spark: mujore(hT),
      delta: teGjitha ? null : ndr(H, sh(hP)), deltaTekst: teGjitha ? `${nr(hT.length)} donacione` : krahasim, nen: arka ? 'në arkë: ' + arka : '' });
    BI.kpi(document.getElementById('kpiDalje'), { etiketa: 'Dalje (harxhime)', vlera: eur(Dl), spark: mujore(dT), ngjyra: P.s[1],
      delta: teGjitha ? null : ndr(Dl, sh(dP)), anasjelltas: true, deltaTekst: teGjitha ? `${nr(dT.length)} pagesa` : krahasim });
    BI.kpi(document.getElementById('kpiBilanci'), { etiketa: 'Bilanci i periudhës', vlera: (H - Dl >= 0 ? '+' : '−') + eur(Math.abs(H - Dl)),
      deltaTekst: H ? `${pct(100 * Dl / H)} e hyrjeve u shpenzuan` : '', nen: `${nr(hT.length)} donacione · mesatarisht ${eur(hT.length ? H / hT.length : 0)}` });
    BI.kpi(document.getElementById('kpiGjendja'), { etiketa: teGjitha ? 'Gjendja e Fondit sot' : `Gjendja më 31.12.${viti}`, vlera: eur(gjendjaFund),
      deltaTekst: teGjitha ? '' : `në fillim të vitit: ${eur(gjendjaFillim)}`, nen: 'të gjitha hyrjet − daljet deri atëherë' });

    grafikuKryesor(hT, dT, viti, teGjitha);
    ura(viti, teGjitha, gjendjaFillim);

    // Treemap: hyrjet sipas llojit
    const sipasLl = {};
    hT.forEach(p => { sipasLl[p.lloji] = (sipasLl[p.lloji] || 0) + p.eur; });
    BI.treemap(document.getElementById('biTreemap'), rendiH.map(i => ({ emri: D.llojet[i], vlera: sipasLl[i] || 0, ngjyra: ngjyraH(i), aktiv: S.llojet.has(i), i })),
      { kliko: a => { ndrysho(S.llojet, a.i); rifresko(); } });
    // Daljet sipas llojit
    const sipasLlD = {};
    dT.forEach(p => { sipasLlD[p.lloji] = (sipasLlD[p.lloji] || 0) + p.eur; });
    BI.renditja(document.getElementById('biDaljet'), rendiD.map(i => ({ emri: D.llojet_dalje[i], vlera: sipasLlD[i] || 0, ngjyra: P.s[1],
      aktiv: S.llojetD.has(i), i })).sort((a, b) => b.vlera - a.vlera).slice(0, 10), { kliko: a => { ndrysho(S.llojetD, a.i); rifresko(); } });
    // Donatorët kryesorë
    const sipasDon = {};
    hT.forEach(p => { sipasDon[p.donatori] = (sipasDon[p.donatori] || 0) + p.eur; });
    BI.renditja(document.getElementById('biDonatoret'), Object.keys(sipasDon).map(i => ({ emri: D.donatoret[i], vlera: sipasDon[i], ngjyra: P.s[0] }))
      .sort((a, b) => b.vlera - a.vlera).slice(0, 10));
    // Matrica e hyrjeve
    const vMat = vitet.slice().reverse();
    BI.matrica(document.getElementById('biMatrica'), {
      rreshtat: vMat, kolonat: MUAJT, rreshtiAktiv: teGjitha ? null : viti, formati: (v, shkurt) => (shkurt ? eurK(v).replace(' €', '') : eur(v)),
      vlerat: vMat.map(y => mujore(hyrjet.filter(p => p.y === y && hOk(p)))), kliko: (y, m) => { S.viti = +y; S.muajt = new Set([m]); rifresko(); },
    });
    // Zekati (pavarësisht filtrit "Paraja")
    const zH = sh(hyrjet.filter(p => p.zekat && neVit(p, viti))), zD = sh(daljet.filter(p => p.zekat && neVit(p, viti)));
    const zG = sh(hyrjet.filter(p => p.zekat && p.d <= fundi)) - sh(daljet.filter(p => p.zekat && p.d <= fundi));
    const zk = document.getElementById('biZekati');
    zk.replaceChildren();
    const kutite = el('div', 'bi-zekati');
    [['Hyri', zH], ['U shpenzua', zD], ['Gjendja e zekatit', zG]].forEach(([t, v]) => {
      const d = el('div'); d.appendChild(el('small', null, t)); d.appendChild(el('strong', null, eur(v))); kutite.appendChild(d);
    });
    zk.appendChild(kutite);
    const z100 = el('div'); zk.appendChild(z100);
    BI.shiriti100(z100, [{ emri: 'U shpenzua', vlera: Math.min(zD, zH), ngjyra: P.s[1] }, { emri: 'Mbetet', vlera: Math.max(0, zH - zD), ngjyra: P.s[2] }]);
    // Monedhat
    const sipasMon = {};
    hT.forEach(p => { sipasMon[p.mon] = (sipasMon[p.mon] || 0) + p.eur; });
    BI.shiriti100(document.getElementById('biMonedhat'), D.monedhat.map((emri, i) => ({ emri, vlera: sipasMon[i] || 0, ngjyra: P.s[i % 8] })));
    // Ditët e javës
    const ditet = Array(7).fill(0);
    hT.forEach(p => { ditet[p.wd] += p.eur; });
    const iMax = ditet.indexOf(Math.max(...ditet));
    BI.grafik('gDitet', {
      type: 'bar',
      data: { labels: BI.DITET_SHKURT, datasets: [{ data: ditet, borderRadius: 4, borderSkipped: 'start', maxBarThickness: 30,
        backgroundColor: ditet.map((_, i) => (i === iMax ? P.s[0] : P.prev)), etiketat: 'max' }] },
      options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 18 } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: c => DITET[c[0].dataIndex], label: c => ' ' + eur(c.raw) } } },
        scales: BI.boshtet(eurK) },
    });

    // Përmbledhja me fjalë
    const fj = [];
    const periudha = teGjitha ? 'gjithë vitet' : (S.muajt.size ? `${pjeset[1]} ${viti}` : (ytd ? `${viti} (deri sot)` : String(viti)));
    let f1 = `Në ${periudha} hynë ${eur(H)} nga ${nr(hT.length)} donacione dhe dolën ${eur(Dl)}`;
    f1 += H - Dl >= 0 ? ` — fondi u rrit me ${eur(H - Dl)}.` : ` — u shpenzua ${eur(Dl - H)} më shumë se sa hyri.`;
    fj.push(f1);
    const dH = ndr(H, sh(hP));
    if (dH != null && !teGjitha) fj.push(`Donacionet janë ${dH >= 0 ? 'rritur' : 'ulur'} ${pct(Math.abs(dH))} ${krahasim}.`);
    const llMax = Object.keys(sipasLl).sort((a, b) => sipasLl[b] - sipasLl[a])[0];
    if (llMax != null && H) fj.push(`Lloji më i madh: ${D.llojet[llMax]} (${pct(100 * sipasLl[llMax] / H)} e hyrjeve).`);
    const lldMax = Object.keys(sipasLlD).sort((a, b) => sipasLlD[b] - sipasLlD[a])[0];
    if (lldMax != null) fj.push(`Shpenzimi më i madh: ${D.llojet_dalje[lldMax]} (${eur(sipasLlD[lldMax])}).`);
    if (ditet[iMax]) fj.push(`Dhurohet më shumë ${DITET[iMax].toLowerCase()}.`);
    fj.push(`Gjendja e Fondit ${teGjitha ? 'sot' : 'në fund të ' + viti}: ${eur(gjendjaFund)}${zG ? `, prej tyre ${eur(zG)} zekat` : ''}.`);
    document.getElementById('biNarrativa').textContent = fj.join(' ');
  }

  function grafikuKryesor(hT, dT, viti, teGjitha) {
    const kat = teGjitha ? vitet : MUAJT;
    const seri = a => {
      const r = Array(kat.length).fill(0);
      a.forEach(p => { r[teGjitha ? vitet.indexOf(p.y) : p.m] += p.eur; });
      if (S.metrika === 'kumul') for (let i = 1; i < r.length; i++) r[i] += r[i - 1];
      return r;
    };
    const h = seri(hT), d = seri(dT);
    document.getElementById('titulliKryesor').textContent = (S.metrika === 'kumul' ? 'Hyrjet dhe daljet kumulative' : 'Hyrjet dhe daljet') +
      (teGjitha ? ' — vit për vit' : ' — muaj për muaj');
    const kumul = S.metrika === 'kumul';
    const ds = (label, data, ngjyra) => (kumul
      ? { type: 'line', label, data, borderColor: ngjyra, backgroundColor: ngjyra, borderWidth: 2, tension: 0.3, pointRadius: 0, pointHoverRadius: 5, etiketat: 'fundi' }
      : { type: 'bar', label, data, backgroundColor: ngjyra, borderRadius: 4, borderSkipped: 'start', maxBarThickness: 26 });
    BI.grafik('gKryesor', {
      type: kumul ? 'line' : 'bar',
      data: { labels: kat, datasets: [ds('Hyrje', h, P.s[0]), ds('Dalje', d, P.s[1])] },
      options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 16, right: 12 } }, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top', align: 'start', labels: kumul ? { pointStyle: 'line' } : {} },
          tooltip: { callbacks: {
            title: c => (teGjitha ? String(kat[c[0].dataIndex]) : MUAJT_PLOTE[c[0].dataIndex]),
            label: c => ` ${eur(c.raw)}  ${c.dataset.label}`,
            footer: c => { const i = c[0].dataIndex; return `Neto: ${h[i] - d[i] >= 0 ? '+' : '−'}${eur(Math.abs(h[i] - d[i]))}`; } } } },
        scales: BI.boshtet(eurK),
        onClick: (e, els) => { if (!els.length) return; if (teGjitha) S.viti = vitet[els[0].index]; else ndrysho(S.muajt, els[0].index); rifresko(); } },
    });
  }

  // Ura e gjendjes (waterfall): gjendja në fillim → neto i çdo muaji → gjendja në fund
  function ura(viti, teGjitha, fillimi) {
    const karta = document.getElementById('kartaUra');
    karta.style.display = teGjitha ? 'none' : '';
    if (teGjitha) return;
    const hV = hyrjet.filter(p => p.y === viti && zekatOk(p)), dV = daljet.filter(p => p.y === viti && zekatOk(p));
    const neto = mujore(hV).map((v, i) => v - mujore(dV)[i]);
    const muajMax = viti === VITI_SOT ? sot.getMonth() : 11;
    const etiketat = ['1 Jan'], vlerat = [[0, fillimi]], ngjyrat = [P.ink2], neto_ = [fillimi];
    let g = fillimi;
    for (let i = 0; i <= muajMax; i++) {
      etiketat.push(MUAJT[i]); vlerat.push([g, g + neto[i]]); ngjyrat.push(neto[i] >= 0 ? P.s[0] : P.s[7]); neto_.push(neto[i]); g += neto[i];
    }
    etiketat.push(viti === VITI_SOT ? 'Sot' : '31 Dhj'); vlerat.push([0, g]); ngjyrat.push(P.ink2); neto_.push(g);
    // Boshti nuk nis nga 0 kur ndryshimet janë të vogla kundrejt gjendjes — përndryshe muajt dalin vija të holla
    const nivelet = vlerat.slice(1, -1).flat().concat([fillimi, g]);
    const mn = Math.min(...nivelet), mx = Math.max(...nivelet), hapesira = Math.max(mx - mn, Math.abs(mx) * 0.05, 1);
    const fundiBoshtit = mn > 0 && mn - hapesira * 0.6 > 0 ? Math.floor((mn - hapesira * 0.6) / 1000) * 1000 : undefined;
    const iMaxNeto = neto_.slice(1, -1).reduce((b, v, i, a) => (Math.abs(v) > Math.abs(a[b]) ? i : b), 0) + 1;
    BI.grafik('gUra', {
      type: 'bar',
      data: { labels: etiketat, datasets: [{ data: vlerat, backgroundColor: ngjyrat, borderRadius: 3, borderSkipped: false, maxBarThickness: 34,
        etiketat: 'aktiv', aktive: [0, iMaxNeto, etiketat.length - 1],
        formatiEtiketes: (v, j) => (j === 0 || j === etiketat.length - 1 ? eurK(neto_[j]) : (neto_[j] >= 0 ? '+' : '−') + eurK(Math.abs(neto_[j]))) }] },
      options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 18 } },
        plugins: { legend: { display: false }, tooltip: { callbacks: {
          label: c => { const j = c.dataIndex; const tot = j === 0 || j === etiketat.length - 1;
            return tot ? ` Gjendja: ${eur(neto_[j])}` : ` Neto: ${neto_[j] >= 0 ? '+' : '−'}${eur(Math.abs(neto_[j]))} → ${eur(vlerat[j][1])}`; } } } },
        scales: BI.boshtet(eurK, { y: { min: fundiBoshtit, grid: { color: P.grid }, border: { display: false }, ticks: { color: P.muted, maxTicksLimit: 5, callback: eurK } } }) },
    });
  }

  rifresko();
})();
