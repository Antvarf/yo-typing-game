#!/bin/bash
sudo docker rm e_asgi
sudo docker run --name='e_asgi' --network='host' -v /var/www/E/db:/app/db e_app daphne -b 0.0.0.0 -p 8033 E.asgi:application
