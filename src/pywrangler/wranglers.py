"""This module contains computation engine independent wrangler interfaces
and corresponding descriptions.

"""
from typing import Any

from pywrangler.base import BaseWrangler
from pywrangler.util import sanitizer
from pywrangler.util.types import TYPE_ASCENDING, TYPE_COLUMNS

NULL = object()


class IntervalIdentifier(BaseWrangler):
    """Defines the reference interface for the interval identification
    wrangler.

    An interval is defined as a range of values beginning with an opening
    marker and ending with a closing marker (e.g. the interval daylight may be
    defined as all events/values occurring between sunrise and sunset).

    The interval identification wrangler assigns ids to values such that values
    belonging to the same interval share the same interval id. For example, all
    values of the first daylight interval are assigned with id 1. All values of
    the second daylight interval will be assigned with id 2 and so on.

    Values which do not belong to any valid interval are assigned the value 0
    by definition.

    Only the shortest valid interval is identified. Given multiple opening
    markers in sequence without an intermittent closing marker, only the last
    opening marker is relevant and the rest is ignored. Given multiple
    closing markers in sequence without an intermittent opening marker, only
    the first closing marker is relevant and the rest is ignored.

    Opening and closing markers are included in their corresponding interval.

    Parameters
    ----------
    marker_column: str
        Name of column which contains the opening and closing markers.
    marker_start: Any
        A value defining the start of an interval.
    marker_end: Any, optional
        A value defining the end of an interval, if necessary
    order_columns: str, Iterable[str], optional
        Column names which define the order of the data (e.g. a timestamp
        column). Sort order can be defined with the parameter `ascending`.
    groupby_columns: str, Iterable[str], optional
        Column names which define how the data should be grouped/split into
        separate entities. For distributed computation engines, groupby columns
        should ideally reference partition keys to avoid data shuffling.
    ascending: bool, Iterable[bool], optional
        Sort ascending vs. descending. Specify list for multiple sort orders.
        If a list is specified, length of the list must equal length of
        `order_columns`. Default is True.
    target_column_name: str, optional
        Name of the resulting target column.

    """

    def __init__(self,
                 marker_column: str,
                 marker_start,
                 marker_end: Any = NULL,
                 order_columns: TYPE_COLUMNS = None,
                 groupby_columns: TYPE_COLUMNS = None,
                 ascending: TYPE_ASCENDING = None,
                 target_column_name: str = "iids"):

        self.marker_column = marker_column
        self.marker_start = marker_start
        self.marker_end = marker_end
        self.order_columns = sanitizer.ensure_iterable(order_columns)
        self.groupby_columns = sanitizer.ensure_iterable(groupby_columns)
        self.ascending = sanitizer.ensure_iterable(ascending)
        self.target_column_name = target_column_name

        self._naive_algorithm = marker_end == NULL

        # sanity checks for sort order
        if self.ascending:

            # check for equal number of items of order and sort columns
            if len(self.order_columns) != len(self.ascending):
                raise ValueError('`order_columns` and `ascending` must have '
                                 'equal number of items.')

            # check for correct sorting keywords
            if not all([isinstance(x, bool) for x in self.ascending]):
                raise ValueError('Only `True` and `False` are '
                                 'as arguments for `ascending`')

        # set default sort order if None is given
        elif self.order_columns:
            self.ascending = (True, ) * len(self.order_columns)

    @property
    def preserves_sample_size(self) -> bool:
        return True
