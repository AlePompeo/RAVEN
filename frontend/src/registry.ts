// SPDX-License-Identifier: Apache-2.0
import { createRouter, type PageModule } from './shell/router';

export const BASE: string = import.meta.env.BASE_URL;

// Auto-registrazione: ogni cartella pages/<nome>/ con index.ts (export default PageModule).
const modules = import.meta.glob<PageModule>('./pages/*/index.ts', {
  eager: true,
  import: 'default',
});

const pages = Object.values(modules);
export const router = createRouter(pages.filter((p) => p.path !== '/404'), pages.find((p) => p.path === '/404'), BASE);
