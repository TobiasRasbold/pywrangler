"""This module contains the dask base wrangler.

"""

from dask.dataframe import DataFrame

from pywrangler.base import BaseWrangler


class DaskWrangler(BaseWrangler):
    """Contains methods common to all dask based wranglers.

    """

    @property
    def computation_engine(self):
        return "dask"


class DaskSingleNoFit(DaskWrangler):
    """Mixin class defining `fit` and `fit_transform` for all wranglers with
    a single data frame input and output with no fitting necessary.

    """

    def fit(self, df: DataFrame):
        """Do nothing and return the wrangler unchanged.

        This method is just there to implement the usual API and hence work in
        pipelines.

        Parameters
        ----------
        df: pd.DataFrame

        """

        return self

    def fit_transform(self, df: DataFrame) -> DataFrame:
        """Apply fit and transform in sequence at once.

        Parameters
        ----------
        df: pd.DataFrame

        Returns
        -------
        result: pd.DataFrame

        """

        return self.fit(df).transform(df)
