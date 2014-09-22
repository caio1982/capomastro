#!/usr/bin/env python
#coding: utf-8

from pip.req import parse_requirements
from distutils.core import setup
from setuptools import find_packages

install_reqs = parse_requirements('requirements.txt')
reqs = [str(ir.req) for ir in install_reqs]

setup(
	name = "capomastro",
	version = "0.1",
	license = "MIT",
	author = "CE Infrastructure",
	author_email = "ce-infrastructure@lists.canonical.com",
	url = "https://github.com/capomastro",
	download_url = "https://github.com/capomastro/capomastro/releases",
	description = "Jenkins best friend",
	include_package_data = True,
	packages = find_packages(),
	# former manage.py
	scripts = ['scripts/capomastro'],
	install_requires = reqs
)
