# asynchronous primitives for finite resources

We introduce the primitive `FiniteResource`, with a similar interface as `asyncio.Semaphore` with a key difference: when
acquiring a lease, you must specify the _amount_ of the resource you want to acquire.

The state of this package is still very much experimental.

e.g.

```python
from finite_resource import FiniteResource

fr = FiniteResource(200)

await fr.acquire(15)
await fr.acquire(100)
```

## Context manager

Similar to `asyncio.Semaphore` you can use the async context manager:

```python
from finite_resource import FiniteResource

fr = FiniteResource(200)

async with fr.use(10):
    pass
```


## Bounded resources and updating values

Similar to `asyncio.BoundedSemaphore`, you can set an upper limit on the amount of leases.

Additionally, you can update this value in-place, in case the amount of resource has changed during execution e.g.

```python
from finite_resource import BoundedFiniteResource
import asyncio

fr = BoundedFiniteResource(20)

async def _heavy_task(_fr):
    async with _fr.use(500):
        return True

async def _light_task(_fr):
    async with _fr.use(1):
        return True

heavy = asyncio.create_task(_heavy_task(fr))
await asyncio.sleep(0)
light = asyncio.create_task(_light_task(fr))
assert await light
assert not heavy.done()  # not able to acquire lease yet

fr.update_bound_value(1000) # more resources coming in...
assert await heavy # okay now
```


## Using non-integer numeric values

If using non-integer values, we recommend passing `Decimal` values rather than `float` to avoid floating-point precision errors.

```python
from finite_resource import FiniteResource
from decimal import Decimal

fr = FiniteResource(Decimal("13.48695"))

async with fr.use(Decimal("2.1")):
    pass
```