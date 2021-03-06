
from setuptools import setup

setup(
    name =             "cui_pydevd",
    version =          "0.0.1",
    author =           "Christoph Landgraf",
    author_email =     "christoph.landgraf@googlemail.com",
    description =      "PyDev.Debugger Frontend for cui",
    license =          "BSD",
    url =              "https://github.com/clandgraf/cui_pydevd",
    packages =         ['cui_pydevd'],
    install_requires = ['cui', 'cui_source']
)
