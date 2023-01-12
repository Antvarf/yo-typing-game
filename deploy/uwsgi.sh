#!/bin/bash
sudo docker rm e_uwsgi
sudo docker run --name='e_uwsgi' --network='host' -v /var/www/E/db:/app/db e_app uwsgi --ini=uwsgi.ini
