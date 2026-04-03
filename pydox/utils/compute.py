from collections import OrderedDict
from typing import (
    Any,
    Callable,
    List,
    Literal,
    Tuple,
    TypeAlias,
)
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import multiprocessing
import logging

log = logging.getLogger("pydox.utils.compute")

ComputeMethods: TypeAlias = Literal["sequential", "thread"]
ErrorMethods: TypeAlias = Literal["raise", "ignore", "silent"]

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
    items: List[Tuple[int, Any]],
    fct: Callable,
    progress: bool = False,
    max_workers: int = 6,
    method: ComputeMethods = "sequential",
    errors: ErrorMethods = "raise",
) -> OrderedDict[int, Any]:
    """A function to compute a collection of fit sequentially or in parallel, using several methods.

    Parameters
    ----------
    items: List[Tuple[int, Any]]
        List of tuples, where 1st value is an integer and 2nd value is anything (typically a unique set of parameters).
        The integer value is used to build the result `OrderedDict`.
    fct: Callable
        A callable object that will reveice the 2nd value of the items tuples.
    max_workers: int, default: 6
        Maximum number of threads or processes
    method: str, default: ``sequential``
        Define the execution method:
            - ``sequential``/``seq``  (default): open data sequentially in a simple loop, no parallelization applied
            - ``thread``: based on :class:`concurrent.futures.ThreadPoolExecutor` with a pool of at most ``max_workers`` threads
            - ``process``: based on :class:`concurrent.futures.ProcessPoolExecutor` with a pool of at most ``max_workers`` processes
    progress: bool, default: False
        Display a progress bar
    errors: str, default: ``raise``
        Define how to handle errors raised during data URIs fetching:
            - ``raise`` (default): Raise any error encountered
            - ``ignore``: Do not stop processing, simply issue a debug message in log console
            - ``silent``: Do not stop processing and do not issue log message

    Returns
    -------
    OrderedDict[int, Any]
        Collected results ordered similarly to the input `items`.
        Eg: OrderedDict[12, Any] = fct(items[12][1])

    Notes
    -----
    For the :class:`distributed.client.Client` and :class:`concurrent.futures.ProcessPoolExecutor` to work appropriately, the function :class:`collections.abc.Callable` must be serializable. This can be checked with:

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
                # by updating the new params from the previous iteration.
                # This could be done using a callback function defined by the caller.
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
        if not _is_serial(fct):
            raise ValueError(
                "For a function to be executed in parallel, it must be serializable. This one is not."
            )

        if method == "thread":
            ConcurrentExecutor = ThreadPoolExecutor(max_workers=max_workers)
        else:
            if max_workers == 6:
                max_workers = multiprocessing.cpu_count()
            ConcurrentExecutor = ProcessPoolExecutor(max_workers=max_workers)

        with ConcurrentExecutor as executor:
            future_to_url = {
                executor.submit(
                    fct,
                    params,
                ): iparam
                for iparam, params in items
            }
            futures = as_completed(future_to_url)
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
