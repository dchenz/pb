==
pb
==

``pb`` is a lightweight pastebin (and url shortener) built using
`flask <http://flask.pocoo.org/docs/0.10/quickstart/>`_.

This project was forked from `ptpb.pw
<https://ptpb.pw>`_ and is currently live in the Arista infra.

Building the docker image & running locally
-------------------------------------------

Run the following in your shell:

.. code:: shell-session

    $ cp config.yaml.example config.yaml
    $ docker build -t pb .
    $ docker run -p 10002:10002 -v/tmp/pb:/data/db -t pb

Then access http://127.0.0.1:10002 on your browser.
