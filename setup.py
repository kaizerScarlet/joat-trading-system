from setuptools import setup, find_packages

setup(
    name="EPIC-QUEST-4-ALPHA",
    version="2.1.2",  # increment version
    python_requires=">=3.14",
    packages=find_packages(where="src"),
    package_dir={"": "src"}, 
    install_requires=[
        # runtime dependencies
        "websockets==11.0",
        "aiohttp",
        "pandas",
        "pyyaml",
        "python-dotenv",
        "redis",
        "numpy",
        "scikit-learn",
        "requests"
    ],
    extras_require={
        "dev": [
            # development / testing dependencies
            "pytest-asyncio>=0.23",
            "setuptools"
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3.14.0",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
