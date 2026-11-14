// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { checkoutUrl } from './checkout';

describe('checkoutUrl', () => {
  it('accepts an explicitly configured HTTPS checkout', () => {
    expect(checkoutUrl('https://payments.example.com/plan')).toBe('https://payments.example.com/plan');
  });

  it.each([undefined, '', '/checkout', 'http://example.com', 'javascript:alert(1)', 'https://user:pass@example.com'])(
    'does not enable checkout for an invalid configuration: %s',
    (value) => expect(checkoutUrl(value)).toBeNull(),
  );
});
