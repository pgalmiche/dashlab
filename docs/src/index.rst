===========
repo-setter
===========

**repo-setter** is a project aiming at starting projects that can be run inside docker
containers.

:K3D:`K3D <>` is used for 3D animations exported in a standalone HTML file.
This HTML file can then be opened in any browsers on any laptop,
is can then be easily integrated into a website or presentation slides like reveal js.

.. warning::
   The documentation is not complete yet, this version is
   only used to test the CI on GitHub and GitLab.

Features
--------

**repo-setter** provides:

* docker templates for latex/python/julia/nodejs projects 
* a makefile to simplify docker usage 
* automatic documentation tools like Sphinx or Doxygen

.. note::
   The folder/files organization has been inspired from the SimExporter GitHub project
   make by RobinEnjalbert.

Gallery
-------

.. image:: _static/repository.png



.. toctree::
    :hidden:

    Demo        <demo.rst>
    Install     <install.rst>
    How to use  <usage.rst>
    API         <api.rst>
