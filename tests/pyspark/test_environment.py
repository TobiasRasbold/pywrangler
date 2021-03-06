"""Check for working test environment.

"""

import os
import subprocess

import pytest

pytestmark = pytest.mark.pyspark


def test_java_environment():
    """Pyspark requires Java to be available. It uses Py4J to start and
    communicate with the JVM. Py4J looks for JAVA_HOME or falls back calling
    java directly. This test explicitly checks for the java prerequisites for
    pyspark to work correctly. If errors occur regarding the instantiation of
    a pyspark session, this test helps to rule out potential java related
    causes.

    """

    java_home = os.environ.get("JAVA_HOME")

    java_version = subprocess.run(["java", "-version"],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT,
                                  universal_newlines=True)

    if (java_home is None) and (java_version.returncode != 0):
        raise EnvironmentError("Java setup broken.")


def test_pyspark_import():
    """Fail if pyspark can't be imported. This test is mandatory because other
    pyspark tests will be skipped if the pyspark session fixture fails.

    """

    try:
        import pyspark
        print(pyspark.__version__)
    except (ImportError, ModuleNotFoundError):
        pytest.fail("pyspark can't be imported")


def test_pyspark_pandas_interaction(spark):
    """Check simple interaction between pyspark and pandas.

    """

    import pandas as pd
    import numpy as np

    df_pandas = pd.DataFrame(np.random.rand(10, 2), columns=["a", "b"])
    df_spark = spark.createDataFrame(df_pandas)
    df_converted = df_spark.toPandas()

    pd.testing.assert_frame_equal(df_pandas, df_converted)
