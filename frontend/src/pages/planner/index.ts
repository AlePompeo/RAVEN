// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/mission-planner',
  title: 'Mission Planner',
  navLabel: 'Mission Planner',
  order: 5,
  load: () => import('./MissionPlanner.svelte'),
};
export default page;
