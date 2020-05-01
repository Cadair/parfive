Changelog
=========

parfive uses `towncrier <https://github.com/twisted/towncrier>`__ to build its changelog. 

Please add a file to the ``changelog/`` directory with a filename matching ``<pr number>.<type>[.number].rst``. 

The changelog types are:

- ``.feature``: Signifying a new feature.
- ``.bugfix``: Signifying a bug fix.
- ``.doc``: Signifying a documentation improvement.
- ``.removal``: Signifying a deprecation or removal of public API.
- ``.misc``: A ticket has been closed, but it is not of interest to users.
