import collections
from asyncio import mixins, exceptions
from contextlib import asynccontextmanager
from typing import Optional, Any


# Most of this code is copied from asyncio.Semaphore and asyncio.BoundedSemaphore
class FiniteResource(mixins._LoopBoundMixin):
    """A FiniteResource implementation.

    FiniteResource supports the context management protocol via the `use` method.

    The argument gives the initial value for the internal
    counter. If the value given is less than 0,
    ValueError is raised.
    """

    @asynccontextmanager
    async def use(self, value):
        await self.acquire(value)
        try:
            yield
        finally:
            self.release(value)

    def __init__(self, value):
        if value < 0:
            raise ValueError("initial value must be >= 0")
        self._waiters = None
        self._value = value

    def __repr__(self):
        res = super().__repr__()
        extra = "locked" if self.locked() else f"unlocked, value:{self._value}"
        if self._waiters:
            extra = f"{extra}, waiters:{len(self._waiters)}"
        return f"<{res[1:-1]} [{extra}]>"

    def locked_for_value(self, value):
        return self._value < value or (
            any(
                (self._value >= v) and (not w.cancelled())
                for (v, w) in (self._waiters or ())
            )
        )

    def locked(self):
        """Returns True if resource cannot be acquired immediately."""
        # Due to state, or FIFO rules (must allow others to run first).
        return self._value == 0 or (
            any(
                (self._value >= v) and (not w.cancelled())
                for (v, w) in (self._waiters or ())
            )
        )

    async def acquire(self, value):
        if self._value >= value:
            # Maintain FIFO, wait for others to start even if _value > 0.
            self._value -= value
            return True

        if self._waiters is None:
            self._waiters = collections.deque()
        fut = self._get_loop().create_future()
        vf = (value, fut)
        self._waiters.append(vf)

        try:
            try:
                await fut
            finally:
                self._waiters.remove(vf)
        except exceptions.CancelledError:
            # Currently the only exception designed be able to occur here.
            if fut.done() and not fut.cancelled():
                # Our Future was successfully set to True via _wake_up_next(),
                # but we are not about to successfully acquire(). Therefore we
                # must undo the bookkeeping already done and attempt to wake
                # up someone else.
                self._value += value
            raise

        finally:
            # New waiters may have arrived but had to wait due to FIFO.
            # Wake up as many as are allowed.
            while self._value > 0:
                if not self._wake_up_next():
                    break  # There was no-one to wake up.
        return True

    def release(self, value):
        self._value += value
        self._wake_up_next()

    def _wake_up_next(self):
        """Wake up the first waiter that isn't done."""
        if not self._waiters:
            return False

        for value, fut in self._waiters:
            if not fut.done() and (self._value >= value):
                self._value -= value
                fut.set_result(True)
                # `fut` is now `done()` and not `cancelled()`.
                return True
        return False


class BoundedFiniteResource(FiniteResource):
    _want_to_decrement_value: Optional[Any] = None

    def __init__(self, value=1):
        self._bound_value = value
        super().__init__(value)

    def release(self, value):
        if self._want_to_decrement_value:
            # In case the `bound_value` has been updated while there were active leases,
            # we allow the active leases to release "cleanly", but will not increment the value
            # This means, however, that if someone without an active lease calls `release` before the
            # active leases, there might be a race condition when the active lease calls `release`,
            # as only at that time will we raise the `ValueError` due to trying to release too many times
            decrement_amount = min(value, self._want_to_decrement_value)
            self._value -= decrement_amount
            self._want_to_decrement_value -= decrement_amount
        if self._value >= self._bound_value:
            raise ValueError("released too many times")
        self._value += value
        self._wake_up_next()

    def update_bound_value(self, new_value) -> tuple[bool, Any]:
        """Change the bounded maximum value to a different value"""
        diff = new_value - self._bound_value
        if diff == 0:
            self._want_to_decrement_value = None
            return True, 0
        elif diff > 0:
            # increment, easy
            self._bound_value = new_value
            self._value += diff  # possible floating-point errors, passing new_value as `Decimal` or int might be safer
            self._want_to_decrement_value = None
            # Since we are incrementing value, this is similar as calling `release`, as we are making available new
            # potential leases, so we will check now if we can wake up any waiters
            self._wake_up_next()
            return True, 0
        else:  # decrement, more complex
            value_of_active_leases = self._bound_value - self._value
            want_to_decrement_by = -diff
            # decrement the amount that we can decrement now safely
            # self._value should never be less than 0, so value_of_active_leases should never be negative unless
            # there is some illegal lease
            n_can_decrement_safely = max(0, self._bound_value - value_of_active_leases)
            if n_can_decrement_safely > 0:
                # decrement up to the maximum amount we want to decrement by
                n_decrement_by = min(want_to_decrement_by, n_can_decrement_safely)
                self._value -= n_decrement_by
                want_to_decrement_by -= n_decrement_by

            self._bound_value = new_value
            if want_to_decrement_by == 0:
                self._want_to_decrement_value = None
                return True, 0
            elif want_to_decrement_by > 0:  # could not update everything
                # set state, this should then be taken into account on the next release
                self._want_to_decrement_value = want_to_decrement_by
                return False, want_to_decrement_by
            else:
                raise RuntimeError(
                    "floating point imprecision error, use `Decimal` or `int` instead"
                )
