from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="majestic",
    version="0.1.0",
    author="Majestic Contributors",
    description="Universal AI agent framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/majestic-agent/majestic",
    packages=find_packages(exclude=["tests*", ".venv*"]),
    python_requires=">=3.11",
    install_requires=[
        "httpx>=0.27.0",
        "fastapi>=0.111.0",
        "uvicorn[standard]>=0.30.0",
        "pydantic>=2.7.0",
        "pyyaml>=6.0.1",
        "python-dotenv>=1.0.1",
        "apscheduler>=3.10.4",
        "pypdf>=4.2.0",
        "python-docx>=1.1.2",
        "trafilatura>=1.12.0",
        "sqlite-vec>=0.1.1",
        "rich>=13.7.1",
        "click>=8.1.7",
        "aiohttp>=3.9.5",
        "questionary>=2.0.1",
        "textual>=0.60.0",
    ],
    entry_points={
        "console_scripts": [
            "majestic=majestic.__main__:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
    ],
    include_package_data=True,
    package_data={
        "majestic": ["py.typed"],
    },
    zip_safe=False,
)
