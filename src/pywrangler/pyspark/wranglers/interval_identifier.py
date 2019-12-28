"""This module contains implementations of the interval identifier wrangler.

"""
import sys

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from pywrangler.pyspark import util
from pywrangler.pyspark.base import PySparkSingleNoFit
from pywrangler.wranglers import IntervalIdentifier


class VectorizedCumSum(PySparkSingleNoFit, IntervalIdentifier):
    """Sophisticated approach avoiding python UDFs. However multiple windows
    are necessary.

    First, get enumeration of all intervals (valid and invalid). Every
    time a start or end marker is encountered, increase interval id by one.
    The end marker is shifted by one to include the end marker in the
    current interval. This is realized via the cumulative sum of boolean
    series of start markers and shifted end markers.

    Second, separate valid from invalid intervals by ensuring the presence
    of both start and end markers per interval id.

    Third, numerate valid intervals starting with 1 and set invalid
    intervals to 0.

    """

    def validate_input(self, df: DataFrame):
        """Checks input data frame in regard to column names.

        Parameters
        ----------
        df: pyspark.sql.Dataframe
            Dataframe to be validated.

        """

        util.validate_columns(df, self.marker_column)
        util.validate_columns(df, self.order_columns)
        util.validate_columns(df, self.groupby_columns)

        if self.order_columns is None:
            raise ValueError("Please define an order column. Pyspark "
                             "dataframes have no implicit order unlike pandas "
                             "dataframes.")

    def transform(self, df: DataFrame) -> DataFrame:
        """Extract interval ids from given dataframe.

        Parameters
        ----------
        df: pyspark.sql.Dataframe

        Returns
        -------
        result: pyspark.sql.Dataframe
            Same columns as original dataframe plus the new interval id column.

        """

        # check input
        self.validate_input(df)

        # define window specs
        orderby = util.prepare_orderby(self.order_columns, self.ascending)
        groupby = self.groupby_columns or []

        w_lag = Window.partitionBy(groupby).orderBy(orderby)
        w_id = Window.partitionBy(groupby + [self.target_column_name])

        # get boolean series with start and end markers
        marker_col = F.col(self.marker_column)
        bool_start = marker_col.eqNullSafe(self.marker_start).cast("integer")

        # account for identical start and end markers
        if self._identical_start_end_markers:
            ser_id = F.sum(bool_start).over(w_lag)
            return df.withColumn(self.target_column_name, ser_id)

        bool_end = marker_col.eqNullSafe(self.marker_end).cast("integer")
        bool_start_end = bool_start + bool_end

        # shifting the close marker allows cumulative sum to include the end
        bool_end_shift = F.lag(bool_end, default=1).over(w_lag).cast("integer")
        bool_start_end_shift = bool_start + bool_end_shift

        # get increasing ids for intervals (in/valid) with cumsum
        ser_id = F.sum(bool_start_end_shift).over(w_lag)

        # separate valid vs invalid: ids with start AND end marker are valid
        bool_valid = F.sum(bool_start_end).over(w_id) == 2
        valid_ids = F.when(bool_valid, ser_id).otherwise(0)

        # re-numerate ids from 1 to x and fill invalid with 0
        valid_ids_shift = F.lag(valid_ids, default=0).over(w_lag)
        valid_ids_diff = valid_ids_shift - valid_ids
        valid_ids_increase = (valid_ids_diff < 0).cast("integer")

        renumerate = F.sum(valid_ids_increase).over(w_lag)
        renumerate_adjusted = F.when(bool_valid, renumerate).otherwise(0)

        # ser_id needs be created temporarily for renumerate_adjusted
        return df.withColumn(self.target_column_name, ser_id) \
            .withColumn(self.target_column_name, renumerate_adjusted)

    def transform_first_start_first_end(self, df: DataFrame) -> DataFrame:
        """Extract interval ids from given dataframe.

        Parameters
        ----------
        df: pyspark.sql.Dataframe

        Returns
        -------
        result: pyspark.sql.Dataframe
            Same columns as original dataframe plus the new interval id column.

        """

        # check input
        self.validate_input(df)

        # define window specs
        orderby = util.prepare_orderby(self.order_columns, self.ascending)
        groupby = self.groupby_columns or []

        w_lag = Window.partitionBy(groupby).orderBy(orderby)
        w_id = Window.partitionBy(groupby + [self.target_column_name])

        # get boolean series with start and end markers
        marker_col = F.col(self.marker_column)
        bool_start = marker_col.eqNullSafe(self.marker_start).cast("integer")

        # account for identical start and end markers
        if self._identical_start_end_markers:
            ser_id = F.sum(bool_start).over(w_lag)
            return df.withColumn(self.target_column_name, ser_id)

        bool_end = marker_col.eqNullSafe(self.marker_end).cast("integer")
        bool_start_end = bool_start + bool_end

        # ffill marker start
        ffill = F.when(marker_col == self.marker_start, 1) \
            .when(marker_col == self.marker_end, 0) \
            .otherwise(None)

        ffill_col = F.last(ffill, ignorenulls=True).over(w_lag.rowsBetween(-sys.maxsize, 0))
        # shift
        shift_col = F.lag(ffill_col, default=0, count=1).over(w_lag).cast("integer")
        # compare ffill and ffill_shift col if equal set to 0
        end_marker_null_col = F.when(shift_col == ffill_col, 0).otherwise(ffill_col)
        # negate shift_col
        shift_col_negated = F.when(shift_col == 0, 1).otherwise(0)
        # add
        add_col = end_marker_null_col + shift_col_negated
        # cumsum
        ser_id = F.sum(add_col).over(w_lag)
        df = df.withColumn(self.target_column_name, ser_id)

        # separate valid vs invalid: ids with start AND end marker are valid
        bool_valid = F.sum(bool_start_end).over(w_id) >= 2
        valid_ids = F.when(bool_valid, ser_id).otherwise(0)

        return df.withColumn(self.target_column_name, valid_ids)

    def transform_last_start_last_end(self, df: DataFrame) -> DataFrame:
        """Extract interval ids from given dataframe.

                Parameters
                ----------
                df: pyspark.sql.Dataframe

                Returns
                -------
                result: pyspark.sql.Dataframe
                    Same columns as original dataframe plus the new interval id column.

                """

        # check input
        self.validate_input(df)

        # define window specs
        orderby_reverse = util.prepare_reverse_orderby(self.order_columns, self.ascending)
        orderby = util.prepare_orderby(self.order_columns, self.ascending)
        groupby = self.groupby_columns or []

        w_lag = Window.partitionBy(groupby).orderBy(orderby_reverse)
        w_id = Window.partitionBy(groupby + [self.target_column_name])

        # get boolean series with start and end markers
        marker_col = F.col(self.marker_column)
        bool_start = marker_col.eqNullSafe(self.marker_start).cast("integer")

        # account for identical start and end markers
        if self._identical_start_end_markers:
            ser_id = F.sum(bool_start).over(w_lag)
            return df.withColumn(self.target_column_name, ser_id)

        bool_end = marker_col.eqNullSafe(self.marker_end).cast("integer")
        bool_start_end = bool_start + bool_end

        # ffill marker start
        ffill = F.when(marker_col == self.marker_end, 1) \
            .when(marker_col == self.marker_start, 0) \
            .otherwise(None)

        ffill_col = F.last(ffill, ignorenulls=True).over(w_lag.rowsBetween(-sys.maxsize, 0))
        # shift, default = 1
        shift_col = F.lag(ffill_col, default=1, count=1).over(w_lag).cast("integer")
        # compare ffill and ffill_shift col if equal set to 0
        end_marker_null_col = F.when(shift_col == ffill_col, 0).otherwise(ffill_col)
        # negate shift_col
        shift_col_negated = F.when(shift_col == 0, 1).otherwise(0)
        # add
        add_col = end_marker_null_col + shift_col_negated
        # cumsum
        ser_id = F.sum(add_col).over(w_lag)
        ser_id = ser_id + 1
        df = df.withColumn(self.target_column_name, ser_id)

        # separate valid vs invalid: ids with start AND end marker are valid
        bool_valid = F.sum(bool_start_end).over(w_id) >= 2
        valid_ids = F.when(bool_valid, ser_id).otherwise(0)

        return df.withColumn(self.target_column_name, valid_ids).orderBy(orderby)

    def transform_first_start_last_end(self, df: DataFrame) -> DataFrame:
        """Extract interval ids from given dataframe.

        Parameters
        ----------
        df: pyspark.sql.Dataframe

        Returns
        -------
        result: pyspark.sql.Dataframe
            Same columns as original dataframe plus the new interval id column.

        """

        # check input
        self.validate_input(df)

        # define window specs
        orderby = util.prepare_orderby(self.order_columns, self.ascending)
        groupby = self.groupby_columns or []

        w_lag = Window.partitionBy(groupby).orderBy(orderby)
        w_id = Window.partitionBy(groupby + [self.target_column_name])

        # get boolean series with start and end markers
        marker_col = F.col(self.marker_column)

        # account for identical start and end markers
        # if self._identical_start_end_markers:
        #   ser_id = F.sum(bool_start).over(w_lag)
        #   return df.withColumn(self.target_column_name, ser_id)

        bool_start = marker_col.eqNullSafe(self.marker_start).cast("integer")
        start_ende = F.when(marker_col == self.marker_start, 1) \
            .when(marker_col == self.marker_end, 0) \
            .otherwise(None)
        ffill = F.last(start_ende, ignorenulls=True) \
            .over(w_lag.rowsBetween(-sys.maxsize, 0))
        ffill_shift = F.lag(ffill, default=0, count=1) \
            .over(w_lag) \
            .cast("integer")

        start_and_fill_shift = F.when(ffill == ffill_shift, 0) \
            .otherwise(ffill)

        cum_sum = F.sum(start_and_fill_shift) \
            .over(w_lag)
        df = df.withColumn(self.target_column_name, cum_sum)

        # delete noise in groups
        ser_id = F.when((~marker_col.isin([self.marker_start, self.marker_end])) &
                        (ffill == 0), None) \
            .otherwise(cum_sum)

        bfill = F.first(ser_id, ignorenulls=True) \
            .over(w_id.orderBy(orderby).rowsBetween(0, sys.maxsize))
        return df.withColumn(self.target_column_name, bfill) \
            .withColumn(self.target_column_name, F.when(F.isnull(self.target_column_name), 0) \
                        .otherwise(cum_sum))
