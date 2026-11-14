// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

// Ospita l'analisi GrazingLink esistente (un sito reale nel tempo).
const page: PageModule = {
  path: '/analizza',
  titleKey: 'title.analyze',
  section: '/explore',
  order: 20,
  aliases: { '/grazinglink': '' },
  load: () => import('../grazinglink/GrazingLink.svelte'),
};
export default page;
