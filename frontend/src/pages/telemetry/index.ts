// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/telemetry',
  titleKey: 'title.telemetry',
  section: '/explore',
  order: 36,
  load: () => import('./Telemetry.svelte'),
};
export default page;
