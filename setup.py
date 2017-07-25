#!/usr/bin/env python
"""Setup configuration."""

from setuptools import setup, Extension, distutils, Command, find_packages
import distutils.command.build
import setuptools.command.build_ext
import setuptools.command.install
import setuptools.command.develop
import setuptools.command.build_py
import platform
import subprocess
import shutil
import sys
import os

################################################################################
# https://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
################################################################################
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ['PATH'].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    return None

################################################################################
# Check variables / find programs
################################################################################
DEBUG = os.getenv('DEBUG') in ['ON', '1', 'YES', 'TRUE', 'Y']
PYCLIF = which("pyclif")
CWD = os.path.dirname(os.path.abspath(__file__))

if not PYCLIF:
  PYCLIF = os.getenv("PYCLIF")
  if not PYCLIF:
    # Check for pyclif by running pyclif
    try:
        PYCLIF = subprocess.check_output(['which', 'pyclif'])
    except OSError:
        raise RuntimeError("PYCLIF was not found. Please set environment variable PYCLIF.")

if "KALDI_DIR" not in os.environ:
  raise RuntimeError("KALDI_DIR environment variable is not set.")

KALDI_DIR = os.environ['KALDI_DIR']
KALDI_SRC_DIR = os.path.join(KALDI_DIR, 'src')
KALDI_LIB_DIR = os.path.join(KALDI_DIR, 'src/lib')

CLIF_DIR = os.getenv('CLIF_DIR', None)
if not CLIF_DIR:
    CLIF_DIR = os.path.dirname(os.path.dirname(PYCLIF))
    print("CLIF_DIR environment variable is not set.")
    print("Defaulting to {}".format(CLIF_DIR))

import numpy as np
NUMPY_INC_DIR = np.get_include()

if DEBUG:
    print("#"*50)
    print("CWD: {}".format(CWD))
    print("PYCLIF: {}".format(PYCLIF))
    print("KALDI_DIR: {}".format(KALDI_DIR))
    print("CLIF_DIR: {}".format(CLIF_DIR))
    print("CXX_FLAGS: {}".format(os.getenv("CXX_FLAGS")))
    print("#"*50)

################################################################################
# Workaround setuptools -Wstrict-prototypes warnings
# From: https://github.com/pytorch/pytorch/blob/master/setup.py
################################################################################
import distutils.sysconfig
cfg_vars = distutils.sysconfig.get_config_vars()
for key, value in cfg_vars.items():
    if type(value) == str:
        cfg_vars[key] = value.replace("-Wstrict-prototypes", "")


################################################################################
# Build dependencies
################################################################################
class build_deps(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        cmake_args = ['-DKALDI_DIR='+KALDI_DIR,
                      '-DPYCLIF='+PYCLIF,
                      '-DCLIF_DIR='+CLIF_DIR]

        if DEBUG:
            cmake_args += ['-DCMAKE_VERBOSE_MAKEFILE:BOOL=ON']

        env = os.environ.copy()
        env['CXX_FLAGS'] = '{} -DVERSION_INFO=\\"{}\\"'.format(env.get('CXX_FLAGS', ''),
                                                              self.distribution.get_version())
        if not os.path.exists(self.build_temp):
            os.mkdirs(self.build_temp)

        subprocess.check_call(['cmake', '..'] + cmake_args, cwd=self.build_temp, env = env)
        print()

################################################################################
# Use CMake to build stuff on parallel
# Code from: http://www.benjack.io/2017/06/12/python-cpp-tests.html
################################################################################
class CMakeExtension(Extension):
    def __init__(self, name, sourcedir = ''):
        super(Extension, self).__init__(name, sources = [])
        self.sourcedir = os.path.abspath(sourcedir)

class CMakeBuild(setuptools.command.build_ext.build_ext):
    def run(self):
        self.run_command("build_deps")
        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext):
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        cmake_args = ['-DCMAKE_LIBRARY_OUTPUT_DIRECTORY='+ extdir,
                      '-DPYTHON_EXECUTABLE=' + sys.executable]

        cfg = 'Debug' if DEBUG else 'Release'
        build_args = ['--config', cfg]

        cmake_args += ['--DCMAKE_BUILD_TYPE='+cfg]
        build_args += ['--', '-j2']

        env = os.environ.copy()
        env['CXX_FLAGS'] = '{} -DVERSION_INFO=\\"{}\\"'.format(env.get('CXX_FLAGS', ''),
                                                              self.distribution.get_version())
        if not os.path.exists(self.build_temp):
            os.mkdirs(self.build_temp)

        subprocess.check_call(['cmake', ext.sourcedir] + cmake_args, cwd=self.build_temp, env=env)
        subprocess.check_call(['cmake', '--build', '.'] + build_args, cwd=self.build_temp)
        print() # Add an empty line for cleaner output

    def get_ext_filename(self, fullname):
        """Convert the name of an extension (eg. "foo.bar") into the name
        of the file from which it will be loaded (eg. "foo/bar.so"). This
        patch overrides platform specific extension suffix with ".so".
        """
        ext_path = fullname.split('.')
        ext_suffix = '.so'
        return os.path.join(*ext_path) + ext_suffix

class build(distutils.command.build.build):
    def finalize_options(self):
        self.build_base = 'build'
        self.build_lib = 'build/lib'
        distutils.command.build.build.finalize_options(self)

################################################################################
# Configure compile flags
################################################################################
library_dirs = ['build/lib/kaldi', KALDI_LIB_DIR]

runtime_library_dirs = ['$ORIGIN/..', '$ORIGIN', KALDI_LIB_DIR]

include_dirs = [
    CWD,
    os.path.join(CWD, 'build/kaldi'),  # Path to wrappers generated by clif
    os.path.join(CWD, 'kaldi'),  # Path to hand written wrappers
    os.path.join(CLIF_DIR, '..'),  # Path to clif install dir
    KALDI_SRC_DIR,
    os.path.join(KALDI_DIR, 'tools/openfst/include'),
    os.path.join(KALDI_DIR, 'tools/ATLAS/include'),
    NUMPY_INC_DIR,
]

extra_compile_args = [
    '-std=c++11',
    '-Wno-write-strings',
    '-DKALDI_DOUBLEPRECISION=0',
    '-DHAVE_EXECINFO_H=1',
    '-DHAVE_CXXABI_H',
    '-DHAVE_ATLAS',
    '-DKALDI_PARANOID'
]

extra_link_args = []

libraries = [':_clif.so']

if DEBUG:
    extra_compile_args += ['-O0', '-g', '-UNDEBUG']
    extra_link_args += ['-O0', '-g']

################################################################################
# Declare extensions and packages
################################################################################
extensions = []

clif = Extension(
    "kaldi._clif",
    sources=[
        os.path.join(CLIF_DIR, 'python/runtime.cc'),
        os.path.join(CLIF_DIR, 'python/slots.cc'),
        os.path.join(CLIF_DIR, 'python/types.cc'),
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs)
extensions.append(clif)

symbol_table = Extension(
    "kaldi.fstext.symbol_table",
    sources=[
        'build/kaldi/fstext/symbol-table-clifwrap.cc',
        'build/kaldi/fstext/symbol-table-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    runtime_library_dirs=runtime_library_dirs,
    libraries=['kaldi-fstext'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(symbol_table)

weight = Extension(
    "kaldi.fstext.weight",
    sources=[
        'build/kaldi/fstext/weight-clifwrap.cc',
        'build/kaldi/fstext/weight-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    runtime_library_dirs=runtime_library_dirs,
    libraries=['kaldi-fstext'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(weight)

float_weight = Extension(
    "kaldi.fstext.float_weight",
    sources=[
        'build/kaldi/fstext/float-weight-clifwrap.cc',
        'build/kaldi/fstext/float-weight-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/fstext'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':weight.so', 'kaldi-fstext'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(float_weight)

lattice_weight = Extension(
    "kaldi.fstext.lattice_weight",
    sources=[
        'build/kaldi/fstext/lattice-weight-clifwrap.cc',
        'build/kaldi/fstext/lattice-weight-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/fstext'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':float_weight.so', 'kaldi-fstext'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(lattice_weight)

lattice_utils = Extension(
    "kaldi.fstext.lattice_utils",
    sources=[
        'build/kaldi/fstext/lattice-utils-clifwrap.cc',
        'build/kaldi/fstext/lattice-utils-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    runtime_library_dirs=runtime_library_dirs,
    libraries=libraries,
    extra_link_args=extra_link_args)
extensions.append(lattice_utils)

arc = Extension(
    "kaldi.fstext.arc",
    sources=[
        'build/kaldi/fstext/arc-clifwrap.cc',
        'build/kaldi/fstext/arc-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/fstext'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':lattice_weight.so', 'kaldi-fstext'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(arc)

fst = Extension(
    "kaldi.fstext.fst",
    sources=[
        'build/kaldi/fstext/fst-clifwrap.cc',
        'build/kaldi/fstext/fst-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/fstext'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':arc.so', ':symbol_table.so', 'kaldi-fstext'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(fst)

fst_ext = Extension(
    "kaldi.fstext.fst_ext",
    sources=[
        'build/kaldi/fstext/fst-ext-clifwrap.cc',
        'build/kaldi/fstext/fst-ext-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/fstext'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':fst.so', 'kaldi-fstext'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(fst_ext)

kaldi_fst_io = Extension(
    "kaldi.fstext.kaldi_fst_io",
    sources=[
        'build/kaldi/fstext/kaldi-fst-io-clifwrap.cc',
        'build/kaldi/fstext/kaldi-fst-io-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/fstext'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':fst.so', 'kaldi-fstext'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_fst_io)


matrix_common = Extension(
    "kaldi.matrix.matrix_common",
    sources=[
        'build/kaldi/matrix/matrix-common-clifwrap.cc',
        'build/kaldi/matrix/matrix-common-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    runtime_library_dirs=runtime_library_dirs,
    libraries=['kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(matrix_common)

kaldi_vector = Extension(
    "kaldi.matrix.kaldi_vector",
    sources=[
        'build/kaldi/matrix/kaldi-vector-clifwrap.cc',
        'build/kaldi/matrix/kaldi-vector-clifwrap-init.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':matrix_common.so', 'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_vector)

kaldi_matrix = Extension(
    "kaldi.matrix.kaldi_matrix",
    sources=[
        'build/kaldi/matrix/kaldi-matrix-clifwrap.cc',
        'build/kaldi/matrix/kaldi-matrix-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_vector.so', ':matrix_common.so', 'kaldi-matrix',
               'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_matrix)

matrix_ext = Extension(
    "kaldi.matrix.matrix_ext",
    sources=[
        'kaldi/matrix/matrix-ext.cc',
        ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(matrix_ext)

compressed_matrix = Extension(
    "kaldi.matrix.compressed_matrix",
    sources=[
        'build/kaldi/matrix/compressed-matrix-clifwrap.cc',
        'build/kaldi/matrix/compressed-matrix-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(compressed_matrix)

packed_matrix = Extension(
    "kaldi.matrix.packed_matrix",
    sources=[
        'build/kaldi/matrix/packed-matrix-clifwrap.cc',
        'build/kaldi/matrix/packed-matrix-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(packed_matrix)

sp_matrix = Extension(
    "kaldi.matrix.sp_matrix",
    sources=[
        'build/kaldi/matrix/sp-matrix-clifwrap.cc',
        'build/kaldi/matrix/sp-matrix-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(sp_matrix)

tp_matrix = Extension(
    "kaldi.matrix.tp_matrix",
    sources=[
        'build/kaldi/matrix/tp-matrix-clifwrap.cc',
        'build/kaldi/matrix/tp-matrix-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(tp_matrix)

kaldi_vector_ext = Extension(
    "kaldi.matrix.kaldi_vector_ext",
    sources = [
        "build/kaldi/matrix/kaldi-vector-ext-clifwrap.cc",
        "build/kaldi/matrix/kaldi-vector-ext-clifwrap-init.cc",
    ],
    language="c++",
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':tp_matrix.so', ':sp_matrix.so', ':packed_matrix.so',
               ':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_vector_ext)

matrix_functions = Extension(
    "kaldi.matrix.matrix_functions",
    sources = [
        "build/kaldi/matrix/matrix-functions-clifwrap.cc",
        "build/kaldi/matrix/matrix-functions-clifwrap-init.cc",
    ],
    language="c++",
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(matrix_functions)

kaldi_io = Extension(
    "kaldi.util.kaldi_io",
    sources = [
        "build/kaldi/util/kaldi-io-clifwrap.cc",
        "build/kaldi/util/kaldi-io-clifwrap-init.cc"
    ],
    language = "c++",
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-util', 'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_io)

kaldi_holder = Extension(
    "kaldi.util.kaldi_holder",
    sources = [
        "build/kaldi/util/kaldi-holder-clifwrap.cc",
        "build/kaldi/util/kaldi-holder-clifwrap-init.cc"
    ],
    language = "c++",
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix', 'build/lib/kaldi/util'],
    runtime_library_dirs=runtime_library_dirs,
    libraries=[':kaldi_io.so', ':kaldi_matrix.so', ':kaldi_vector.so', ':matrix_common.so',
               'kaldi-util', 'kaldi-matrix', 'kaldi-base'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_holder)

wave_reader = Extension(
    "kaldi.feat.wave_reader",
    sources = [
        "build/kaldi/feat/wave-reader-clifwrap.cc",
        "build/kaldi/feat/wave-reader-clifwrap-init.cc"
    ],
    language = "c++",
    extra_compile_args = extra_compile_args,
    include_dirs = include_dirs,
    library_dirs = library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs = ['$ORIGIN/../matrix'] + runtime_library_dirs,
    libraries = [':kaldi_matrix.so', 'kaldi-matrix', 'kaldi-feat'] + libraries,
    extra_link_args = extra_link_args)
extensions.append(wave_reader)

kaldi_table = Extension(
    "kaldi.util.kaldi_table",
    sources = [
        "build/kaldi/util/kaldi-table-clifwrap.cc",
        "build/kaldi/util/kaldi-table-clifwrap-init.cc",
    ],
    language = "c++",
    extra_compile_args = extra_compile_args,
    include_dirs = ['kaldi/util/'] + include_dirs,
    library_dirs = library_dirs + ['build/lib/kaldi/util', 'build/lib/kaldi/matrix', 'build/lib/kaldi/feat'],
    runtime_library_dirs = ['$ORIGIN/../feat'] + ['$ORIGIN/../matrix'] + runtime_library_dirs,
    libraries = [':compressed_matrix.so', ':kaldi_matrix.so', ':kaldi_vector.so', ':wave_reader.so',
                 'kaldi-util', 'kaldi-matrix'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(kaldi_table)

options_ext = Extension(
    "kaldi.util.options_ext",
    sources = [
        "build/kaldi/util/options-ext-clifwrap.cc",
        "build/kaldi/util/options-ext-clifwrap-init.cc",
    ],
    language = "c++",
    extra_compile_args = extra_compile_args,
    include_dirs = ['kaldi/util/'] + include_dirs,
    library_dirs = library_dirs,
    runtime_library_dirs = runtime_library_dirs,
    libraries = ['kaldi-util'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(options_ext)

feature_window = Extension(
    "kaldi.feat.feature_window",
    sources=[
        'build/kaldi/feat/feature-window-clifwrap.cc',
        'build/kaldi/feat/feature-window-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=['$ORIGIN/../matrix'] + runtime_library_dirs,
    libraries=[':kaldi_vector.so',
               'kaldi-feat'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(feature_window)

feature_functions = Extension(
    "kaldi.feat.feature_functions",
    sources=[
        'build/kaldi/feat/feature-functions-clifwrap.cc',
        'build/kaldi/feat/feature-functions-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix'],
    runtime_library_dirs=['$ORIGIN/../matrix'] + runtime_library_dirs,
    libraries=[':kaldi_matrix.so', ':kaldi_vector.so',
               'kaldi-feat'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(feature_functions)

mel_computations = Extension(
    "kaldi.feat.mel_computations",
    sources=[
        'build/kaldi/feat/mel-computations-clifwrap.cc',
        'build/kaldi/feat/mel-computations-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix',
                                 'build/lib/kaldi/feat'],
    runtime_library_dirs=['$ORIGIN/../matrix'] + runtime_library_dirs,
    libraries=[':feature_window.so', ':kaldi_vector.so',
               'kaldi-feat'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(mel_computations)

feature_mfcc = Extension(
    "kaldi.feat.feature_mfcc",
    sources=[
        'build/kaldi/feat/feature-mfcc-clifwrap.cc',
        'build/kaldi/feat/feature-mfcc-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix', 'build/lib/kaldi/util',
                                 'build/lib/kaldi/feat'],
    runtime_library_dirs=['$ORIGIN/../matrix', '$ORIGIN/../util'] + runtime_library_dirs,
    libraries=[':mel_computations.so', ':feature_window.so', ':options_ext.so', ':kaldi_vector.so',
               'kaldi-feat'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(feature_mfcc)

feature_common_ext = Extension(
    "kaldi.feat.feature_common_ext",
    sources=[
        'build/kaldi/feat/feature-common-ext-clifwrap.cc',
        'build/kaldi/feat/feature-common-ext-clifwrap-init.cc',
    ],
    language='c++',
    extra_compile_args=extra_compile_args,
    include_dirs=include_dirs,
    library_dirs=library_dirs + ['build/lib/kaldi/matrix',
                                 'build/lib/kaldi/feat'],
    runtime_library_dirs=['$ORIGIN/../matrix'] + runtime_library_dirs,
    libraries=[':feature_mfcc.so', ':kaldi_matrix.so', ':kaldi_vector.so',
               'kaldi-feat'] + libraries,
    extra_link_args=extra_link_args)
extensions.append(feature_common_ext)

packages = find_packages()

setup(name = 'pykaldi',
      version = '0.0.1',
      description='Kaldi Python Wrapper',
      author='SAIL',
      ext_modules=extensions,
      cmdclass= {
          'build_deps': build_deps,
          'build_ext': CMakeBuild,
          'build': build,
          },
      packages=packages,
      package_data={},
      install_requires=['enum34;python_version<"3.4"', 'numpy'])
