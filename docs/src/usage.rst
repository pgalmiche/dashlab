==========
How to use
==========

This gives the main steps to make this project run and use it.


Step 1: run docker
----------------------

* build the image

.. code-block:: bash

  make docker-build

* run the container

.. code-block:: bash

  make docker-run


Step 2: Enjoy the code 
--------------------------

You can run the code you want to use and save your results on a git platform.

You can follow the tutorials to deploy your git repo with the documentation with CI.

Step 3: stop docker
----------------------

* stop the container

.. code-block:: bash

  make docker-stop

* delete the image and all dependencies of this project on your computer

.. code-block:: bash

  make docker-image_removal
