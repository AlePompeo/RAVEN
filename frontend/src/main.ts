// SPDX-License-Identifier: Apache-2.0
import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';
import { detectTv } from './shell/tv';
import { initI18n } from './i18n/i18n.svelte';

// navigazione spaziale con le frecce: chunk lazy, solo in modalità TV (fuori dalla TV i gestori uscivano subito)
if (detectTv()) void import('./shell/spatialNav').then((m) => m.installSpatialNav()).catch(() => {});

const target = document.getElementById('app');
if (!target) throw new Error('Elemento #app mancante');

// lingua risolta e catalogo caricato prima del primo rendering (nessun lampo di inglese né spostamento del layout);
// initI18n non rifiuta mai: in caso di errore o attesa troppo lunga resta l'inglese
void initI18n().then(() => mount(App, { target }));
