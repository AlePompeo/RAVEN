// SPDX-License-Identifier: Apache-2.0
// Applica la modalità TV (html[data-tv]) in modo sincrono, prima del primo paint e prima del bundle: la
// scala del rem e il padding di overscan non cambiano dopo la prima pittura (CLS). Stessa logica di
// detectTv() in src/shell/spatialNav.ts, che resta la fonte di verità (e la riapplica al montaggio).
// File esterno (non inline): la CSP è default-src 'self'.
(function () {
  try {
    var q = new URLSearchParams(location.search).get('tv');
    var saved = false;
    try {
      saved = localStorage.getItem('hb.tv') === '1';
    } catch (e) {
      saved = false;
    }
    var big = typeof matchMedia === 'function' && matchMedia('(min-width: 1920px) and (not (any-pointer: fine))').matches;
    if (q === '1' || (q !== '0' && (saved || big))) document.documentElement.dataset.tv = '1';
  } catch (e) {
    /* la modalità TV resta decisa da detectTv() */
  }
})();
