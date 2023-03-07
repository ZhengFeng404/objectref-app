from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

with open("VERSION", "r") as fh:
    version = fh.read().strip()

setup(
    name='objectref-app',
    version=version,
    package_dir={'': 'py-app'},
    packages=find_packages(include=['*'], where='py-app'),
    data_files=[('VERSION', ['VERSION'])],
    url="https://github.com/numblr/objectref-app",
    license='MIT License',
    author='CLTL',
    author_email='t.baier@vu.nl',
    description='Application for object referencing project',
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires='>=3.8',
    install_requires=[
        "cltl.backend[impl,host,service]",
        "cltl.asr[google,service]",
        "cltl.vad[impl,service]",
        "cltl.chat-ui",
        "cltl.eliza",
        "flask",
        "werkzeug"
    ],
    entry_points={
        'eliza': [ 'eliza = app:main']
    }
)
