import asyncio

import pytest
from finite_resource import FiniteResource, BoundedFiniteResource


@pytest.mark.asyncio
async def test():
    fr = FiniteResource(value=3.5)
    assert (await fr.acquire(2)) is True

    task_1 = asyncio.create_task(fr.acquire(1))
    await asyncio.sleep(0)
    assert task_1.done()
    assert fr._value == 0.5
    fr.release(3)


@pytest.mark.asyncio
async def test2():
    fr = FiniteResource(value=3.5)
    assert (await fr.acquire(2)) is True

    task_1 = asyncio.create_task(fr.acquire(3))
    await asyncio.sleep(0)
    assert task_1.done() is False

    fr.release(2)
    await asyncio.sleep(0)
    assert task_1.done()


@pytest.mark.asyncio
async def test_ctx_manager():
    fr = FiniteResource(value=3.5)

    async with fr.use(1):
        assert fr._value == 2.5
    assert fr._value == 3.5

    async with fr.use(1):
        assert fr._value == 2.5
        async with fr.use(1.2):
            assert fr._value == 1.3
        assert fr._value == 2.5
    assert fr._value == 3.5

    cm = fr.use(2)
    async with cm:
        pass
    # cannot re-use cm
    with pytest.raises(AttributeError):
        async with cm:
            pass


@pytest.mark.asyncio
async def test3():
    fr = FiniteResource(value=2)
    # check FIFO may be bypassed if a lease can be acquired by a "later" task

    # too large value requested
    task_1 = asyncio.create_task(fr.acquire(5))
    await asyncio.sleep(0)
    assert task_1.done() is False

    # can still request smaller value and acquire
    assert not fr.locked()
    assert fr.locked_for_value(3)
    assert not fr.locked_for_value(2)
    task_2 = asyncio.create_task(fr.acquire(1))
    await asyncio.sleep(0)
    assert task_2.done()
    assert fr._value == 1

    task_1.cancel()
    await asyncio.sleep(0)
    assert task_1.cancelled()
    assert fr._value == 1


@pytest.mark.asyncio
async def test4():
    fr = FiniteResource(value=2)
    # check FIFO is respected as long as the value requested can be acquired
    task_1 = asyncio.create_task(fr.acquire(1))
    await asyncio.sleep(0)
    task_2 = asyncio.create_task(fr.acquire(2))
    await asyncio.sleep(0)

    assert task_1.done()
    assert task_2.done() is False

    fr.release(1)
    task_3 = asyncio.create_task(fr.acquire(1))
    await asyncio.sleep(0)
    assert task_2.done()
    assert task_3.done() is False
    assert fr.locked()

    fr.release(0.5)
    await asyncio.sleep(0)
    assert task_3.done() is False
    fr.release(0.5)
    await asyncio.sleep(0)
    assert task_3.done()


@pytest.mark.asyncio
async def test_bounded():
    fr = BoundedFiniteResource(value=2)
    with pytest.raises(ValueError):
        fr.release(1)

    # check FIFO is respected as long as the value requested can be acquired
    task_1 = asyncio.create_task(fr.acquire(1))
    await asyncio.sleep(0)
    task_2 = asyncio.create_task(fr.acquire(2))
    await asyncio.sleep(0)

    assert task_1.done()
    assert task_2.done() is False

    fr.release(1)
    task_3 = asyncio.create_task(fr.acquire(1))
    await asyncio.sleep(0)
    assert task_2.done()
    assert task_3.done() is False
    assert fr.locked()

    fr.release(0.5)
    await asyncio.sleep(0)
    assert task_3.done() is False
    fr.release(0.5)
    await asyncio.sleep(0)
    assert task_3.done()


from decimal import Decimal


@pytest.mark.asyncio
async def test_bounded_decimal():
    v = Decimal("2.53523463153")
    fr = BoundedFiniteResource(value=v)
    with pytest.raises(ValueError):
        fr.release(1)
    # check FIFO is respected as long as the value requested can be acquired
    task_1 = asyncio.create_task(fr.acquire(Decimal(1)))
    await asyncio.sleep(0)
    task_2 = asyncio.create_task(fr.acquire(Decimal(2)))
    await asyncio.sleep(0)

    assert task_1.done()
    assert task_2.done() is False

    fr.release(Decimal("1") - Decimal("0.53523463153"))
    task_3 = asyncio.create_task(fr.acquire(Decimal(1)))
    await asyncio.sleep(0)
    assert task_2.done()
    assert task_3.done() is False
    assert fr.locked()

    fr.release(Decimal("0.5"))
    await asyncio.sleep(0)
    assert task_3.done() is False
    fr.release(Decimal("0.5"))
    await asyncio.sleep(0)
    assert task_3.done()


@pytest.mark.asyncio
async def test_bounded_decimal_update():
    v = Decimal("2.53523463153")
    fr = BoundedFiniteResource(value=v)
    with pytest.raises(ValueError):
        fr.release(1)
    # check FIFO is respected as long as the value requested can be acquired
    task_1 = asyncio.create_task(fr.acquire(Decimal(1)))
    await asyncio.sleep(0)
    task_2 = asyncio.create_task(fr.acquire(Decimal(2)))
    await asyncio.sleep(0)

    fr.update_bound_value(Decimal("3"))
    await asyncio.sleep(0)  # wake up task_2
    assert task_1.done()
    assert task_2.done()
    assert fr.locked()

    # Make things difficult
    fr.update_bound_value(Decimal("1e-9"))

    # allow to release previous leases
    fr.release(Decimal(2))
    fr.release(Decimal(1))

    # but don't allow releasing any more than was previously acquired
    # (there may be race conditions in this scenario, we will live with that)
    with pytest.raises(ValueError):
        fr.release(Decimal("1e-8"))

    task_3 = asyncio.create_task(fr.acquire(Decimal(1)))
    await asyncio.sleep(0)
    assert task_2.done()
    assert task_3.done() is False
    assert fr._value == Decimal("1e-9")

    fr.update_bound_value(Decimal("0.5"))  # update again
    await asyncio.sleep(0)
    assert task_3.done() is False
    fr.update_bound_value(Decimal("1"))  # update again
    await asyncio.sleep(0)
    assert task_3.done()


@pytest.mark.asyncio
async def test_bounded_context_manager():
    fr = BoundedFiniteResource(value=20)
    with pytest.raises(ValueError):
        fr.release(1)

    async def _acquire(value):
        async with fr.use(value):
            await asyncio.sleep(0.01)

    task_1 = asyncio.create_task(_acquire(1))
    task_2 = asyncio.create_task(_acquire(2))
    await asyncio.sleep(0)
    assert not task_1.done()
    assert not task_2.done()
    assert fr._value == 17
    fr.update_bound_value(0)
    assert fr.locked()
    task_3 = asyncio.create_task(_acquire(1))
    await asyncio.sleep(0.011)
    assert task_1.done()
    assert task_2.done()
    assert not task_3.done()
    assert fr.locked()
    task_3.cancel()
    await asyncio.sleep(0)
    assert task_3.cancelled()
    assert fr.locked()

    task_4 = asyncio.create_task(_acquire(20))  # large value
    await asyncio.sleep(0)
    task_5 = asyncio.create_task(_acquire(2))  # small value
    await asyncio.sleep(0)
    fr.update_bound_value(3)  # small can go through, large cannot
    await asyncio.sleep(0.011)
    assert task_5.done()
    assert fr._value == 3
    fr.update_bound_value(20)
    await asyncio.sleep(0.011)
    assert task_4.done()
