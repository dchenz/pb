==
pb
==

``pb`` is a lightweight pastebin (and url shortener) built using
`flask <http://flask.pocoo.org/docs/0.10/quickstart/>`_.

This project was forked from `ptpb.pw
<https://ptpb.pw>`_ and is currently live at `http://pb/ <http://pb>`_.

Building the docker image & running locally
-------------------------------------------

Run the following in your shell:

.. code:: shell-session

    $ cp config.yaml.example config.yaml
    $ docker build -t pb .
    $ docker run -p 10002:10002 -v/tmp/pb:/data/db -t pb

Then access http://127.0.0.1:10002 on your browser.

Deploying new versions on the infra
-----------------------------------

First, edit `kube/pb-rc.yaml` and bump the version number of the app & container.

Then build, tag & push the container on the infra (setting `pb_version` with the new version number):

.. code:: shell-session

    $ pb_version=x.y.z
    $ docker build -t pb:$pb_version .
    $ docker tag pb:$pb_version registry.docker.sjc.aristanetworks.com:5000/pb:$pb_version
    $ docker push registry.docker.sjc.aristanetworks.com:5000/pb:$pb_version

Finally, update the replication controller on the k8s cluster:

.. code:: shell-session

    $ kubectl rolling-update pb -f kube/pb-rc.yaml

If rolling-update doesn't work (it doesn't right now), simply re-create the units:

.. code:: shell-session

    $ kubectl delete pb -f kube/pb-rc.yaml
    $ kubectl create pb -f kube/pb-rc.yaml

(Do the same thing with `kube/pb-svc.yaml` if you changed it).

Check that everything works at http://pb.staging.kube.sw-infra.sjc.aristanetworks.com/

If you're feeling that everything is OK, re-run the `kubectl` commands with `--namespace=production`. The app is now up and rolling!
