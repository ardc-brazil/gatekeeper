from setuptools import setup, find_packages

setup(
    name='gatekeeper',
    version='1.0.0',
    author='Caio Maia',
    author_email='caio.maia@usp.br',
    description='Gatekeeper Backend',
    url='https://github.com/ardc-brazil/gatekeeper',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Flask>=2.0.0',
        'Flask-SQLAlchemy>=3.0.0',
        'psycopg2-binary>=2.9.1',
        'SQLAlchemy>=1.4.23'
    ],
    classifiers=[
        'Development Status :: 1 - Beta',
        'Environment :: Web Environment',
        'Framework :: Flask',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.8',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)