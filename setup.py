from setuptools import setup, find_packages

setup(
    name="joat_trading_system",
    version="0.1",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
)
