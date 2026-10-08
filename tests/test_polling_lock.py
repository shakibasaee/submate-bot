"""A second local polling instance cannot enter, and shutdown releases the lock."""

import pytest

from app.core.polling_lock import polling_lock


def test_polling_lock_is_exclusive_and_released(tmp_path):
    with polling_lock("test-token", tmp_path):
        with pytest.raises(RuntimeError), polling_lock("test-token", tmp_path):
            pytest.fail("duplicate polling acquired lock")
        with polling_lock("different-token", tmp_path):
            pass
    with polling_lock("test-token", tmp_path):
        pass
