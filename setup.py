import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="watson-osint",
    version="0.1.9",
    author="margoul1",
    author_email="github.pydoctor@gmail.com",
    description="Watson OSINT - A powerful tool to search for usernames on multiple platforms",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/margoul1/watson",
    packages=setuptools.find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Security",
        "Topic :: Internet :: WWW/HTTP :: Indexing/Search",
    ],
    python_requires=">=3.6",
    install_requires=[
        "requests",
        "colorama",
        "beautifulsoup4",
        "fake_useragent",
        "dnspython",
        "google-api-python-client",
        "cloudscraper",
        "urllib3",
    ],
    entry_points={
        "console_scripts": [
            "watson=watson.__main__:main",
        ],
    },
)
