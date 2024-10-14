from setuptools import setup
from setuptools import find_packages
import os
import re

this_dir = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(this_dir, "README.md"), encoding="utf-8") as f:
    long_description = f.read()


# with open('megnet/__init__.py', encoding='utf-8') as fd:
#     try:
#         lines = ''
#         for item in fd.readlines():
#             item = item
#             lines += item + '\n'
#     except Exception as exc:
#         raise Exception('Caught exception {}'.format(exc))


# version = re.search('__version__ = "(.*)"', lines).group(1)


setup(
    name="frgpascal",
    version="0.2",
    description="Control of Fenning Research Group automated synthesis platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Rishi Kumar",
    author_email="rek010@eng.ucsd.edu",
    download_url="https://github.com/fenning-research-group/PASCAL/frgpascal",
    license="MIT",
    install_requires=[
        "numpy",
        "aiohttp",
        "pyyaml",
        "scipy",
        "mixsol",
        "ortools",
        "matplotlib",
        "pandas",
        "pyserial",
        "natsort",
        "ntplib",
        "websockets",
        # "tensorflow",
        "dill",
        "roboflo",
        "PyQt5",
        "tifffile",
        "scikit-image",
        "ax-platform",
        "ntplib",
        "doepy",
    ],
    # extras_require={
    #     'model_saving': ['h5py'],
    #     'molecules': ['openbabel', 'rdkit'],
    #     'tensorflow': ['tensorflow>=2.1'],
    #     'tensorflow with gpu': ['tensorflow-gpu>=2.1'],
    # },
    packages=find_packages(),
    package_data={
        "": [
            "hardware/*.yaml",
            "hardware/*/*.yaml",
            "hardware/*/*/*.yaml",
            "hardware/*/*/*.json",
            "Examples/*.ipynb",
            "experimentaldesign/recipes/liquidhandlerprotocols/*.py",
        ],
    },
    include_package_data=True,
    keywords=["materials", "science", "machine", "automation"],
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: Scientific/Engineering :: Physics",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    # entry_points={
    #     'console_scripts': [
    #         'meg = megnet.cli.meg:main',
    #     ]
    # }
)
