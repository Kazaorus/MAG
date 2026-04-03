from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext

# 定义扩展模块
ext_modules = [
    Pybind11Extension(
        "RestaurantDecider",
        ["decider.cpp"],
        include_dirs=["."],
        extra_compile_args=['/std:c++latest', '/utf-8']
    )
]

setup(
    name="RestaurantDecider",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
    zip_safe=False
)