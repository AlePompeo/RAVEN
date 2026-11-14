// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/simula',
  titleKey: 'title.simulate',
  section: '/explore',
  order: 10,
  aliases: { '/lander': 'tab=sito', '/wave': 'tab=onda' },
  load: () => import('./Simula.svelte'),
};
export default page;
