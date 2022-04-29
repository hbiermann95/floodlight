import matplotlib
import pandas as pd


# TODO: @utils checkaxisgiven
def plot_events(
    events,
    start: int = None,
    end: int = None,
    use_frameclock: bool = False,
    ax: matplotlib.axes = None,
    **kwargs,
) -> matplotlib.axes:
    """Plots events of the floodlight Events object within a time interval.

    Parameters
    ----------
    events: floodlight.core.events.Events
        Event data fragment that contains the events as a DataFrame.
    start: int, optional
        Frameclock or gameclock value from which on events are drawm. Defaults to
        beginning of segment.
    end: int, optional
        Frameclock or gameclock value until which on events are drawn. Defaults to end
        of segment.
    use_frameclock: bool = False,
        Whether to use the values in the ``frameclock`` column as time axis. If set to
        ``False`` (default), values from ``gameclock`` are used.
    ax: matplotlib.axes
        Axes from matplotlib library on which the events are drawn.
    kwargs:
        Optional keyworded arguments e.g. {'linewidth', 'zorder', 'linestyle', 'alpha'}
        which can be used for the plot functions from matplotlib. The kwargs are only
        passed to all the plot functions of matplotlib.
    Returns
    -------
    matplotlib.axes
        A matplotlib.axes on which the trajectories are drawn.
    """
    col = "frameclock" if use_frameclock else "gameclock"

    for _, event in events.events.iterrows():
        if not start <= event[col] < end:
            continue

        at_x = event["at_x"]
        at_y = event["at_y"]
        if not pd.isna(at_x) and not pd.isna(at_y):
            ax.scatter(at_x, at_y, **kwargs)

    return ax
