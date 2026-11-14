# SPDX-License-Identifier: Apache-2.0
def test_core_importable():
    import backend.core

    assert backend.core is not None
