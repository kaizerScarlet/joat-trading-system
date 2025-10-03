from setuptools import setup, find_packages

setup(
    name="Ghost_Of_Turing",
    version="V2.1",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
)
