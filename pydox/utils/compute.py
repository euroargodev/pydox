from collections import OrderedDict
from typing import Any, Callable, Iterable, Literal
import concurrent.futures
import multiprocessing
import logging


log = logging.getLogger("pydox.utils.compute")

try:
    from tqdm import tqdm
except ModuleNotFoundError:
    log.debug("pydox needs 'tqdm' to display progress bars")

    def tqdm(fct, **kw):
        return fct


def _is_serial(obj: Callable) -> bool:
    from distributed.protocol import serialize
    from distributed.protocol.serialize import ToPickle

    try:
        serialize(ToPickle(obj))
        return True
    except:
        return False


def compute_fits(
    items: Iterable,
    fct: Callable,
    progress: bool = False,
    max_workers: int = 6,
    method: Literal["sequential", "thread"] = "sequential",
    errors: Literal["ignore", "raise", "silent"] = "raise",
) -> OrderedDict[Any, Any]:
    """A function to compute a collection of fit sequentially or in parallel, using several methods.

    Notes
    -----
    For the :class:`distributed.client.Client` and :class:`concurrent.futures.ProcessPoolExecutor` to work appropriately, the pre-processing :class:`collections.abc.Callable` must be serializable. This can be checked with:

    >>> from distributed.protocol import serialize
    >>> from distributed.protocol.serialize import ToPickle
    >>> serialize(ToPickle(preprocess_function))

    """
    results = OrderedDict()
    failed = []

    ################################
    if method in ["seq", "sequential"]:
        if progress:
            items = tqdm(items, total=len(items), disable="disable" in [progress])

        for iparam, params in items:
            data = None
            try:
                data = fct(params)
                # This is where we should implement progressive gain computation
                # by updating the new params from the previous iteration
            except Exception:
                failed.append(params)
                if errors == "ignore":
                    log.debug(f"Ignored error with this item: {params}")
                    # See fsspec.http logger for more
                    pass
                elif errors == "silent":
                    pass
                else:
                    raise
            finally:
                results[iparam] = data

        return results

    ################################
    elif method in ["thread", "process"]:
        if method == "thread":
            ConcurrentExecutor = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers
            )
        else:
            if max_workers == 6:
                max_workers = multiprocessing.cpu_count()
            ConcurrentExecutor = concurrent.futures.ProcessPoolExecutor(
                max_workers=max_workers
            )

        with ConcurrentExecutor as executor:
            future_to_url = {
                executor.submit(
                    fct,
                    params,
                ): iparam
                for iparam, params in items
            }
            futures = concurrent.futures.as_completed(future_to_url)
            if progress:
                futures = tqdm(
                    futures, total=len(items), disable="disable" in [progress]
                )

            for future in futures:
                iparam = future_to_url[future]
                data = None
                try:
                    data = future.result()
                except Exception:
                    failed.append(future_to_url[future])
                    if errors == "ignore":
                        log.debug(
                            f"Ignored error with this item: {future_to_url[future]}"
                        )
                        # See fsspec.http logger for more
                        pass
                    elif errors == "silent":
                        pass
                    else:
                        raise
                finally:
                    results[iparam] = data

        return results

    ################################
    else:
        raise NotImplementedError
