from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in royal_mobile_app/__init__.py
from royal_mobile_app import __version__ as version

setup(
	name="royal_mobile_app",
	version=version,
	description="Royal Mobile App",
	author="Axmed Najaad",
	author_email="rasiintech@gmail.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
